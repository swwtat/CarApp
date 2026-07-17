# 🔍 人脸识别 — 训练 & 数据

人脸识别模型训练、评估、数据管理工具链。

## 目录

```
face_recognition/
├── data/
│   ├── enrolled/              注册用户照片
│   │   ├── personA/               收件人 A（11 张）
│   │   └── personB/               收件人 B（8 张）
│   └── strangers/              陌生人照片（负样本，200+ 张）
├── models/
│   ├── face_embed.onnx            人脸嵌入模型（93.9 MB）
│   └── enrolled_embeddings.npz    预计算特征向量
├── output/
│   ├── similarity_distribution.png  相似度分布图
│   └── threshold.txt                最优阈值（0.64, TAR=0.90）
├── demo.py                      演示脚本
├── verify_faces.py              验证基准测试
├── export_models.py             导出 ONNX 模型
└── download_stranger_dataset.py 下载陌生人数据集
```

## 使用

```bash
# 录入新用户 → 将照片放入 data/enrolled/<人名>/
# 提取嵌入
python export_models.py

# 标定阈值
python verify_faces.py
```
