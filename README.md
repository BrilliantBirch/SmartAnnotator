# VAI_E_SmartAnnotator v1.2.0

基于 PySide6 的智能标注工具，提供 LabelMe ↔ YOLO 格式转换与 ONNX/TensorRT 自动标注功能。

## 1. 功能概述

| 功能 | 说明 |
|------|------|
| **格式转换** | LabelMe JSON ↔ YOLO TXT 双向转换，支持目标检测/姿态估计/实例分割 |
| **自动标注** | 加载 ONNX/TensorRT 模型，对图片/视频批量推理并输出 LabelMe 标注文件 |
| **数据集划分** | 按 train/val/test 比例分层抽样划分 YOLO 数据集 |
| **配置管理** | JSON 格式导入/导出，兼容旧版 camelCase 键 |

### 支持的任务模式

| 模式 | 说明 | 转换 | 标注 |
|------|------|------|------|
| `DETECT` | 目标检测 | ✓ | ✓ |
| `POSE` | 姿态估计（关键点） | ✓ | ✓ |
| `SEGMENT` | 实例分割 | ✓ | ✓ |
| `OCR` | 光学字符识别 | ✓ | 未来版本 |

## 2. 技术栈

| 项目 | 版本 |
|------|------|
| Python | 3.12.10（严格锁定） |
| PySide6 | 6.11.1 |
| numpy | 2.4.6 |
| opencv-python | 4.13.0.92 |
| onnxruntime | 1.28.0 |
| pywin32 | 312 |

完整依赖见 [requirements.txt](requirements.txt)，GPU 额外依赖见 [requirements-gpu.txt](requirements-gpu.txt)。

## 3. 项目结构

```
VAI_E_SmartAnnotator/
├── smart_annotator/              # 主包
│   ├── __init__.py               # 应用常量
│   ├── __main__.py               # python -m smart_annotator 入口
│   ├── main.py                   # QApplication 入口
│   ├── app.py                    # MainWindow 主窗口
│   ├── styles.py                 # 全局 QSS 样式表
│   ├── config.py                 # dataclass 配置 + 枚举
│   ├── version_manager.py        # 版本号管理
│   ├── pages/                    # 三页界面（欢迎/转换/标注）
│   ├── widgets/                  # 公共控件（按钮/卡片/字段/对话框）
│   ├── workers/                  # QThread 工作线程
│   ├── core/                     # 业务逻辑（转换/标注算法）
│   └── utils/                    # 工具（日志/文件/路径/颜色）
├── build.py                      # PyInstaller 打包脚本（项目根目录）
├── installer.iss                 # Inno Setup 离线安装器脚本
├── installer_online.iss          # Inno Setup 在线安装器脚本
├── download_config.ini           # Gitee Release 下载 URL 配置
├── app.ico                       # 应用图标
├── resources/                    # 资源文件
│   └── images/                   # 图标资源
├── assets/                       # 示例图片
├── requirements.txt              # 依赖列表
├── requirements-gpu.txt          # GPU 额外依赖
└── README.md
```

## 4. 安装与运行

### 4.1 环境准备

```bash
# 创建 conda 虚拟环境（Python 3.12.10）
conda create -n VAI_E_SmartAnnotator python=3.12.10
conda activate VAI_E_SmartAnnotator

# 安装依赖
pip install -r requirements.txt

# GPU 推理需额外安装（需先安装 CUDA + cuDNN）
pip install -r requirements-gpu.txt
```

### 4.2 运行

```bash
# 方式一：模块入口
python -m smart_annotator

# 方式二：直接运行
python smart_annotator/main.py
```

## 5. 配置文件格式

### 5.1 格式转换配置（convert_config.json）

```json
{
  "source_format": "LABELME",
  "target_format": "YOLO",
  "classes": ["cat", "dog"],
  "kpt": { "nose_point0": { "isChecked": true, "bbox_size": 10 } },
  "visualize": false,
  "export": false,
  "input_dir": "",
  "output_dir": "",
  "train_ratio": 0.8,
  "val_ratio": 0.1,
  "test_ratio": 0.1
}
```

### 5.2 自动标注配置（annotate_config.json）

```json
{
  "device": "GPU",
  "model_path": "",
  "image_path": "",
  "dataset_path": "",
  "conf": 0.25,
  "kpt_conf": 0.5,
  "nms": 0.7,
  "frame_interval": 30,
  "diff_threshold": 10.0,
  "task_type": "DETECT"
}
```

> 配置导入兼容旧版 camelCase 键名（如 `modelPath` → `model_path`）。

## 6. 打包

```bash
# 在项目根目录执行
python build.py --mode all      # 构建 CPU + GPU 离线安装器 + 在线安装器
python build.py --mode cpu      # 仅构建 CPU 离线安装器
python build.py --mode gpu      # 仅构建 GPU 离线安装器
python build.py --mode online   # 仅编译在线安装器（上传 zip 到 Gitee 后使用）
```

打包产物位于 `build/dist_{mode}/VAI_E_SmartAnnotator/`：
- `VAI_E_SmartAnnotator.exe` — 可执行文件
- `VAI_E_SmartAnnotator/` — 依赖包目录
- `py_packages_list.txt` — 依赖文件清单

安装程序输出到 `build/installer_output/`，zip 分发包输出到 `build/packages/`。

版本号策略：
- 文件版本：`年.月.日.构建次数`（如 `26.8.10.0`），自动递增
- 产品版本：`1.2.0.0`（固定）

## 7. 架构设计

### 7.1 分层架构

```
pages/（界面层）→ workers/（线程层）→ core/（算法层）
     ↑                ↑                  ↑
     └── widgets/     └── base_worker    └── utils/
```

- **界面层**（pages/）：BasePage 基类 + 三页，通过 Signal 与 worker 通信
- **线程层**（workers/）：BaseWorker(QThread) 提供暂停/恢复/停止控制
- **算法层**（core/）：纯 Python 算法，无 Qt 依赖，可独立测试
- **工具层**（utils/）：日志（LOGGER 纯 Python + QtLogHandler Qt 适配）、文件扫描、路径解析

### 7.2 配置管理

基于 `@dataclass` 的配置类（`ConvertConfig`/`AnnotateConfig`/`SysConfig`），支持 `to_dict()`/`from_dict()` 序列化与旧版 camelCase 键迁移。

### 7.3 响应式 UI

- 窗口宽度 ≥ 768px：显示侧边栏导航
- 窗口宽度 < 768px：切换为底部标签栏
- 内容区使用 QScrollArea 包裹，小屏不溢出

## 8. 作者

BaiBinnan（baibinnan@chuanfeng.com）

武汉川丰软件
