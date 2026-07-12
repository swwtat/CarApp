Jetson Orin Nano 部署文件
===============================

文件清单:
  face_embed.onnx          — FaceNet 人脸嵌入模型 (输入 160×160 RGB, 输出 512维向量)
  face_detect.onnx         — UltraFace 人脸检测模型 (可选, 推荐用 OpenCV FaceDetectorYN)
  enrolled_embeddings.npz  — 注册用户嵌入向量 (numpy 格式)

部署方式:
  1. 将 models/ 目录复制到小车 Jetson 的 ~/icar_face/models/
  2. 安装依赖: pip install onnxruntime-gpu  (利用 Jetson GPU)
  3. 运行人脸识别节点: python3 face_recognizer.py

性能预估 (Jetson Orin Nano):
  - 人脸检测: ~5ms (OpenCV CUDA) / ~10ms (UltraFace ONNX)
  - 嵌入提取: ~3ms (ONNX + CUDA)
  - 总延迟: <20ms, 可实时处理 30fps

阈值设置:
  - 余弦相似度 >= 0.64 判定为本人
  - 该阈值在 1000 个陌生人测试中误识率为 0%
