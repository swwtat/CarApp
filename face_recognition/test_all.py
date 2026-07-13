"""
人脸识别系统 — 综合测试
=======================
测试覆盖:
  1. ONNX 模型加载
  2. 人脸检测 (MTCNN)
  3. 嵌入提取 + 比对
  4. 注册用户验证
  5. 陌生人拒识
  6. 性能基准 (fps)

用法:
  python test_all.py             # 快速测试
  python test_all.py --full      # 完整测试 (含陌生人 999 张)
  python test_all.py --image <路径>  # 单张图片测试
"""

import os, sys, time, base64, json, argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1
import onnxruntime as ort

# ── 配置 ──
MODEL_DIR = Path('models')
STRANGER_DIR = Path('data/strangers')
FACEDATA_DIR = Path('../facedata')
THRESHOLD = 0.64

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
passed = 0
failed = 0

def check(msg, condition):
    """断言并计数"""
    global passed, failed
    status = 'OK' if condition else 'FAIL'
    if condition:
        passed += 1
    else:
        failed += 1
    print(f"  [{status}] {msg}")

def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

# ===== 加载模型 =====
section('测试 1: 加载模型')

# PyTorch 模型
print("  加载 MTCNN...")
mtcnn = MTCNN(image_size=160, margin=0, min_face_size=20,
              thresholds=[0.6, 0.7, 0.7], factor=0.709,
              post_process=True, device=DEVICE, keep_all=False)
print("  加载 FaceNet...")
resnet = InceptionResnetV1(pretrained='vggface2', classify=False, device=DEVICE).eval()

check('MTCNN 加载成功', mtcnn is not None)
check('FaceNet 加载成功', resnet is not None)

# ONNX 模型
onnx_path = MODEL_DIR / 'face_embed.onnx'
if onnx_path.exists():
    session = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])
    check(f'ONNX 模型加载 ({onnx_path.stat().st_size/1024:.0f}KB)', True)
else:
    check(f'ONNX 模型不存在: {onnx_path}', False)
    session = None

# ===== 人脸检测测试 =====
section('测试 2: 人脸检测 (MTCNN)')

# 测试 facedata 中的图片
for person_dir in sorted(FACEDATA_DIR.glob('person*')):
    if not person_dir.is_dir():
        continue
    images = list(person_dir.glob('*.jpg'))
    detected = 0
    for img_path in images:
        try:
            img = Image.open(img_path).convert('RGB')
            face = mtcnn(img)
            if face is not None:
                detected += 1
        except Exception:
            pass
    rate = detected / len(images) * 100 if images else 0
    check(f'{person_dir.name}: {detected}/{len(images)} 张检测到人脸 ({rate:.0f}%)', rate >= 70)

# 测试陌生人
stranger_images = sorted(STRANGER_DIR.glob('*.jpg'))[:5]
stranger_detected = 0
for img_path in stranger_images:
    try:
        img = Image.open(img_path).convert('RGB')
        face = mtcnn(img)
        if face is not None:
            stranger_detected += 1
    except Exception:
        pass
check(f'陌生人样本: {stranger_detected}/{len(stranger_images)} 张检测到人脸', stranger_detected >= 3)

# ===== 嵌入提取测试 =====
section('测试 3: 嵌入提取 + 比对')

# 提取张明和李芳的嵌入向量
def get_enrolled_embeddings():
    """从 facedata 提取注册用户嵌入"""
    enrolled = {}
    for person_dir in sorted(FACEDATA_DIR.glob('person*')):
        if not person_dir.is_dir():
            continue
        mapping = {'personA': '张明', 'personB': '李芳'}
        name = mapping.get(person_dir.name, person_dir.name)
        embs = []
        for img_path in sorted(person_dir.glob('*.jpg')):
            try:
                img = Image.open(img_path).convert('RGB')
                face = mtcnn(img)
                if face is not None:
                    with torch.no_grad():
                        emb = resnet(face.unsqueeze(0).to(DEVICE))
                    embs.append(emb.cpu().numpy().flatten())
            except Exception:
                pass
        if embs:
            enrolled[name] = {
                'centroid': np.mean(embs, axis=0),
                'count': len(embs),
            }
    return enrolled

enrolled = get_enrolled_embeddings()
for name, info in enrolled.items():
    check(f'{name}: {info["count"]} 张嵌入提取成功', info['count'] >= 5)

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

