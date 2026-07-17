# 🚦 YOLO 交通标志检测训练

训练小车识别转向标志（左转/右转/掉头）。

## 类别

- `turnleft` — 左转
- `turnright` — 右转
- `turnaround` — 掉头

## 文件

| 文件 | 说明 |
|------|------|
| `split_dataset.py` | 数据集拆分 (70% train / 15% val / 15% test) |
| `voc_traffic.yaml` | YOLOv5 数据配置 |
| `train.bat` | Windows 训练启动脚本 |
| `TRAFFIC/` | 标注数据存放目录 |

## 使用

```bash
# 1. 将图片和标注放入 TRAFFIC/images/ 和 TRAFFIC/labels/
# 2. 拆分数据集
python split_dataset.py

# 3. 训练
python train.py --data voc_traffic.yaml --epochs 100
```
