@echo off
REM ============================================
REM  YOLOv5 交通标志检测 — 一键训练脚本
REM  用法: 在 Anaconda Prompt 中运行此脚本
REM ============================================

echo.
echo ==========================================
echo   YOLOv5 交通标志检测模型训练
echo ==========================================
echo.

REM --- 检查 conda 环境 ---
where conda >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 conda，请先安装 Anaconda 或 Miniconda
    echo        下载地址: https://www.anaconda.com/download
    pause
    exit /b 1
)

REM --- 激活虚拟环境 ---
echo [1/4] 激活 yolov5-7 环境...
call conda activate yolov5-7
if %ERRORLEVEL% neq 0 (
    echo [错误] 虚拟环境 yolov5-7 不存在，请先运行:
    echo        conda create -n yolov5-7 python=3.10
    echo        conda activate yolov5-7
    echo        conda install pytorch torchvision torchaudio pytorch-cuda=12.4 -c pytorch -c nvidia
    pause
    exit /b 1
)

REM --- 检查 YOLOv5 ---
if not exist "yolov5-7.0\train.py" (
    echo [错误] 未找到 yolov5-7.0，请先下载:
    echo        git clone https://github.com/ultralytics/yolov5 -b v7.0 yolov5-7.0
    echo        cd yolov5-7.0
    echo        pip install -r requirements.txt
    pause
    exit /b 1
)

REM --- 拆分数据集 ---
echo [2/4] 拆分数据集...
cd /d "%~dp0"
python split_dataset.py
if %ERRORLEVEL% neq 0 (
    echo [错误] 数据集拆分失败！请确认 TRAFFIC/images/ 和 TRAFFIC/labels/ 中有数据
    pause
    exit /b 1
)

REM --- 复制配置文件到 YOLOv5 目录 ---
echo [3/4] 复制配置文件...
copy /Y voc_traffic.yaml ..\..\yolov5-7.0\data\voc_traffic.yaml

REM --- 开始训练 ---
echo [4/4] 开始训练...
cd /d "%~dp0..\..\yolov5-7.0"
python train.py --data data/voc_traffic.yaml --weights yolov5s.pt --epochs 100 --batch-size 16 --img 640

echo.
echo ==========================================
echo   训练完成! 结果保存在:
echo   yolov5-7.0\runs\train\exp\
echo ==========================================
pause
