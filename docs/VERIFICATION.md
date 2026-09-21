# 实测与校验报告

> 环境：Windows 11 · RTX 5060 Laptop **8 GB** (sm_120) · 33.7 GB RAM · ComfyUI **0.37.0** · PyTorch **2.13.0+cu130** · Python 3.13.12
> 启动参数：`--windows-standalone-build --fast fp16_accumulation --use-sage-attention --reserve-vram 0.5`

---

## 1. 出图实测

| 项 | 数值 |
|---|---|
| 分辨率 | 512 × 512 |
| 步数 | 20 |
| cfg | 1.0 |
| 采样器 / 调度器 | euler / simple |
| seed | 593103825222985 |
| **总耗时** | **32.30 秒**（约 1.15 it/s） |
| 显存峰值 | **7477 / 8151 MiB** |
| 温度峰值 | 76 °C |
| 功耗峰值 | 100.8 W |
| 产物 | `qwen21_gguf_fixed_00001_.png`（326 KB） |

画面内容与提示词完全吻合（黑白时尚编辑肖像 / 圆框墨镜 / 高对比明暗光），**非噪声、非模糊**，链路正确。

### 加载阶段日志

```
[INFO] Model QwenImage21TEModel_ prepared for dynamic VRAM loading. 8916MB Staged. 0 patches attached.
[INFO] gguf qtypes: BF16 (3), Q8_0 (229), F32 (65)
[INFO] model weight dtype torch.bfloat16, manual cast: None
[INFO] model_type FLUX
[INFO] Requested to load QwenImage21
[INFO] loaded partially; 5635.55 MB usable, 5582.88 MB loaded, 1785.00 MB offloaded, 51.00 MB buffer reserved, lowvram patches: 0
0%|          | 0/20 [00:00<?, ?it/s]
[INFO] Prompt executed in 32.30 seconds
```

`BF16 (3), Q8_0 (229), F32 (65)` —— **修复成功的指纹**（原版为 `BF16 (4), Q8_0 (293)`）。

`loaded partially ... 1785.00 MB offloaded` 说明 8 GB 显存确实不够全量驻留，已自动 offload 一部分到内存，速度受影响但可正常完成。

---

## 2. 修复器无损校验

对 `qwen-image-2.1-Q8_0.gguf`（7.07 GB / 297 张量）执行 `tools/gguf_1d_repair.py fix` 后，用 `verify` 做逐张量对比：

```
tensor count: A=297  B=297
names only in A: []
names only in B: []

---- result ----
same-type tensors compared byte-wise : 232
type-converted tensors               : 65
shape mismatches                     : 0
RAW byte mismatches (must be 0)      : 0
VALUE mismatches (must be 0)         : 0
conversion map: {'Q8_0->F32': 64, 'BF16->F32': 1}

1D non-F32 left in B (must be 0): 0

=== PASS - repaired file is numerically identical and structurally sound ===
```

四项断言全部满足：

| # | 断言 | 结果 |
|---|---|---|
| 1 | 张量名字集合一致、无增减 | ✅ 297 / 297 |
| 2 | 类型未变的张量**逐字节相同** | ✅ 232 个，0 差异 |
| 3 | 类型改变的张量数值**完全相等**（`np.array_equal`） | ✅ 65 个，零漂移 |
| 4 | 新文件中残留的一维非 F32 张量数 = 0 | ✅ |

### 修复开销

| 项 | 数值 |
|---|---|
| 耗时 | **14 秒** |
| 输入 | 7.070 GB |
| 输出 | 7.070 GB |
| 体积变化 | **+31.5 KB（+0.0004%）** |
| 额外下载 | **0 字节** |

对比方案：重新下载 Q6_K 档位需 **5.88 GB** 流量。

---

## 3. 与缺陷原版的对照

| 指标 | 缺陷原版 | 修复版 |
|---|---|---|
| 加载指纹 | `BF16 (4), Q8_0 (293)` | `BF16 (3), Q8_0 (229), F32 (65)` |
| 采样 | ❌ `[136] vs [128]` 崩溃 | ✅ 正常出图 |
| 一维张量 | 64 个 Q8_0 + 1 个 BF16 | 全部 F32 |
| `general.architecture` | 缺失（KV=0） | `qwen_image21` |
| 张量数据 | — | **与原版逐值一致** |

---

## 4. 显存边界（8 GB 卡）

| 分辨率 | 估算 token 量 | 结论 |
|---|---|---|
| 512 × 512 | 1× | ✅ 实测通过，峰值 7.48 GB |
| 768 × 768 | 2.25× | ⚠️ 余量 < 0.3 GB，需实测，可能全量 offload |
| 1024 × 1024 | 4× | ❌ 不建议，极易 OOM 或被系统杀进程 |

**建议**：先进 512×512 验证链路通了，再按 +128 的步长往上试，盯 `loaded partially` 那行日志判断 offload 程度。

---

## 5. 复现命令

```bash
# 全流程（假设 ComfyUI 便携版在 <portable>，模型在 <portable>/../models）
PY=<portable>/python_embeded/python.exe

# 1) 扫描缺陷
"$PY" tools/gguf_1d_repair.py scan   <models>/diffusion_models/qwen-image-2.1-Q8_0.gguf

# 2) 重写
"$PY" tools/gguf_1d_repair.py fix    <models>/diffusion_models/qwen-image-2.1-Q8_0.gguf \
                                     <models>/diffusion_models/qwen-image-2.1-Q8_0_fixed.gguf \
                                     --arch qwen_image21

# 3) 校验（必须看到 === PASS ===）
"$PY" tools/gguf_1d_repair.py verify <models>/diffusion_models/qwen-image-2.1-Q8_0.gguf \
                                     <models>/diffusion_models/qwen-image-2.1-Q8_0_fixed.gguf
```
