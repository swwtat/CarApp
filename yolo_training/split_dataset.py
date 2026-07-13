"""
数据集拆分脚本 — 将完整数据集拆分为训练集 / 验证集 / 测试集
来源: 第6章 PDF 2 (机器人目标检测模型训练)

用法:
    python split_dataset.py

输入: TRAFFIC/images/, TRAFFIC/labels/
输出: traffic_dataset/train/, valid/, test/
"""

import os
import random
import shutil

# 设置随机数种子 (可复现)
random.seed(123)

# ===== 配置 =====
root_dir = 'TRAFFIC'
image_dir = os.path.join(root_dir, 'images')
label_dir = os.path.join(root_dir, 'labels')
output_dir = 'traffic_dataset'

# 拆分比例: 训练 70% / 验证 15% / 测试 15%
train_ratio = 0.7
valid_ratio = 0.15
test_ratio = 0.15

# ===== 获取文件名 =====
image_filenames = [os.path.splitext(f)[0] for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp'))]
label_filenames = [os.path.splitext(f)[0] for f in os.listdir(label_dir) if f.endswith('.txt')]

# 只保留同时有图片和标注的文件
valid_filenames = sorted(set(image_filenames) & set(label_filenames))
print(f"图片总数: {len(image_filenames)}")
print(f"标注总数: {len(label_filenames)}")
print(f"匹配有效数据: {len(valid_filenames)}")

if len(valid_filenames) == 0:
    print("❌ 错误: 没有找到同时有图片和标注的数据!")
    print(f"   请确认图片放在 {os.path.abspath(image_dir)}/")
    print(f"   标注文件放在 {os.path.abspath(label_dir)}/")
    exit(1)

if len(valid_filenames) < len(image_filenames):
    print(f"⚠️  警告: {len(image_filenames) - len(valid_filenames)} 张图片缺少对应标注")
if len(valid_filenames) < len(label_filenames):
    print(f"⚠️  警告: {len(label_filenames) - len(valid_filenames)} 个标注缺少对应图片")

# ===== 随机打乱 =====
random.shuffle(valid_filenames)

# ===== 计算数量 =====
total_count = len(valid_filenames)
train_count = int(total_count * train_ratio)
valid_count = int(total_count * valid_ratio)
test_count = total_count - train_count - valid_count

print(f"\n拆分结果:")
print(f"  训练集 (train): {train_count} 张 ({train_ratio*100:.0f}%)")
print(f"  验证集 (valid): {valid_count} 张 ({valid_ratio*100:.0f}%)")
print(f"  测试集 (test):  {test_count} 张 ({test_ratio*100:.0f}%)")

# ===== 定义输出路径 =====
subsets = {
    'train': (os.path.join(output_dir, 'train', 'images'), os.path.join(output_dir, 'train', 'labels')),
    'valid': (os.path.join(output_dir, 'valid', 'images'), os.path.join(output_dir, 'valid', 'labels')),
    'test':  (os.path.join(output_dir, 'test', 'images'), os.path.join(output_dir, 'test', 'labels')),
}

# ===== 创建输出目录 =====
for img_dir, lbl_dir in subsets.values():
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

# ===== 复制文件 =====
for i, filename in enumerate(valid_filenames):
    # 自动检测图片后缀
    img_src = None
    for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.JPG', '.JPEG', '.PNG']:
        candidate = os.path.join(image_dir, filename + ext)
        if os.path.exists(candidate):
            img_src = candidate
            break
    if img_src is None:
        print(f"⚠️  跳过 {filename}: 找不到图片文件")
        continue

    label_src = os.path.join(label_dir, filename + '.txt')

    if i < train_count:
        subset = 'train'
    elif i < train_count + valid_count:
        subset = 'valid'
    else:
        subset = 'test'

    img_dst_dir, lbl_dst_dir = subsets[subset]

    # 复制图片
    ext = os.path.splitext(img_src)[1]
    shutil.copy2(img_src, os.path.join(img_dst_dir, filename + ext))
    # 复制标注
    shutil.copy2(label_src, os.path.join(lbl_dst_dir, filename + '.txt'))

print(f"\n✅ 数据集拆分完成 → {os.path.abspath(output_dir)}/")

# 如果有 classes.txt，也复制过去
classes_src = os.path.join(root_dir, 'classes.txt')
if os.path.exists(classes_src):
    for _, (img_dir, _) in subsets.items():
        shutil.copy2(classes_src, os.path.join(os.path.dirname(img_dir), 'classes.txt'))
    print("✅ classes.txt 已复制到各子集目录")
