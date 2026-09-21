# 文件结构 · 模型落位详解

## 1. 上游发布包的结构

从 `abenzerps/Qwen-Image-2.1-Uncensored-GGUF` 下载后，原始包长这样：

```text
qwen-image-2.1Uncensored Model and workflows/     # 32.74 GB
├── diffusion_models/
│   └── qwen-image-2.1-Q8_0.gguf                  7.07 GB   ← 有量化缺陷，必须修复
├── text_encoders/
│   ├── qwen3vl_8b_bf16.safetensors              16.33 GB   ← 可选（显存充裕）
│   └── qwen3vl_8b_int8_convrot.safetensors       8.71 GB   ← 8 GB 显存用这个
├── vae/
│   └── qwen_image_2.1_vae_bf16.safetensors       0.63 GB
└── 越狱工作流/                                     （空目录）
```

> 经 md5 抽样比对，包内的 `qwen3vl_8b_int8_convrot.safetensors` 与 `qwen_image_2.1_vae_bf16.safetensors` 同 `Comfy-Org/Qwen-Image-2.1` 发布的文件**完全一致** —— 如果本地已经有这两个文件，无需重复下载。

## 2. 在 ComfyUI 里应该放哪

ComfyUI 的模型目录由 `extra_model_paths.yaml` 决定。默认情况下：

| 文件类型 | 目标目录（相对 ComfyUI 根） | 本套件工作流里的节点 |
|---|---|---|
| 扩散模型 GGUF | `models/diffusion_models/`（或 `models/unet/`） | `UnetLoaderGGUF` |
| 文本编码器 | `models/text_encoders/`（或 `models/clip/`） | `CLIPLoader` |
| VAE | `models/vae/` | `VAELoader` |

**落位后应该是：**

```text
<ComfyUI>/models/
├── diffusion_models/
│   ├── qwen-image-2.1-Q8_0.gguf            # 原始文件（保留作对照/备份）
│   └── qwen-image-2.1-Q8_0_fixed.gguf      # 修复后的文件 ← 工作流指向这个
├── text_encoders/
│   ├── qwen3vl_8b_int8_convrot.safetensors
│   └── qwen3vl_8b_bf16.safetensors         # 可选
└── vae/
    └── qwen_image_2.1_vae_bf16.safetensors
```

## 3. 两个多路径的坑

### 坑 A：`is_default: true` 是"插到最前"，不是"替换"

`extra_model_paths.yaml` 中：

```yaml
some_config:
    base_path: D:/somewhere/ComfyUI
    is_default: true
    diffusion_models: models/diffusion_models
```

`is_default: true` 只是把这条配置**插到搜索列表最前面**，ComfyUI 便携版**自带的** `models/` 目录仍然在列表里。结果是**两个目录的文件会同时出现在下拉里**，同名文件容易选错。

→ 排查"明明换了模型但报错照旧"时，先确认下拉里的**完整文件名**与你以为的不是两个不同文件。

### 坑 B：节点包多副本

`custom_nodes` 也可以被 `extra_model_paths.yaml` 外挂注册。如果同一个节点包（如 `ComfyUI-GGUF`）在多个位置各有一份，ComfyUI 会**并行加载**它们，再用 `NODE_CLASS_MAPPINGS` 合并同名类 —— **哪一份生效是不确定的**。

```text
[INFO] 0.0 seconds: <A>/ComfyUI/custom_nodes/ComfyUI-GGUF
[INFO] 0.0 seconds: <B>/CustomNodes/CustomNodes-TorI2V/ComfyUI-GGUF
[INFO] 0.0 seconds: <B>/CustomNodes/CustomNodes-TorI2V/ComfyUI-GGUF-molbal
```

→ 给其中一份打补丁可能完全不生效。**定位方法**：看报错的 traceback 里出现的文件路径，那就是真正生效的那份。

## 4. 目录名含空格/中文会怎样

ComfyUI 与 Python 能处理，但：

- 命令行操作（`cd`、`copy`）容易被转义吃掉字符，建议全程加引号；
- Git / 部分脚本对非 ASCII 路径兼容性差；
- 本仓库的文件因此统一改成 **英文名 + 连字符**（例如 `workflows/qwen_image_2.1_t2i_gguf.json`），内容不变。

## 5. 本仓库目录 ↔ 本地文件对应关系

| 本仓库 | 本地来源 |
|---|---|
| `workflows/qwen_image_2.1_t2i_gguf.json` | `（越狱版）image_qwen_image_2_1_t2i_gguf.json`（模型名已指向 `_fixed`） |
| `workflows/qwen_image_2.1_multi_image_edit.json` | `（越狱版）Qwen image 2.1 多图片编辑模型.json`（同上） |
| `patches/*.patch` | 对 `ComfyUI-GGUF/tools/convert.py` 与 `loader.py` 的实际改动 |
| `tools/*.py` | 本次排障中实际使用并验证过的脚本 |

> 原始工作流里的 `UnetLoaderGGUF` 下拉值原本是 `qwen-image-2.1-Q6_K.gguf`（该档位并未随包提供）。本仓库版本已统一改为 `qwen-image-2.1-Q8_0_fixed.gguf`。
