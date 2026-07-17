# 🎥 小车相机 & 部署脚本

## 文件

| 文件 | 说明 |
|------|------|
| `camera_stream_server.py` | MJPEG HTTP 流服务 — `/stream` 实时画面、`/capture` 单帧抓取、`/photo` 拍照 |
| `cam.py` | 简化版相机服务，读 `/dev/camera_depth` |
| `fix_capture_frame.py` | 向 `rosmaster_main.py` 注入 `capture_frame()` 方法 |

## 使用

```bash
# 启动相机流 (端口 8080)
python3 camera_stream_server.py

# APP 端访问
http://<小车IP>:8080/stream   # 实时画面
http://<小车IP>:8080/capture  # 单帧抓取
```
