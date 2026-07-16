# 去水印批量工具

裁剪底部水印区域，无需 AI，纯 Python + PIL 实现。

## 适用场景

去除图片右下角「豆包AI生成」水印。水印位于底部边缘的留白区域，裁剪底部 150px 即可完全去除，不影响主体内容。

## 快速开始

### 方法一：GUI 版

```bash
python watermark_remover_simple.py
```

### 方法二：Web 版（推荐批量处理）

```bash
# 双击 启动工具.bat，或运行：
python server.py
```

浏览器打开 http://localhost:7890

### 方法三：命令行批量

```python
from watermark_remover_simple import remove_watermark, DEFAULT_CONFIG
from PIL import Image

img = Image.open("input.png")
result = remove_watermark(img, DEFAULT_CONFIG)
result.save("output_nowm.png")
```

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `watermark_height` | 150 | 底部裁剪高度（像素） |

## 原理

水印「豆包AI生成」位于图片右下角，距离底部约 0-30px，高度约 90-130px。
裁剪底部 150px 可完全去除水印区域。

对于竖构图图片（如 1600x2848），底部 150px 通常是背景/留白，裁剪不影响主体。

## 输出

- 默认后缀：`_nowm`（如 `image_nowm.png`）
- 支持 PNG 和 JPEG 输出
- 配置自动保存（localStorage）

## 技术栈

- Python 3 + Pillow (PIL)
- 纯本地处理，无需 GPU、无需网络
