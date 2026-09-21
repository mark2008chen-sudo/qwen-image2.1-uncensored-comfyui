# 排错手册 · 三个坑的完整过程

本套件整理自一次真实部署 —— Windows + RTX 5060 Laptop 8 GB + ComfyUI 0.37.0 跑 Qwen-Image-2.1 Uncensored (GGUF)。以下是撞到的全部问题与解法，按**出现顺序**排列。

---

## 坑 1 · `Unknown model architecture!`

### 症状

```
This model is not currently supported - (Unknown model architecture!)
```

### 定位

```python
from gguf import GGUFReader
r = GGUFReader(path)
print(list(r.fields.keys()))
```

正常应该有 `general.architecture` 等业务字段。本模型只返回：

```
['GGUF.version', 'GGUF.tensor_count', 'GGUF.kv_count']
```

→ 元数据被剥离，loader 只能靠 `detect_arch()` 按张量名猜架构，而 `city96/ComfyUI-GGUF` 的 `arch_list` 里没有 Qwen。

### 解决

打架构补丁（新增 `QwenImage21` 类 + 追加进 `arch_list` / `IMG_ARCH_LIST`）→ 见 `patches/README.md`。

> ⚠️ 注意别把两个同名报错搞混：`detect_arch()` 内部的断言文本也是 `Unknown model architecture!`，和 ComfyUI 核心的报错长得一样，要看 traceback 判断来源。

---

## 坑 2 · 补丁打了不生效（多副本）

### 症状

补丁明明改了，报错照旧，且 traceback 指向一个"你以为没在用的"目录。

### 原因

多份 `ComfyUI-GGUF` 副本被并行加载（`extra_model_paths.yaml` 外挂注册 + `custom_nodes` 自带），注册顺序不确定。

### 解决

**所有副本都打补丁**。用 traceback 里的路径确认哪份在生效。

---

## 坑 3 · `weight of shape [136] and normalized_shape = [128]` ⭐

### 症状

模型能加载成功（`gguf qtypes` 正常打印），但一进入采样就崩：

```
RuntimeError: Expected weight to be of same shape as normalized_shape,
but got weight of shape [136] and normalized_shape = [128]
```

栈底固定落在：

```
comfy/ldm/qwen_image21/model.py:102   q, k = comfy.quant_ops.ck.rms_rope(...)
  → comfy_kitchen/backends/eager/rope.py:85   x_norm = torch.nn.functional.rms_norm(...)
```

### 原因

**发布方的量化缺陷**：标准 GGUF 转换规则（`city96` 的 `convert.py`）要求 **一维张量保持 F32**，而该文件的 **65 个一维张量被错误量化**：

| 张量 | 数量 | 维度 | 原类型 | 存储字节 |
|---|---|---|---|---|
| `transformer_blocks.N.attn.norm_q.weight` | 32 | 128 | Q8_0 | 136 |
| `transformer_blocks.N.attn.norm_k.weight` | 32 | 128 | Q8_0 | 136 |
| `txt_in.text_norm.weight` | 1 | 4096 | BF16 | 8192 |

Q8_0 的打包方式是**每 32 个元素 = 1 个 fp16 scale + 32 个 int8 = 34 字节**。128 个元素 → 4 块 → **136 字节**。loader 把「存储字节数」当成了权重形状，于是 `rms_norm` 拿到 136 维的 weight 去归一化 128 维的输入 → 报错。

### 关键判据：数据本身是好的

```python
from gguf import quants
t = [x for x in r.tensors if x.name.endswith('norm_q.weight')][0]
print(tuple(t.shape), t.tensor_type, t.data.nbytes)      # (128,) Q8_0 136
print(quants.dequantize(t.data, t.tensor_type).shape)    # (128,)  ← 能正确还原
```

dequantize 能还原 → 只是**封装方式违规**，不是数据损坏 → **可以就地修复**，不必重新下载数 GB。

### 解决（三条路，推荐第 2 条）

1. **换量化档位**：Q6_K / Q5_K_M / Q4_K_M 通常 1D 张量正确保留 F32。代价是要重新下载。
2. **就地重写 GGUF**（推荐）：把 65 个一维张量反量化回 F32 重新封装，其余张量原样搬运，顺带补上 `general.architecture`。
   ```bash
   python tools/gguf_1d_repair.py scan   <src.gguf>
   python tools/gguf_1d_repair.py fix    <src.gguf> <dst.gguf> --arch qwen_image21
   python tools/gguf_1d_repair.py verify <src.gguf> <dst.gguf>
   ```
   - 7.07 GB 文件 **约 14 秒**完成
   - 体积只增加 **+31.5 KB**
   - `verify` 会做逐张量字节级对比，必须看到 `=== PASS ===`

