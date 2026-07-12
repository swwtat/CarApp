"""
人脸验证脚本 — 评估注册用户 vs 陌生人的区分能力
==================================================
用法:
  python verify_faces.py

前提:
  1. data/strangers/  — CASIA-WebFace 陌生人样本 (1000张)
  2. ../facedata/     — 注册用户自拍 (personA/, personB/)

输出:
  - 相似度分布图 (similarity_distribution.png)
  - 最佳阈值、TAR、FAR 指标
  - ROC 曲线
"""

import os
import sys
import numpy as np
from pathlib import Path

import torch
from facenet_pytorch import MTCNN, InceptionResnetV1
from PIL import Image
from sklearn.metrics import roc_curve, auc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ===== 配置 =====
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
STRANGER_DIR = 'data/strangers'
ENROLLED_DIRS = ['../facedata/personA', '../facedata/personB']
OUTPUT_DIR = 'output'
THRESHOLD_STEP = 50  # 阈值搜索步数

print(f"设备: {DEVICE}")
print(f"陌生人目录: {STRANGER_DIR}")
print(f"注册用户: {[os.path.basename(d) for d in ENROLLED_DIRS]}")

# ===== 步骤 1: 初始化模型 =====
print("\n[1/4] 加载模型...")
mtcnn = MTCNN(
    image_size=160,    # FaceNet 要求的输入尺寸
    margin=0,
    min_face_size=20,
    thresholds=[0.6, 0.7, 0.7],
    factor=0.709,
    post_process=True,
    device=DEVICE,
    keep_all=False,    # 每张图只取置信度最高的人脸
)

resnet = InceptionResnetV1(
    pretrained='vggface2',
    classify=False,    # 输出 embedding，不分类
    device=DEVICE,
).eval()

