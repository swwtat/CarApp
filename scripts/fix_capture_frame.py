#!/usr/bin/env python3
"""修复 rosmaster_main.py - 在 mode_handle 前插入 capture_frame 方法"""

import shutil

path = "/home/jetson/Rosmaster-App/rosmaster/rosmaster_main.py"
backup = path + ".bak"

# 备份
shutil.copy(path, backup)
print(f"Backup saved: {backup}")

with open(path, "r") as f:
    lines = f.readlines()

# 精确格式化的 capture_frame 方法（4空格缩进，与 mode_handle 对齐）
method = [
    "    def capture_frame(self):\n",
    "        import cv2 as cv\n",
    "        if self.g_camera_type == self.g_camera.TYPE_USB_CAMERA:\n",
    "            success, frame = self.g_camera_usb.get_frame()\n",
    "        elif self.g_camera_type == self.g_camera.TYPE_WIDE_ANGLE_CAMERA:\n",
    "            success, frame = self.g_camera_wide_angle.get_frame()\n",
    "        else:\n",
    "            success, frame = self.g_camera.get_frame()\n",
    "        if not success:\n",
    "            return False, None\n",
    "        _, jpg = cv.imencode('.jpg', frame, [cv.IMWRITE_JPEG_QUALITY, 80])\n",
    "        return True, jpg.tobytes()\n",
]

# 删除旧的错误 capture_frame（如果存在）
start_sig = "def capture_frame(self):"
end_sig = "def mode_handle(self):"

new_lines = []
skip_old = False
for i, line in enumerate(lines):
    stripped = line.rstrip()
    if stripped.endswith(start_sig) or (skip_old and not stripped.endswith(end_sig)):
        skip_old = True
        continue
    if skip_old and stripped.endswith(end_sig):
        skip_old = False
        new_lines.append("\n")
        new_lines.extend(method)
        new_lines.append("\n")
        new_lines.append(line)
        continue
    new_lines.append(line)

with open(path, "w") as f:
    f.writelines(new_lines)

# 验证
with open(path, "r") as f:
    content = f.read()

if "def capture_frame(self):" in content and "def mode_handle(self):" in content:
    print("OK: capture_frame inserted successfully")
else:
    print("ERROR: insertion failed")
