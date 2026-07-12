"""
下载 CASIA-WebFace 数据集并抽取陌生人样本
============================================
用途: 为人脸识别系统提供"陌生人"负面测试样本
      测试系统能否正确拒绝未注册的人脸

数据来源:
  CASIA-WebFace (对齐版 112×112) — 10,575 人 / ~49 万张
  Kaggle: https://www.kaggle.com/datasets/yakhyokhuja/webface-112x112

用法:
  python download_stranger_dataset.py

输出:
  face_recognition/data/strangers/   — 陌生人样本 (每人 1 张)
  face_recognition/data/enrolled/    — 注册用户目录 (你的自拍放这里)
"""

import os
import random
import shutil

random.seed(42)

# ===== 配置 =====
STRANGER_COUNT = 1000          # 抽取陌生人数量
SAMPLE_PER_PERSON = 1          # 每人取几张
OUTPUT_DIR = "data/strangers"  # 输出目录
DATASET_DIR = "data/casia_webface_raw"  # 原始数据集缓存

# ===== 步骤 1: 下载数据集 =====
print("=" * 50)
print("步骤 1/3: 下载 CASIA-WebFace 数据集...")
print("=" * 50)
print("首次下载约 2-4 GB，请耐心等待...\n")

try:
    import kagglehub
    raw_path = kagglehub.dataset_download("yakhyokhuja/webface-112x112")
    print(f"[OK] 下载完成 -> {raw_path}")
    # 如果下载目录下只有一个子文件夹，自动进入 (kagglehub 常见结构)
    sub_items = [d for d in os.listdir(raw_path) if os.path.isdir(os.path.join(raw_path, d))]
    if len(sub_items) == 1 and os.path.isdir(os.path.join(raw_path, sub_items[0])):
        raw_path = os.path.join(raw_path, sub_items[0])
        print(f"[INFO] 自动进入子目录 -> {raw_path}")
except Exception as e:
    print(f"\n[FAIL] 下载失败: {e}")
    print("\n备选方案:")
    print("  1. 手动下载: https://www.kaggle.com/datasets/yakhyokhuja/webface-112x112")
    print("  2. 解压后将文件夹路径作为参数传入: python download_stranger_dataset.py <路径>")
    exit(1)

# ===== 步骤 2: 了解数据结构 =====
print(f"\n{'='*50}")
print("步骤 2/3: 扫描数据集结构...")
print("=" * 50)

# CASIA-WebFace 对齐版结构: 每个身份一个文件夹
# webface-112x112/
#   ├── 0000045/    (身份 ID)
#   │   ├── 001.jpg
#   │   ├── 002.jpg
#   │   └── ...
#   ├── 0000099/
#   │   └── ...

identities = [
    d for d in os.listdir(raw_path)
    if os.path.isdir(os.path.join(raw_path, d))
]
print(f"总身份数: {len(identities)}")

# ===== 步骤 3: 随机抽取陌生人 =====
print(f"\n{'='*50}")
print(f"步骤 3/3: 抽取 {STRANGER_COUNT} 个陌生人...")
print("=" * 50)

strangers = random.sample(identities, min(STRANGER_COUNT, len(identities)))
os.makedirs(OUTPUT_DIR, exist_ok=True)

copied = 0
for pid in strangers:
    person_dir = os.path.join(raw_path, pid)
    images = [f for f in os.listdir(person_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if len(images) == 0:
        continue

    # 每人取 SAMPLE_PER_PERSON 张
    for img_file in images[:SAMPLE_PER_PERSON]:
        src = os.path.join(person_dir, img_file)
        dst = os.path.join(OUTPUT_DIR, f"{pid}_{img_file}")
        shutil.copy2(src, dst)
        copied += 1

print(f"\n[OK] 完成! 已抽取 {copied} 张陌生人样本 -> {os.path.abspath(OUTPUT_DIR)}")

# ===== 创建注册用户目录 =====
enrolled_dir = "data/enrolled"
os.makedirs(enrolled_dir, exist_ok=True)
readme_path = os.path.join(enrolled_dir, "README.txt")
if not os.path.exists(readme_path):
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("""注册用户照片存放说明
====================

将你的自拍照片放在这里，推荐:

  数量: 20-30 张
  角度: 正面、左偏、右偏、上仰、下俯
  光照: 室内光、室外光、暗光
  表情: 无表情、微笑
  配件: 戴眼镜/不戴眼镜 (如适用)
  格式: JPG 或 PNG
  人脸: 清晰可见，不要遮挡

文件结构:
  data/enrolled/
  ├── 001.jpg
  ├── 002.jpg
  └── ...
""")

print(f"[OK] 注册用户目录已创建 -> {os.path.abspath(enrolled_dir)}")
print("   请将你的自拍照片放入该目录 (20-30 张)")

# ===== 目录结构说明 =====
print(f"""
{'='*50}
目录结构:
  face_recognition/
  ├── download_stranger_dataset.py   (本脚本)
  └── data/
      ├── strangers/                 ← {copied} 张陌生人脸 (负面样本)
      └── enrolled/                  ← 你的自拍放这里 (正面样本)

下一步:
  1. 把你的 20-30 张自拍放入 data/enrolled/
  2. 运行 face recognition 验证脚本
{'='*50}
""")