# ===== 步骤 2: 提取所有嵌入向量 =====
def extract_embeddings(image_dir, label_name):
    """从目录提取所有人脸的嵌入向量"""
    base = Path(image_dir)
    if not base.exists():
        print(f"  [WARN] 目录不存在: {image_dir}")
        return np.array([]), []

    files = sorted([f for f in base.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp')])
    if not files:
        print(f"  [WARN] 无图片: {image_dir}")
        return np.array([]), []

    embeddings = []
    valid_files = []
    failed = 0

    for f in files:
        try:
            img = Image.open(f).convert('RGB')
            face = mtcnn(img)  # 返回 tensor (1, 3, 160, 160) 或 None
            if face is None:
                failed += 1
                continue
            with torch.no_grad():
                emb = resnet(face.unsqueeze(0).to(DEVICE))
            embeddings.append(emb.cpu().numpy().flatten())
            valid_files.append(str(f))
        except Exception as e:
            failed += 1

    embs = np.array(embeddings) if embeddings else np.array([])
    print(f"  {label_name}: {len(embeddings)} 张成功, {failed} 张检测不到人脸")

    return embs, valid_files

print("\n[2/4] 提取嵌入向量...")

# 注册用户
enrolled_embs = {}
enrolled_labels = []
all_enrolled_embs = []
for enroll_dir in ENROLLED_DIRS:
    name = os.path.basename(enroll_dir)
    embs, files = extract_embeddings(enroll_dir, name)
    if len(embs) > 0:
        enrolled_embs[name] = embs
        enrolled_labels.extend([name] * len(embs))
        all_enrolled_embs.append(embs)

# 合并所有注册用户
if all_enrolled_embs:
    all_enrolled = np.vstack(all_enrolled_embs)
else:
    print("\n[FAIL] 没有检测到任何注册用户的人脸!")
    print("请确认 facedata/personA/ 和 facedata/personB/ 中有清晰的人脸照片")
    sys.exit(1)

# 陌生人
stranger_embs, stranger_files = extract_embeddings(STRANGER_DIR, "陌生人")

if len(stranger_embs) == 0:
    print("\n[FAIL] 没有检测到任何陌生人的人脸!")
    sys.exit(1)

# ===== 步骤 3: 计算相似度矩阵 =====
print("\n[3/4] 计算相似度...")

def cosine_similarity(a, b):
    """余弦相似度, [0, 1]"""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(a_norm, b_norm.T)

def euclidean_distance(a, b):
    """欧氏距离"""
    return np.linalg.norm(a[:, np.newaxis] - b, axis=2)

# 注册用户之间的相似度 (同一人)
intra_similarities = []  # 同一人的相似度
inter_similarities = []  # 不同注册用户之间的相似度

for name, embs in enrolled_embs.items():
    if len(embs) >= 2:
        sim_matrix = cosine_similarity(embs, embs)
        # 取上三角 (排除自己和自己的比较)
        n = len(embs)
        for i in range(n):
            for j in range(i + 1, n):
                intra_similarities.append(sim_matrix[i, j])

# 不同注册用户之间的相似度
enrolled_names = list(enrolled_embs.keys())
for i in range(len(enrolled_names)):
    for j in range(i + 1, len(enrolled_names)):
        sim_matrix = cosine_similarity(
            enrolled_embs[enrolled_names[i]],
            enrolled_embs[enrolled_names[j]]
        )
        inter_similarities.extend(sim_matrix.flatten().tolist())

# 注册用户 vs 陌生人 (负样本)
enrolled_vs_stranger = []
for name, embs in enrolled_embs.items():
    sim_matrix = cosine_similarity(embs, stranger_embs)
    enrolled_vs_stranger.extend(sim_matrix.flatten().tolist())

intra_similarities = np.array(intra_similarities)
inter_similarities = np.array(inter_similarities)
enrolled_vs_stranger = np.array(enrolled_vs_stranger)

print(f"  同一人配对 (正样本): {len(intra_similarities)} 对")
print(f"  不同注册用户: {len(inter_similarities)} 对")
print(f"  注册用户 vs 陌生人 (负样本): {len(enrolled_vs_stranger)} 对")

# ===== 步骤 4: 评估指标 =====
print("\n[4/4] 评估...")

# 负样本 = 不同注册用户 + 陌生人
negative_samples = np.concatenate([inter_similarities, enrolled_vs_stranger])
if len(intra_similarities) == 0:
    print("\n[SKIP] 同一人的样本不足 (每人至少2张照片才能计算配对)")
    sys.exit(0)

# 标签: 1=同一人(应该通过), 0=不同人(应该拒绝)
labels = np.concatenate([
    np.ones(len(intra_similarities)),
    np.zeros(len(negative_samples)),
])
scores = np.concatenate([intra_similarities, negative_samples])

# 寻找最佳阈值 (最大化 F1 或 Youden 指数)
best_threshold = 0.5
best_f1 = 0

for threshold in np.linspace(0.1, 0.95, THRESHOLD_STEP):
    pred_pos = scores >= threshold
    tp = np.sum((pred_pos == 1) & (labels == 1))
    fp = np.sum((pred_pos == 1) & (labels == 0))
    fn = np.sum((pred_pos == 0) & (labels == 1))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    if f1 > best_f1:
        best_f1 = f1
        best_threshold = threshold

# 用最佳阈值计算最终指标
pred_pos = scores >= best_threshold
tp = np.sum((pred_pos == 1) & (labels == 1))
fp = np.sum((pred_pos == 1) & (labels == 0))
tn = np.sum((pred_pos == 0) & (labels == 0))
fn = np.sum((pred_pos == 0) & (labels == 1))

tar = tp / (tp + fn) if (tp + fn) > 0 else 0  # True Accept Rate
far = fp / (fp + tn) if (fp + tn) > 0 else 0  # False Accept Rate
accuracy = (tp + tn) / len(labels)

print(f"\n{'='*50}")
print(f"  评估结果 (余弦相似度)")
print(f"{'='*50}")
print(f"  最佳阈值:           {best_threshold:.4f}")
print(f"  TAR (本人通过率):   {tar:.2%}")
print(f"  FAR (陌生人误识率): {far:.2%}")
print(f"  准确率:            {accuracy:.2%}")
print(f"  同一人平均相似度:   {np.mean(intra_similarities):.4f} ± {np.std(intra_similarities):.4f}")
print(f"  陌生人平均相似度:   {np.mean(negative_samples):.4f} ± {np.std(negative_samples):.4f}")
print(f"{'='*50}")

# ===== 输出目录 =====
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 保存阈值到文件
with open(os.path.join(OUTPUT_DIR, 'threshold.txt'), 'w') as f:
    f.write(f"best_threshold={best_threshold:.4f}\n")
    f.write(f"tar={tar:.4f}\n")
    f.write(f"far={far:.4f}\n")
    f.write(f"accuracy={accuracy:.4f}\n")
    f.write(f"intra_mean={np.mean(intra_similarities):.4f}\n")
    f.write(f"intra_std={np.std(intra_similarities):.4f}\n")
    f.write(f"inter_mean={np.mean(negative_samples):.4f}\n")
    f.write(f"inter_std={np.std(negative_samples):.4f}\n")

# ===== 可视化 =====
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# 相似度分布
ax1 = axes[0, 0]
ax1.hist(intra_similarities, bins=30, alpha=0.6, label=f'同一人 (n={len(intra_similarities)})', color='green', edgecolor='black')
ax1.hist(negative_samples, bins=30, alpha=0.6, label=f'不同人 (n={len(negative_samples)})', color='red', edgecolor='black')
ax1.axvline(best_threshold, color='blue', linestyle='--', linewidth=2, label=f'最佳阈值={best_threshold:.3f}')
ax1.set_xlabel('余弦相似度')
ax1.set_ylabel('频次')
ax1.set_title('相似度分布')
ax1.legend()

# 散点图 (注册用户内 vs 陌生人)
ax2 = axes[0, 1]
n_intra = len(intra_similarities)
n_neg = len(negative_samples)
max_plot = min(200, max(n_intra, n_neg))
rng = np.random.RandomState(42)
idx_intra = rng.choice(n_intra, min(max_plot, n_intra), replace=False) if n_intra > 0 else []
idx_neg = rng.choice(n_neg, min(max_plot, n_neg), replace=False) if n_neg > 0 else []
ax2.scatter(range(len(idx_intra)), np.sort(intra_similarities[idx_intra]) if len(idx_intra) > 0 else [],
            alpha=0.5, s=10, label='同一人', color='green')
ax2.scatter(range(len(idx_neg)), np.sort(negative_samples[idx_neg]) if len(idx_neg) > 0 else [],
            alpha=0.5, s=10, label='不同人', color='red')
ax2.axhline(best_threshold, color='blue', linestyle='--', linewidth=1.5)
ax2.set_xlabel('样本编号')
ax2.set_ylabel('余弦相似度')
ax2.set_title('排序相似度分布')
ax2.legend()

# ROC 曲线
ax3 = axes[1, 0]
fpr, tpr, thresholds = roc_curve(labels, scores)
roc_auc = auc(fpr, tpr)
ax3.plot(fpr, tpr, 'b-', linewidth=2, label=f'ROC (AUC={roc_auc:.3f})')
ax3.plot([0, 1], [0, 1], 'k--', alpha=0.3)
ax3.set_xlabel('FAR (陌生人误识率)')
ax3.set_ylabel('TAR (本人通过率)')
ax3.set_title('ROC 曲线')
ax3.legend()
ax3.grid(True, alpha=0.3)

# 摘要
ax4 = axes[1, 1]
ax4.axis('off')
summary_text = f"""
验证结果摘要
============

模型: InceptionResnetV1 (FaceNet)
      预训练数据: VGGFace2

注册用户: {len(enrolled_embs)} 人
陌生人:   {len(stranger_embs)} 人

-----------------------
注册用户配对 (同一人):
  {len(intra_similarities)} 对
  均值: {np.mean(intra_similarities):.4f}
  标准差: {np.std(intra_similarities):.4f}

陌生人配对 (不同人):
  {len(negative_samples)} 对
  均值: {np.mean(negative_samples):.4f}
  标准差: {np.std(negative_samples):.4f}

-----------------------
最佳余弦相似度阈值:
  {best_threshold:.4f}

TAR (本人通过率):
  {tar:.2%}  ({tp}/{tp+fn})

FAR (陌生人误识率):
  {far:.2%}  ({fp}/{fp+tn})

准确率: {accuracy:.2%}
"""
ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes,
         fontsize=10, verticalalignment='top', fontfamily='monospace',
         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
output_png = os.path.join(OUTPUT_DIR, 'similarity_distribution.png')
plt.savefig(output_png, dpi=150, bbox_inches='tight')
print(f"\n图表已保存 -> {os.path.abspath(output_png)}")

# ===== 个人级别统计 =====
print(f"\n---- 个人级别统计 ----")
for name, embs in enrolled_embs.items():
    sim_matrix = cosine_similarity(embs, stranger_embs)
    avg_sim = np.mean(sim_matrix)
    max_sim = np.max(sim_matrix)
    false_accepts = np.sum(sim_matrix >= best_threshold)
    print(f"  {name}: 与陌生人平均相似度={avg_sim:.4f}, 最大={max_sim:.4f}, 误识={false_accepts}/{len(stranger_embs)}")

print(f"\n全部完成! 输出目录: {os.path.abspath(OUTPUT_DIR)}")
