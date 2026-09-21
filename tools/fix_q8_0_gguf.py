# -*- coding: utf-8 -*-
"""
Repair qwen-image-2.1-Q8_0.gguf  (MinimaxH3 / Qwen-Image-2.1 uncensored GGUF)

Two defects in the published file:
  1) 64 x 1D RMSNorm weights (norm_q / norm_k, 128 dims) were quantized to Q8_0.
     Standard quant rules keep 1D tensors in F32. As Q8_0 the loader sees the
     storage byte count (136 = 4 blocks * 34 B) instead of 128 -> at sampling:
     "Expected weight to be of same shape as normalized_shape, but got weight
      of shape [136] and normalized_shape = [128]".
  2) general.architecture was stripped (kv_count == 0), so arch detection had
     to fall back to detect_arch().

Fix: rewrite every 1D non-F32 tensor back to F32 (dequantize first), keep all
other tensors byte-identical, and inject general.architecture = qwen_image21.

Usage (portable python):
    python _fix_q8_0_gguf.py            # dry-run scan only
    python _fix_q8_0_gguf.py --apply    # write repaired file
"""
import os
import sys
import time

import numpy as np
import gguf
from gguf import GGUFReader, GGUFWriter, GGMLQuantizationType, quants

SRC = r'd:\Software\WorkBuddy\comfyui\models\diffusion_models\qwen-image-2.1-Q8_0.gguf'
DST = r'd:\Software\WorkBuddy\comfyui\models\diffusion_models\qwen-image-2.1-Q8_0_fixed.gguf'
ARCH = 'qwen_image21'

APPLY = '--apply' in sys.argv


def qsize(qtype):
    """(block_size, type_size) for a quantization type."""
    try:
        return gguf.GGML_QUANT_SIZES[qtype]
    except Exception:
        return (1, 0)


def main():
    t0 = time.time()
    if not os.path.exists(SRC):
        print('[FATAL] source not found:', SRC)
        return 1
    print('[open] %s  (%.3f GB)' % (SRC, os.path.getsize(SRC) / 1024 ** 3))

    reader = GGUFReader(SRC, 'r')
    print('[kv] %d fields: %s' % (len(reader.fields), list(reader.fields.keys())))
    n_tensors = len(reader.tensors)
    print('[tensors] %d' % n_tensors)

    # ---- pass 1: scan -------------------------------------------------
    to_fix = []          # (index, name, shape, qtype, storage_bytes, deq_size)
    type_hist = {}
    problems = []
    for i, t in enumerate(reader.tensors):
        qt = t.tensor_type
        type_hist[qt] = type_hist.get(qt, 0) + 1
        shape = tuple(int(x) for x in t.shape)
        nbytes = int(getattr(t.data, 'nbytes', 0))
        if len(shape) == 1 and qt != GGMLQuantizationType.F32:
            try:
                dec = quants.dequantize(t.data, qt)
                dsz = int(dec.size)
            except Exception as e:
                dsz = -1
                problems.append((t.name, 'dequantize failed: %r' % (e,)))
            if dsz != shape[0]:
                problems.append((t.name, 'dequantized size %s != shape %s' % (dsz, shape)))
            to_fix.append((i, t.name, shape, qt, nbytes, dsz))
        else:
            bs, ts = qsize(qt)
            expect = int(np.prod(shape)) // bs * ts if bs else -1
            if nbytes and expect > 0 and nbytes != expect:
                problems.append((t.name, 'storage bytes %d != expected %d' % (nbytes, expect)))

    print('\n---- tensor type histogram ----')
    for qt, c in sorted(type_hist.items(), key=lambda kv: -kv[1]):
        print('  %-10s x%d' % (str(qt).split('.')[-1], c))

    print('\n---- 1D tensors needing F32 rewrite: %d ----' % len(to_fix))
    limit = int(os.environ.get('LIST_ALL', '8'))
    for i, name, shape, qt, nb, dsz in to_fix[:limit]:
        print('  #%-4d %-60s shape=%-10s %s(%dB) -> F32(%dB)'
              % (i, name, shape, str(qt).split('.')[-1], nb, dsz * 4))
    if len(to_fix) > limit:
        print('  ... and %d more' % (len(to_fix) - limit))
    # group by suffix so unexpected 1D tensors stand out
    from collections import Counter
    suf = Counter(n.split('.')[-2] + '.' + n.split('.')[-1] for _, n, *_ in to_fix)
    print('  suffixes: %s' % dict(suf))
    extra = sum(dsz * 4 - nb for _, _, _, _, nb, dsz in to_fix if dsz > 0)
    print('  net size delta: %+d bytes (%.1f KB)' % (extra, extra / 1024.0))

    if problems:
        print('\n⚠️  %d anomaly(ies):' % len(problems))
        for name, msg in problems[:20]:
            print('   %s : %s' % (name, msg))
    else:
        print('\n✅ no structural anomaly detected')

    if not APPLY:
        print('\n[dry-run] nothing written. re-run with --apply to write %s' % DST)
        return 0

    # ---- pass 2: rewrite ---------------------------------------------
    if os.path.exists(DST):
        print('\n[abort] destination already exists, remove it first: %s' % DST)
        return 1

    print('\n[write] -> %s  (use_temp_file=True)' % DST)
    writer = GGUFWriter(DST, ARCH, use_temp_file=True)
    try:
        writer.add_quantization_version(gguf.GGML_QUANT_VERSION)
    except Exception:
        writer.add_quantization_version(2)

    fix_idx = {i for i, *_ in to_fix}
    written = 0
    for i, t in enumerate(reader.tensors):
        if i in fix_idx:
            dec = quants.dequantize(t.data, t.tensor_type)
            writer.add_tensor(t.name, np.ascontiguousarray(dec, dtype=np.float32),
                              raw_dtype=GGMLQuantizationType.F32)
        else:
            writer.add_tensor(t.name, t.data, raw_dtype=t.tensor_type)
        written += 1
        if written % 50 == 0:
            print('   %d/%d tensors  (%.0fs)' % (written, n_tensors, time.time() - t0))

    print('   [flush] writing header + kv + tensor data ...')
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    size = os.path.getsize(DST)
    print('\n[done] %d tensors, %.3f GB, %.0fs' % (written, size / 1024 ** 3, time.time() - t0))

    # ---- verify ------------------------------------------------------
    print('\n---- verify ----')
    r2 = GGUFReader(DST, 'r')
    print('kv fields: %s' % list(r2.fields.keys()))
    arch_field = r2.fields.get('general.architecture')
    if arch_field is not None:
        try:
            print('general.architecture = %r' % (bytes(arch_field.parts[-1]).decode('utf-8'),))
        except Exception as e:
            print('general.architecture raw = %r (%r)' % (arch_field.parts[-1], e))
    print('tensor count: %d' % len(r2.tensors))
    check = {n: (tuple(int(x) for x in t.shape), str(t.tensor_type).split('.')[-1], int(t.data.nbytes))
             for t in r2.tensors for n in [t.name]
             if n in {nm for _, nm, *_ in to_fix}}
    for name in list(check)[:5]:
        print('  %-60s %s' % (name, check[name]))
    if check:
        bad = [n for n, (sh, tp, nb) in check.items() if len(sh) == 1 and tp != 'F32']
        print('remaining 1D non-F32: %d (expect 0)' % len(bad))
    return 0


if __name__ == '__main__':
    sys.exit(main())