# 同一人测试
for name, info in enrolled.items():
    centroid = info['centroid']
    intra_sims = []
    # 重新提取每张图的嵌入并与 centroid 比对
    person_dir = {'张明': 'personA', '李芳': 'personB'}.get(name)
    if not person_dir:
        continue
    for img_path in sorted((FACEDATA_DIR / person_dir).glob('*.jpg'))[:5]:
        try:
            img = Image.open(img_path).convert('RGB')
            face = mtcnn(img)
            if face is not None:
                with torch.no_grad():
                    emb = resnet(face.unsqueeze(0).to(DEVICE)).cpu().numpy().flatten()
                intra_sims.append(cosine_sim(emb, centroid))
        except Exception:
            pass
    if intra_sims:
        avg_sim = np.mean(intra_sims)
        all_above = all(s >= THRESHOLD for s in intra_sims)
        check(f'{name} 本人验证: avg sim={avg_sim:.4f} (阈值={THRESHOLD})', all_above)

# 不同人测试 (张明 vs 李芳)
if '张明' in enrolled and '李芳' in enrolled:
    cross_sim = cosine_sim(enrolled['张明']['centroid'], enrolled['李芳']['centroid'])
    check(f'张明 vs 李芳: sim={cross_sim:.4f} (应 < {THRESHOLD})', cross_sim < THRESHOLD)

# ===== ONNX 与 PyTorch 一致性测试 =====
if session is not None:
    section('测试 4: ONNX vs PyTorch 一致性')
    img_path = sorted(FACEDATA_DIR.glob('personA/*.jpg'))[0]
    img = Image.open(img_path).convert('RGB')
    face = mtcnn(img)

    if face is not None:
        # PyTorch 推理
        with torch.no_grad():
            pt_emb = resnet(face.unsqueeze(0).to(DEVICE)).cpu().numpy().flatten()

        # ONNX 推理 (MTCNN post_process=True 已输出 [-1,1], 只需加 batch 维度)
        face_np = face.numpy()  # shape: (3, 160, 160), 值域 [-1, 1]
        face_np = np.expand_dims(face_np, axis=0)  # -> (1, 3, 160, 160)
        ort_input = {session.get_inputs()[0].name: face_np}
        onnx_emb = session.run(None, ort_input)[0].flatten()

        diff = np.abs(pt_emb - onnx_emb).max()
        check(f'ONNX/PyTorch 最大误差: {diff:.8f} (应 < 0.001)', diff < 0.001)

        sim_pt = cosine_sim(pt_emb, enrolled['张明']['centroid'])
        sim_onnx = cosine_sim(onnx_emb, enrolled['张明']['centroid'])
        check(f'PyTorch sim={sim_pt:.4f}, ONNX sim={sim_onnx:.4f} (应接近)', abs(sim_pt - sim_onnx) < 0.01)
    else:
        check('MTCNN 未检测到人脸，跳过', False)

# ===== 陌生人拒识测试 =====
section('测试 5: 陌生人拒识')

stranger_count = 50  # 快速测试
stranger_embs = []
stranger_files_used = []
for img_path in sorted(STRANGER_DIR.glob('*.jpg'))[:stranger_count]:
    try:
        img = Image.open(img_path).convert('RGB')
        face = mtcnn(img)
        if face is not None:
            with torch.no_grad():
                emb = resnet(face.unsqueeze(0).to(DEVICE)).cpu().numpy().flatten()
            stranger_embs.append(emb)
            stranger_files_used.append(img_path)
    except Exception:
        pass

false_accepts = 0
for emb in stranger_embs:
    best_sim = max(cosine_sim(emb, info['centroid']) for _, info in enrolled.items())
    if best_sim >= THRESHOLD:
        false_accepts += 1

far = false_accepts / len(stranger_embs) * 100 if stranger_embs else 0
check(f'陌生人测试: {false_accepts}/{len(stranger_embs)} 误识 (FAR={far:.1f}%)', far < 5)

# 打印最像的陌生人 (接近误识的那张)
all_sims = []
for i, emb in enumerate(stranger_embs):
    best = max((cosine_sim(emb, info['centroid']), name) for name, info in enrolled.items())
    all_sims.append((best[0], str(stranger_files_used[i].name), best[1]))
all_sims.sort(reverse=True)
if all_sims:
    top = all_sims[0]
    print(f"  最接近的陌生人: {top[1]} sim={top[0]:.4f} 匹配到={top[2]}")

