# -*- coding: utf-8 -*-
"""Bit-level verification: qwen-image-2.1-Q8_0_fixed.gguf vs the original.

Checks
  1. identical tensor name set / shapes
  2. every tensor whose type is unchanged  -> raw bytes must be byte-identical
  3. every tensor whose type changed (1D Q8_0/BF16 -> F32) -> dequantized
     values must be exactly equal (no numeric drift)
  4. no 1D non-F32 tensor left in the repaired file
"""
import sys
import numpy as np
import gguf
from gguf import GGUFReader, GGMLQuantizationType, quants

A = r'd:\Software\WorkBuddy\comfyui\models\diffusion_models\qwen-image-2.1-Q8_0.gguf'
B = r'd:\Software\WorkBuddy\comfyui\models\diffusion_models\qwen-image-2.1-Q8_0_fixed.gguf'


def nm(qt):
    return getattr(qt, 'name', str(qt))


def main():
    ra = GGUFReader(A, 'r')
    rb = GGUFReader(B, 'r')
    na = {t.name: t for t in ra.tensors}
    nb = {t.name: t for t in rb.tensors}

    only_a = sorted(set(na) - set(nb))
    only_b = sorted(set(nb) - set(na))
    print('tensor count: A=%d  B=%d' % (len(na), len(nb)))
    print('names only in A: %s' % only_a[:5])
    print('names only in B: %s' % only_b[:5])

    shape_diff, raw_diff, val_diff = [], [], []
    converted = []
    same_type = 0

    for name, ta in na.items():
        tb = nb.get(name)
        if tb is None:
            continue
        sa = tuple(int(x) for x in ta.shape)
        sb = tuple(int(x) for x in tb.shape)
        if sa != sb:
            shape_diff.append((name, sa, sb))
            continue
        qa, qb = ta.tensor_type, tb.tensor_type
        if nm(qa) == nm(qb):
            same_type += 1
            if ta.data.tobytes() != tb.data.tobytes():
                raw_diff.append((name, nm(qa)))
        else:
            da = quants.dequantize(ta.data, qa).astype(np.float32).ravel()
            db = np.asarray(tb.data, dtype=np.float32).ravel()
            ok = da.shape == db.shape and np.array_equal(da, db)
            converted.append((name, nm(qa), nm(qb), int(da.size), ok))
            if not ok:
                val_diff.append((name, nm(qa), nm(qb), da.shape, db.shape,
                                 float(np.abs(da[:db.size] - db).max()) if da.size == db.size else -1))

    print('\n---- result ----')
    print('same-type tensors compared byte-wise : %d' % same_type)
    print('type-converted tensors               : %d' % len(converted))
    print('shape mismatches                     : %d' % len(shape_diff))
    print('RAW byte mismatches (must be 0)      : %d' % len(raw_diff))
    print('VALUE mismatches (must be 0)         : %d' % len(val_diff))
    for x in shape_diff[:5]:
        print('   SHAPE', x)
    for x in raw_diff[:5]:
        print('   RAW  ', x)
    for x in val_diff[:5]:
        print('   VAL  ', x)

    from collections import Counter
    print('conversion map: %s' % dict(Counter('%s->%s' % (a, b) for _, a, b, _, _ in converted)))

    bad = [(t.name, nm(t.tensor_type), tuple(int(x) for x in t.shape))
           for t in rb.tensors if len(t.shape) == 1 and t.tensor_type != GGMLQuantizationType.F32]
    print('\n1D non-F32 left in B (must be 0): %d' % len(bad))
    for x in bad[:5]:
        print('   ', x)

    ok = (not only_a and not only_b and not shape_diff and not raw_diff
          and not val_diff and not bad)
    print('\n=== %s ===' % ('PASS - repaired file is numerically identical and structurally sound'
                            if ok else 'FAIL - see above'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
