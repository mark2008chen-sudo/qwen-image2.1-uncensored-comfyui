# NOTICE · 来源、许可与免责声明

## 1. 本仓库包含什么

本仓库**只包含**以下内容，全部由整理者编写或从上游开源项目摘录：

| 目录 | 内容 | 许可 |
|---|---|---|
| `workflows/` | ComfyUI 工作流 JSON | MIT |
| `tools/` | GGUF 修复与校验脚本（原创） | MIT |
| `patches/` | 针对 ComfyUI-GGUF 的适配补丁（原创） | MIT |
| `scripts/` | 权重下载脚本（原创） | MIT |
| `docs/` | 文档（原创） | MIT |

## 2. 本仓库不包含什么

**模型权重一律未包含**，原因：权重合计 32.74 GB，超出 GitHub 单文件 100 MB 硬限制、Release 附件 2 GB 上限、以及 Git LFS 免费额度（1 GB）。权重请从下列上游仓库自行获取。

## 3. 上游来源

| 组件 | 上游仓库 | 说明 |
|---|---|---|
| Qwen-Image-2.1 基座模型 | `Qwen/Qwen-Image-2.1` (Hugging Face) | 阿里通义千问图像模型 |
| GGUF 量化 + Uncensored 版 | `abenzerps/Qwen-Image-2.1-Uncensored-GGUF` (Hugging Face) | 本套件主要目标模型；**其 Q8_0 档存在一维张量量化缺陷**，见 `docs/TROUBLESHOOTING.md` |
| 文本编码器 / VAE（ComfyUI repack） | `Comfy-Org/Qwen-Image-2.1` (Hugging Face) | int8_convrot / bf16 精度版本 |
| GGUF 加载节点 | `city96/ComfyUI-GGUF`、`leejet/ComfyUI-GGUF` (GitHub) | 本仓库补丁针对 city96 原版编写 |
| ComfyUI 本体 | `comfyanonymous/ComfyUI` (GitHub) | 需 ≥ 0.37.0 |

## 4. 许可

- 本仓库原创部分（工作流、脚本、文档、补丁）以 **MIT License** 发布，可自由使用、修改、再分发，请保留出处。
- `patches/` 中的代码片段取自 `leejet/ComfyUI-GGUF`（遵循其原始许可），并标注了出处与用途。
- 模型权重的许可条款以**各上游仓库为准**，与本仓库无关。

## 5. 免责声明

1. **`Uncensored` 的含义**：上游仓库移除了内容过滤器（内容审核绕过），模型可接受更宽泛的提示词。本仓库仅为技术配套，**不生成、不托管、不分发任何生成内容**。
2. **合规责任在使用者**：请自行确保你的使用方式与生成内容符合所在地法律法规、以及你所用平台的服务条款。请勿用于生成违法内容。
3. **无隶属关系**：本仓库整理者与 Qwen 团队、`abenzerps`、ComfyUI 官方及其节点作者均**无隶属或背书关系**。
4. **无担保**：脚本与文档按"现状"提供，不提供任何明示或默示担保。模型文件重写等操作有潜在风险，**请务必先备份原始文件**（本套件所有工具默认另存新文件，不覆盖原文件）。
5. **技术准确性**：文档中的实测数据来自一次具体部署（Windows + RTX 5060 Laptop 8 GB + ComfyUI 0.37.0），你的环境结果可能不同。

## 6. 致谢

- 阿里通义千问团队 —— Qwen-Image-2.1 基座模型
- `abenzerps` —— GGUF 量化与 Uncensored 分发
- `city96` / `leejet` —— ComfyUI-GGUF 节点
- ComfyUI 团队 —— 0.37.0 的原生 Qwen-Image-2.1 支持
