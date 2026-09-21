# ComfyUI-GGUF 适配补丁说明

## 为什么需要补丁

`abenzerps/Qwen-Image-2.1-Uncensored-GGUF` 发布时**剥离了 GGUF 的业务元数据** —— 文件里只剩 GGUF 骨架字段：

```
['GGUF.version', 'GGUF.tensor_count', 'GGUF.kv_count']
```

正常的 GGUF 应该还有 `general.architecture` / `general.file_type` / `general.quantization_version`。

缺失后，`UnetLoaderGGUF` 只能走 `tools/convert.py` 的 `detect_arch()` 兜底逻辑，靠**张量名的特征**猜架构；而 `city96/ComfyUI-GGUF` 的 `arch_list` 里**没有 Qwen**，于是：

```
This model is not currently supported - (Unknown model architecture!)
```

## 补丁内容

### `qwen_image21_arch.patch` → `tools/convert.py`

新增架构类（**照抄自 `leejet/ComfyUI-GGUF`**，该分支已原生支持 Qwen-Image 2.1）：

```python
class QwenImage21(ModelTemplate):
    arch = "qwen_image21"
    keys_detect = [
        ("txt_in.text_norm.weight",)
    ]
```

并把 `QwenImage21` 追加进模块级 `arch_list`。

### `qwen_image21_loader.patch` → `loader.py`

把 `"qwen_image21"` 加进 `IMG_ARCH_LIST`。

## 应用方法

```bash
cd <ComfyUI>/custom_nodes/ComfyUI-GGUF
patch -p1 < <本仓库>/patches/qwen_image21_arch.patch
patch -p1 < <本仓库>/patches/qwen_image21_loader.patch
```

打之前先备份：

```bash
cp tools/convert.py tools/convert.py.bak
cp loader.py        loader.py.bak
```

或者干脆手改 —— 改动很小，直接在 `convert.py` 里找到 `arch_list = [...]` 往上插类、往下追加类名即可。

## 🚨 如果打补丁不生效：多副本问题

**这是最容易白干一轮的坑。** 如果启动日志里同一个节点包出现多次：

```
[INFO] 0.0 seconds: <A>/ComfyUI/custom_nodes/ComfyUI-GGUF
[INFO] 0.0 seconds: <B>/CustomNodes/CustomNodes-TorI2V/ComfyUI-GGUF
[INFO] 0.0 seconds: <B>/CustomNodes/CustomNodes-TorI2V/ComfyUI-GGUF-molbal
```

ComfyUI 是**并行加载**这些包的，最后用 `NODE_CLASS_MAPPINGS` 合并同名类 —— **哪一份生效不确定**，不一定是最后打印的那份。

**定位真正生效的那份**：看报错 traceback 里的文件路径。

```
File "...\CustomNodes-TorI2V\ComfyUI-GGUF\tools\convert.py", line 169, in detect_arch
```

→ 那就是生效副本。

**处置**：把同样的补丁**打到所有副本上**（不动配置、不改名、可回滚，最稳）。

### Windows 下枚举进程（避开 `%` 通配，会被安全过滤误判）

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*ComfyUI*' } |
  Select-Object ProcessId, CommandLine
```

## 验证补丁是否生效（不用重启）

```python
import importlib.util
spec = importlib.util.spec_from_file_location('gc', r'<...>/ComfyUI-GGUF/tools/convert.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.detect_arch(tensor_names).arch)   # 期望输出 qwen_image21
```

或者直接看启动后的加载日志，出现下面这行即代表架构识别成功：

```
[INFO] gguf qtypes: BF16 (3), Q8_0 (229), F32 (65)
[INFO] model weight dtype torch.bfloat16, manual cast: None
```

> 注：日志里可能同时出现 `Warning: This gguf model file is loaded in compatibility mode 'sd.cpp' [arch:qwen_image21]` —— 这是提示走了兼容加载路径，**不影响正确性**。

## 何时不需要补丁

如果你直接使用 **`leejet/ComfyUI-GGUF`**（已内置 `QwenImage21` 架构类），则**无需任何补丁**。

## 回滚

```bash
cp tools/convert.py.bak tools/convert.py
cp loader.py.bak        loader.py
```

然后重启 ComfyUI。
