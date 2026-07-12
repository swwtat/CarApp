"""
人脸识别演示 — 直观展示"本人 vs 陌生人"的区分效果
=====================================================
每次运行随机抽取照片进行比对，显示相似度和判定结果。
"""

import os
import sys
import random
import numpy as np
from pathlib import Path

import torch
from facenet_pytorch import MTCNN, InceptionResnetV1
from PIL import Image

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
STRANGER_DIR = 'data/strangers'
ENROLLED_DIRS = ['../facedata/personA', '../facedata/personB']
THRESHOLD = 0.6378  # 来自训练结果

print(f"设备: {DEVICE}")
print("加载模型...")
mtcnn = MTCNN(image_size=160, margin=0, min_face_size=20, thresholds=[0.6, 0.7, 0.7],
              factor=0.709, post_process=True, device=DEVICE, keep_all=False)
resnet = InceptionResnetV1(pretrained='vggface2', classify=False, device=DEVICE).eval()

def get_embedding(image_path):
    """提取一张图片的人脸嵌入"""
    img = Image.open(image_path).convert('RGB')
    face = mtcnn(img)
    if face is None:
        return None
    with torch.no_grad():
        emb = resnet(face.unsqueeze(0).to(DEVICE))
    return emb.cpu().numpy().flatten()

def cos_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

# ===== 加载注册用户嵌入 =====
print("注册用户嵌入...")
enrolled = {}
for enroll_dir in ENROLLED_DIRS:
    name = os.path.basename(enroll_dir)
    base = Path(enroll_dir)
    files = list(base.glob('*.jpg')) + list(base.glob('*.png'))
    embs = []
    for f in files:
        emb = get_embedding(f)
        if emb is not None:
            embs.append(emb)
    if embs:
        enrolled[name] = {
            'centroid': np.mean(embs, axis=0),  # 平均嵌入作为"标准特征"
            'count': len(embs),
        }
        print(f"  {name}: {len(embs)} 张")

# ===== 随机演示 =====
print(f"\n{'='*60}")
print(f"  人脸识别演示 (阈值={THRESHOLD:.4f})")
print(f"{'='*60}")

# 演示场景
demos = []

# 场景1: 注册用户本人 (随机抽 personA 的图)
pa_files = list(Path('../facedata/personA').glob('*.jpg'))
pb_files = list(Path('../facedata/personB').glob('*.jpg'))
demo_pa = random.choice(pa_files)
demo_pb = random.choice(pb_files)

# 场景2: 陌生人 (随机抽)
stranger_files = list(Path(STRANGER_DIR).glob('*.jpg'))
demo_stranger1 = random.choice(stranger_files)
demo_stranger2 = random.choice(stranger_files)

demos = [
    ('personA 本人', demo_pa, 'personA'),
    ('personB 本人', demo_pb, 'personB'),
    ('陌生人 #1', demo_stranger1, None),
    ('陌生人 #2', demo_stranger2, None),
    ('personA → 冒充 personB', demo_pa, 'personB'),
    ('personB → 冒充 personA', demo_pb, 'personA'),
]

print(f"\n{'标号':<6} {'场景':<24} {'文件':<45} {'相似度':>8} {'结果':>6}")
print("-" * 95)

for i, (label, img_path, target) in enumerate(demos, 1):
    emb = get_embedding(img_path)
    if emb is None:
        print(f" [{i}]  {label:<22} {img_path.name:<43} {'N/A':>8} {'无脸':>6}")
        continue

    # 对每个注册用户计算相似度
    best_name = '-'
    best_sim = 0
    for name, info in enrolled.items():
        sim = cos_sim(emb, info['centroid'])
        if sim > best_sim:
            best_sim = sim
            best_name = name

    passed = best_sim >= THRESHOLD
    verdict = f"{best_name} PASS" if passed else "REJECT"
    correct = "OK" if (target and passed and best_name == target) or (target is None and not passed) else "!!"
    warn = "??" if (target is None and passed) else ""
    flag = warn if warn else correct

    print(f" [{i}]  {label:<22} {img_path.name:<43} {best_sim:>8.4f}  {verdict:<6} {flag}")

# ===== 统计演示 =====
print(f"\n{'='*60}")
print("  批量统计 (100 个随机样本)")
print(f"{'='*60}")

# 抽取 50 个注册用户样本 + 50 个陌生人样本
test_samples = []
all_enrolled_files = pa_files + pb_files
random.shuffle(all_enrolled_files)
random.shuffle(stranger_files)

for f in all_enrolled_files[:50]:
    test_samples.append((f, True))  # True = 应该通过
for f in stranger_files[:50]:
    test_samples.append((f, False))  # False = 应该拒绝

tp = fp = tn = fn = 0
for img_path, should_pass in test_samples:
    emb = get_embedding(img_path)
    if emb is None:
        continue
    best_sim = max(cos_sim(emb, info['centroid']) for _, info in enrolled.items())
    predicted_pass = best_sim >= THRESHOLD

    if should_pass and predicted_pass:
        tp += 1
    elif should_pass and not predicted_pass:
        fn += 1
    elif not should_pass and predicted_pass:
        fp += 1
    else:
        tn += 1

tar = tp / (tp + fn) if (tp + fn) > 0 else 0
far = fp / (fp + tn) if (fp + tn) > 0 else 0
acc = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0

print(f"  本人样本: {tp+fn}  陌生人样本: {fp+tn}")
print(f"  TAR (本人通过率): {tar:.1%}  ({tp}/{tp+fn})")
print(f"  FAR (陌生人误识): {far:.1%}  ({fp}/{fp+tn})")
print(f"  准确率:           {acc:.1%}  ({(tp+tn)}/{tp+fp+tn+fn})")

print(f"\n阈值线: {THRESHOLD:.4f}")
print(f"高于此值 → 识别为本人，允许操作")
print(f"低于此值 → 识别为陌生人，拒绝操作")