3. 改 loader 对 1D 量化张量的处理（不确定性最高，且多副本环境要改多处，不推荐）。

### 顺带一提

修复后的文件加载日志会变成：

```
[INFO] gguf qtypes: BF16 (3), Q8_0 (229), F32 (65)      ← 297 = 3 + 229 + 65
```

而缺陷原版是：

```
[INFO] gguf qtypes: BF16 (4), Q8_0 (293)                ← 297 = 4 + 293
```

**看这一行就能立刻判断当前加载的是修复版还是原版** —— 排障时非常有用。

---

## 坑 4 · 进程凭空消失，日志无 traceback

### 症状

模型加载到一半（日志停在 `Requested to load QwenImage21`），进程没了，**日志里没有 Python 异常栈**，端口关闭。

### 原因

**系统内存耗尽**导致进程被强制终止（不会产生 Python traceback）。加载阶段内存占用是叠加的：

- 文本编码器 `QwenImage21TEModel_` staged **8916 MB**
- DiT：7 GB Q8_0 → 转 bf16 约 **13 GB**

8 GB 显存必然触发 offload 到内存，内存不足即被杀。

### 解决

- 关掉其他吃内存的程序（浏览器、IDE 等）；
- 分辨率降档（512×512 起步）；
- 加内存 / 增大页面文件；
- 若日志出现 `loaded partially; ... MB offloaded`，说明已走 offload 路径，能跑但会慢。

---

## 坑 5 · `Given normalized_shape=[4096] ... got input of size[1,N,2560]`

### 原因

文本编码器选错。Qwen-Image-2.1 的 DiT `txt_in` 期望 **4096** 维隐层，只有 **Qwen3-VL-8B** 匹配。

`comfy/sd.py` 中的分支条件：

```python
if clip_type == CLIP_TYPE.QWEN_IMAGE and te_model == TEModel.QWEN3VL_8B:
    # 走 qwen_image21.te（4096）
else:
    # 落到通用 qwen3vl_4b（2560）
```

### 解决

`CLIPLoader` 的模型必须是 **Qwen3-VL-8B**（如 `qwen3vl_8b_int8_convrot.safetensors`），且 `type` 选 `qwen_image`。

❌ **2560 维的模型不能直接作 TE**：任何 Qwen3-VL-**4B** 系列（含 abliterated 版）、纯 Qwen3-4B。

> 想用 4B 做"宽审核"扩词是可以的 —— 但只能作为**提示词改写器**产出文本，再把文本喂给 8B 编码，**不能替换 TE**。

---

## 坑 6 · 下拉里只有旧文件名 / 找不到新模型

ComfyUI 有文件夹列表缓存（TTL 很短，通常几秒），但**前端下拉**需要重新拉取元数据。

**解决**：

1. 重启 ComfyUI；
2. 浏览器 **Ctrl + F5** 硬刷新；
3. 确认文件扩展名是 `.gguf` 且落在 `models/diffusion_models/`（或 `unet/`）。

> 已有工作流里存的模型名是**字符串**。换文件名后，工作流不会自动跟着改 —— 需要手动在下拉里重选。这也是为什么建议修复后**另存新名**（`..._fixed.gguf`）而要记得回工作流改下拉。**排查"改了没用"时报错照旧，第一件事就是确认下拉里选的是哪个文件。**

---

## 附：一次完整排障的日志对照

| 阶段 | 日志关键行 | 含义 |
|---|---|---|
| 加载 | `gguf qtypes: BF16 (4), Q8_0 (293)` | 加载的是**缺陷原版** |
| 加载 | `gguf qtypes: BF16 (3), Q8_0 (229), F32 (65)` | 加载的是**修复版** ✅ |
| 加载 | `loaded partially; 5635.55 MB usable, 5582.88 MB loaded, 1785.00 MB offloaded` | 显存不足，走 offload，正常可继续 |
| 采样 | `0%\|   \| 0/20 [00:00<?, ?it/s]` | 采样启动 = `[136] vs [128]` 已彻底解决 |
| 完成 | `Prompt executed in 32.30 seconds` | 出图成功 |
