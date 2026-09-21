# Contributing

Thanks for trying this kit. Issues and pull requests are welcome.

## Reporting a bug

Please open an issue and include the following — most "it doesn't work" reports turn
out to be one of three things below, and these details make it a five-minute fix:

1. **The full ComfyUI error report** (the red dialog's "Copy" button), not a screenshot.
   The traceback line matters more than the headline message.
2. **The exact loader values** you used in the workflow:
   - `UnetLoaderGGUF` → which `.gguf` file, and its full filename
   - `CLIPLoader` → which text encoder file, and the `type` you selected
   - `VAELoader` → which VAE file
3. **Environment**: ComfyUI version, GPU model + VRAM, and whether you applied the
   architecture patch from `patches/`.

## The three most common failures

| Symptom | Cause |
| --- | --- |
| `ComfyUI-GGUF: This model is not currently supported - (Unknown model architecture!)` | Architecture patch not applied — see `patches/README.md` |
| `weight shape [136] vs normalized_shape [128]` | You loaded the **original** Q8_0 file instead of the repaired one — run `tools/fix_q8_0_gguf.py` |
| `normalized_shape=[4096] ... got input of size [1, N, 2560]` | Text encoder is a 4B model; this DiT needs the 8B encoder (hidden size 4096) |

## Pull requests

- Keep patches as unified diffs against the upstream file, with the upstream
  commit or file version noted at the top.
- If you fix a workflow JSON, please state in the PR body which node IDs changed
  and what they now point to — filenames alone are not enough, since a workflow
  can reference the wrong model by an identical-looking name.
- Documentation fixes are just as welcome as code fixes.
