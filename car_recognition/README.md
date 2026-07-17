# 👤 人脸识别通信模块

Web 管理端 ↔ 小车端的人脸扫描指令转发工具。

## 文件

`face_commander.py` — 从 Web 端 TCP 发送人脸扫描指令到小车 `端口 6001`

## 协议（type=20）

```json
{
  "action": "face_scan",
  "order_id": 1,
  "recipient_name": "张明",
  "face_image_base64": "...",
  "classroom_no": "501"
}
```