# ===== 性能基准 =====
section('测试 6: 性能基准')

# MTCNN 检测速度
test_img = Image.open(FACEDATA_DIR / 'personA' / sorted(os.listdir(FACEDATA_DIR / 'personA'))[0]).convert('RGB')
times_detect = []
for _ in range(10):
    t0 = time.time()
    face = mtcnn(test_img)
    times_detect.append((time.time() - t0) * 1000)
avg_detect = np.mean(times_detect)

# FaceNet 嵌入速度
if face is not None:
    face_tensor = face.unsqueeze(0).to(DEVICE)
    times_embed = []
    for _ in range(10):
        t0 = time.time()
        with torch.no_grad():
            resnet(face_tensor)
        times_embed.append((time.time() - t0) * 1000)
    avg_embed = np.mean(times_embed)

    # ONNX 嵌入速度 (CPU)
    if session is not None:
        face_np = face.numpy().astype(np.float32)  # MTCNN 已归一化到 [-1,1]
        face_np_batch = np.expand_dims(face_np, axis=0)  # add batch dim
        times_onnx = []
        for _ in range(10):
            t0 = time.time()
            session.run(None, {session.get_inputs()[0].name: face_np_batch})
            times_onnx.append((time.time() - t0) * 1000)
        avg_onnx = np.mean(times_onnx)
        check(f'ONNX 推理速度: {avg_onnx:.1f}ms (CPU)', avg_onnx < 100)

    check(f'MTCNN 检测: {avg_detect:.0f}ms', avg_detect < 500)
    check(f'FaceNet 嵌入: {avg_embed:.0f}ms ({DEVICE})', avg_embed < 100)

estimated_fps = 1000 / (avg_detect + avg_embed) if face is not None else 0
print(f"  预估帧率: {estimated_fps:.1f} fps (检测+嵌入总计 {avg_detect+avg_embed:.0f}ms)")

# ===== 汇总 =====
section('测试结果汇总')
total = passed + failed
print(f"  通过: {passed}/{total}")
if failed > 0:
    print(f"  失败: {failed}/{total}")
    print(f"  通过率: {passed/total*100:.1f}%")
else:
    print(f"  全部通过!")
print()

# ===== 可选: 单张图片测试 =====
def test_single_image(image_path):
    print(f"\n  测试图片: {image_path}")
    try:
        img = Image.open(image_path).convert('RGB')
        face = mtcnn(img)
        if face is None:
            print("  结果: 未检测到人脸")
            return
        with torch.no_grad():
            emb = resnet(face.unsqueeze(0).to(DEVICE)).cpu().numpy().flatten()

        for name, info in enrolled.items():
            sim = cosine_sim(emb, info['centroid'])
            verdict = 'PASS (本人)' if sim >= THRESHOLD else 'REJECT'
            print(f"    {name}: sim={sim:.4f} → {verdict}")

        # 最佳匹配
        best_name, best_sim = max(
            ((name, cosine_sim(emb, info['centroid'])) for name, info in enrolled.items()),
            key=lambda x: x[1]
        )
        print(f"  最佳匹配: {best_name} ({best_sim:.4f})")
    except Exception as e:
        print(f"  错误: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true', help='完整测试 (999 陌生人)')
    parser.add_argument('--image', type=str, help='测试单张图片')
    args = parser.parse_args()

    if args.image:
        test_single_image(args.image)
    elif args.full:
        # 用全部 999 陌生人重跑测试 5
        stranger_count = 999
        # 重新运行陌生人测试
        section('完整陌生人测试 (999 张)')
        stranger_embs = []
        for img_path in sorted(STRANGER_DIR.glob('*.jpg')):
            try:
                img = Image.open(img_path).convert('RGB')
                face = mtcnn(img)
                if face is not None:
                    with torch.no_grad():
                        emb = resnet(face.unsqueeze(0).to(DEVICE)).cpu().numpy().flatten()
                    stranger_embs.append(emb)
            except Exception:
                pass
        false_accepts = sum(
            max(cosine_sim(emb, info['centroid']) for _, info in enrolled.items()) >= THRESHOLD
            for emb in stranger_embs
        )
        far = false_accepts / len(stranger_embs) * 100 if stranger_embs else 0
        check(f'完整陌生人: {false_accepts}/{len(stranger_embs)} 误识 (FAR={far:.1f}%)', far < 1)
