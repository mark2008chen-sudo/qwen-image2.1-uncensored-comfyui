#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Repair a GGUF whose 1D tensors were wrongly quantized, and verify the rewrite.

Why: standard quant rules (city96/ComfyUI-GGUF tools/convert.py) keep every
1D tensor in F32. Some published GGUFs quantize RMSNorm weights (norm_q/norm_k,
128 dims) to Q8_0. Q8_0 packs 32 elements into 34 bytes, so 128 elements take
136 bytes; the loader then sees a weight of shape [136] and sampling dies with
    Expected weight to be of same shape as normalized_shape,
    but got weight of shape [136] and normalized_shape = [128]
The data itself is fine - it just needs dequantizing back to F32.

Subcommands
    scan   <src>                      list 1D non-F32 tensors, no writes
    fix    <src> <dst> [--arch NAME]  rewrite (1D -> F32) + inject architecture
    verify <src> <dst>                bit-level diff of the two files

Notes / pitfalls
  * Requires a Python with `gguf` + numpy. In a ComfyUI portable install use
    <portable>\\python_embeded\\python.exe, which ships gguf + numpy.
  * Use GGUFWriter(..., use_temp_file=True) so the ~7 GB of tensor data is not
    held in RAM.
  * Python 3.11+ IntEnum.__str__ returns the *number*, not the name. Comparing
    str(t.tensor_type) to 'F32' silently fails - always use `.name` or compare
    against GGMLQuantizationType members.
  * The writer leaves reader file handles open; do not try to delete the output
    inside the same process on Windows (WinError 32).
