# 🔍 人脸识别数据 & 模型

## 目录

| 目录 | 说明 |
|------|------|
| `data/enrolled/` | 注册用户照片（每人 20-30 张，多角度多光照）|
| `data/strangers/` | 陌生人照片（负样本，含 LFW 子集）|
| `models/` | ONNX 推理模型 + 注册用户嵌入向量 |
| `output/` | 相似度阈值分析结果 |

## 模型文件

| 文件 | 说明 |
|------|------|
| `face_embed.onnx` | SFace 人脸嵌入模型 (0.7 MB) |
| `enrolled_embeddings.npz` | 已注册用户的预计算特征向量 |

## 录入新用户

将自拍照片放入 `data/enrolled/`，运行嵌入提取脚本更新 `enrolled_embeddings.npz`。
