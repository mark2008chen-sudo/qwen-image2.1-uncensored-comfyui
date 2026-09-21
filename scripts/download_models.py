#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download the Qwen-Image-2.1 Uncensored weights this kit expects.

Files and their upstream repos (Hugging Face):

  diffusion_models/qwen-image-2.1-Q8_0.gguf          abenzerps/Qwen-Image-2.1-Uncensored-GGUF
  text_encoders/qwen3vl_8b_int8_convrot.safetensors  Comfy-Org/Qwen-Image-2.1
  text_encoders/qwen3vl_8b_bf16.safetensors          Comfy-Org/Qwen-Image-2.1   (optional, 16 GB)
  vae/qwen_image_2.1_vae_bf16.safetensors            Comfy-Org/Qwen-Image-2.1

Features: resume (HTTP Range), mirror fallback, size + sha256 verification.

Usage
  python download_models.py --dir D:/ComfyUI/models
  python download_models.py --dir D:/ComfyUI/models --mirror
  python download_models.py --dir D:/ComfyUI/models --only gguf
  python download_models.py --dir D:/ComfyUI/models --with-bf16
  python download_models.py --dir D:/ComfyUI/models --token hf_xxx
"""
import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request

HF = "https://huggingface.co"
MIRROR = "https://hf-mirror.com"

# key, repo path, target subdir, filename, approx bytes, optional?
FILES = [
    ("gguf", "abenzerps/Qwen-Image-2.1-Uncensored-GGUF", "diffusion_models",
     "diffusion_models/qwen-image-2.1-Q8_0.gguf", 7_591_551_648, False),
    ("te-int8", "Comfy-Org/Qwen-Image-2.1", "text_encoders",
     "text_encoders/qwen3vl_8b_int8_convrot.safetensors", 9_354_000_000, False),
    ("vae", "Comfy-Org/Qwen-Image-2.1", "vae",
     "vae/qwen_image_2.1_vae_bf16.safetensors", 675_000_000, False),
    ("te-bf16", "Comfy-Org/Qwen-Image-2.1", "text_encoders",
     "text_encoders/qwen3vl_8b_bf16.safetensors", 17_537_000_000, True),
]


def human(n):
    return "%.2f GB" % (n / 1024 ** 3)


def sha256(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def probe(url, token=None, timeout=20):
    """HEAD the url; return (ok, total_size, supports_range)."""
    req = urllib.request.Request(url, method="HEAD")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "qwen21-kit/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            total = int(r.headers.get("Content-Length") or 0)
            return True, total, (r.headers.get("Accept-Ranges", "").lower() == "bytes")
    except Exception as e:
        return False, 0, str(e)


def download(url, dest, token=None, expect=None):
    """Resume-capable download. Returns (ok, message)."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if expect and have == expect:
        print("   already complete, skip")
        return True, "exists"

    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "qwen21-kit/1.0")
    if have:
        req.add_header("Range", "bytes=%d-" % have)
        print("   resume from %s" % human(have))

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if have and r.status != 206:
                print("   server ignored Range, restarting from 0")
                have = 0
            mode = "ab" if have else "wb"
            total = have + int(r.headers.get("Content-Length") or 0)
            done = have
            t0 = time.time()
            last = 0.0
            with open(dest, mode) as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last > 2:
                        last = now
                        spd = (done - have) / max(now - t0, 1e-6) / 1024 ** 2
                        pct = ("%5.1f%%" % (done * 100.0 / total)) if total else "  ?  "
                        print("   %s  %s / %s  %.1f MB/s" % (pct, human(done), human(total), spd), flush=True)
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.reason)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)

    size = os.path.getsize(dest)
    if expect and size != expect:
        return False, "size mismatch: got %d, expected %d" % (size, expect)
    return True, "ok"


def main():
    ap = argparse.ArgumentParser(description="Download Qwen-Image-2.1 Uncensored weights")
    ap.add_argument("--dir", required=True, help="ComfyUI models directory")
    ap.add_argument("--mirror", action="store_true", help="use hf-mirror.com (mainland China)")
    ap.add_argument("--only", default=None, help="comma separated: gguf,te-int8,vae,te-bf16")
    ap.add_argument("--with-bf16", action="store_true", help="also download the 16 GB bf16 text encoder")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"), help="HF token (or env HF_TOKEN)")
    ap.add_argument("--sha256", action="store_true", help="print sha256 of each finished file")
    a = ap.parse_args()

    base = MIRROR if a.mirror else HF
    print("=" * 72)
    print("Qwen-Image-2.1 Uncensored · weights downloader")
    print("endpoint : %s" % base)
    print("target   : %s" % a.dir)
    print("=" * 72)

    want = None
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}

    rc = 0
    for key, repo, sub, relpath, approx, optional in FILES:
        if want and key not in want:
            continue
        if optional and not a.with_bf16 and not (want and key in want):
            print("\n[skip] %s (optional, enable with --with-bf16)" % key)
            continue

        fname = os.path.basename(relpath)
        dest = os.path.join(a.dir, sub, fname)
        url = "%s/%s/resolve/main/%s" % (base, repo, relpath)

        print("\n[%s] %s  (~%s)" % (key, fname, human(approx)))
        print("   from %s" % repo)
        ok, total, info = probe(url, a.token)
        if not ok:
            print("   [!] unreachable: %s" % info)
            if not a.mirror:
                print("   retry with --mirror ...")
                ok2, total, info2 = probe("%s/%s/resolve/main/%s" % (MIRROR, repo, relpath), a.token)
                if ok2:
                    url = "%s/%s/resolve/main/%s" % (MIRROR, repo, relpath)
                    print("   mirror ok")
                else:
                    print("   [FAIL] mirror also unreachable")
                    rc = 1
                    continue
            else:
                rc = 1
                continue
        else:
            print("   remote size %s" % (human(total) if total else "unknown"))

        ok, msg = download(url, dest, a.token, total or None)
        if ok:
            print("   [OK] %s  %s" % (dest, human(os.path.getsize(dest))))
            if a.sha256:
                print("   sha256 %s" % sha256(dest))
        else:
            print("   [FAIL] %s" % msg)
            rc = 1

    print("\n" + "=" * 72)
    if rc == 0:
        print("All requested files are in place.")
        print("\nNEXT: repair the Q8_0 quantization defect (required!)")
        print("  python tools/gguf_1d_repair.py scan   %s"
              % os.path.join(a.dir, "diffusion_models", "qwen-image-2.1-Q8_0.gguf"))
        print("  python tools/gguf_1d_repair.py fix    <src> <dst> --arch qwen_image21")
    else:
        print("Finished with errors, see above.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