"""
import argparse
import os
import sys
import time
from collections import Counter

import numpy as np
from gguf import GGUFReader, GGUFWriter, GGMLQuantizationType, quants


def tname(qt):
    """Type name that works on py3.8..3.13 (IntEnum str() changed in 3.11)."""
    return getattr(qt, "name", None) or str(qt)


def quant_version():
    try:
        import gguf
        return gguf.GGML_QUANT_VERSION
    except Exception:
        return 2


def scan(src, verbose=True):
    r = GGUFReader(src, "r")
    hist = Counter(tname(t.tensor_type) for t in r.tensors)
    todo = []
    problems = []
    for t in r.tensors:
        shape = tuple(int(x) for x in t.shape)
        nb = int(getattr(t.data, "nbytes", 0))
        if len(shape) == 1 and t.tensor_type != GGMLQuantizationType.F32:
            try:
                dsz = int(quants.dequantize(t.data, t.tensor_type).size)
            except Exception as e:                      # noqa: BLE001
                dsz = -1
                problems.append((t.name, "dequantize failed: %r" % (e,)))
            if dsz != shape[0]:
                problems.append((t.name, "dequant size %s != shape %s" % (dsz, shape)))
            todo.append((t.name, shape, t.tensor_type, nb, dsz))
    if verbose:
        print("[kv] %s" % list(r.fields.keys()))
        print("[tensors] %d  types: %s" % (len(r.tensors), dict(hist)))
        print("[1D non-F32] %d" % len(todo))
        for n, sh, qt, nb, dsz in todo[:10]:
            print("   %-58s %s %s(%dB) -> F32(%dB)" % (n, sh, tname(qt), nb, dsz * 4))
        if len(todo) > 10:
            print("   ... %d more" % (len(todo) - 10))
        print("   suffixes: %s" % dict(Counter(n.split(".")[-2] + "." + n.split(".")[-1]
                                              for n, *_ in todo)))
        print("   size delta: %+d B" % sum(d * 4 - nb for _, _, _, nb, d in todo if d > 0))
        print("[anomalies] %d" % len(problems))
        for n, m in problems[:10]:
            print("   %s : %s" % (n, m))
    return r, todo, problems


def cmd_scan(a):
    scan(a.src)
    return 0


def cmd_fix(a):
    t0 = time.time()
    r, todo, problems = scan(a.src)
    if problems:
        print("[abort] structural anomalies found - fix the file, do not rewrite it")
        return 1
    if os.path.exists(a.dst):
        print("[abort] destination exists: %s" % a.dst)
        return 1
    arch = a.arch
    if not arch:
        f = r.fields.get("general.architecture")
        arch = bytes(f.parts[-1]).decode("utf-8") if f is not None else None
    print("[arch] %s" % (arch or "<none>"))
    w = GGUFWriter(a.dst, arch, use_temp_file=True)
    w.add_quantization_version(quant_version())
    fix = {n for n, *_ in todo}
    for i, t in enumerate(r.tensors):
        if t.name in fix:
            d = quants.dequantize(t.data, t.tensor_type)
            w.add_tensor(t.name, np.ascontiguousarray(d, dtype=np.float32),
                         raw_dtype=GGMLQuantizationType.F32)
        else:
            # keep the original storage bytes untouched
            w.add_tensor(t.name, t.data, raw_dtype=t.tensor_type)
        if (i + 1) % 100 == 0:
            print("   %d/%d (%.0fs)" % (i + 1, len(r.tensors), time.time() - t0))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    print("[done] %s  %.3f GB  %.0fs" % (a.dst, os.path.getsize(a.dst) / 1024 ** 3,
                                         time.time() - t0))
    print("[next] run:  %s verify %s %s" % (sys.argv[0], a.src, a.dst))
    return 0


def cmd_verify(a):
    ra, rb = GGUFReader(a.src, "r"), GGUFReader(a.dst, "r")
    na = {t.name: t for t in ra.tensors}
    nb = {t.name: t for t in rb.tensors}
    only_a, only_b = sorted(set(na) - set(nb)), sorted(set(nb) - set(na))
    shape_diff, raw_diff, val_diff, converted = [], [], [], []
    same = 0
    for name, ta in na.items():
        tb = nb.get(name)
        if tb is None:
            continue
        sa = tuple(int(x) for x in ta.shape)
        sb = tuple(int(x) for x in tb.shape)
        if sa != sb:
            shape_diff.append((name, sa, sb))
            continue
        if tname(ta.tensor_type) == tname(tb.tensor_type):
            same += 1
            if ta.data.tobytes() != tb.data.tobytes():
                raw_diff.append((name, tname(ta.tensor_type)))
        else:
            da = quants.dequantize(ta.data, ta.tensor_type).astype(np.float32).ravel()
            db = np.asarray(tb.data, dtype=np.float32).ravel()
            ok = da.shape == db.shape and np.array_equal(da, db)
            converted.append((name, tname(ta.tensor_type), tname(tb.tensor_type), ok))
            if not ok:
                val_diff.append((name, tname(ta.tensor_type), tname(tb.tensor_type)))
    bad = [(t.name, tuple(int(x) for x in t.shape)) for t in rb.tensors
           if len(t.shape) == 1 and t.tensor_type != GGMLQuantizationType.F32]
    print("tensors: A=%d B=%d | only-in-A=%d only-in-B=%d" % (len(na), len(nb),
                                                             len(only_a), len(only_b)))
    print("byte-identical same-type tensors : %d" % same)
    print("type-converted tensors           : %d  %s"
          % (len(converted), dict(Counter("%s->%s" % (x[1], x[2]) for x in converted))))
    print("shape mismatches / raw diffs / value diffs : %d / %d / %d"
          % (len(shape_diff), len(raw_diff), len(val_diff)))
    print("1D non-F32 left in B (must be 0) : %d" % len(bad))
    for x in (shape_diff + raw_diff + val_diff)[:5]:
        print("   !!", x)
    ok = not (only_a or only_b or shape_diff or raw_diff or val_diff or bad)
    print("=== %s ===" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan");   p.add_argument("src"); p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("fix");    p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--arch", default=None,
                   help="general.architecture to inject; defaults to the source's own value")
    p.set_defaults(fn=cmd_fix)
    p = sub.add_parser("verify"); p.add_argument("src"); p.add_argument("dst")
    p.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
