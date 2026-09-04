# SmartAnnotator v1.2.0

基于 PySide6 的智能标注工具，提供 LabelMe ↔ YOLO 格式转换与 ONNX 自动标注（CPU / CUDA GPU）功能。

## 1. 功能概述

| 功能             | 说明                                                                     |
| ---------------- | ------------------------------------------------------------------------ |
| **标注编辑器**   | 三栏式（工具栏/画布/信息栏）标注编辑器，矩形/点/多边形绘制、属性编辑、撤销重做 |
| **格式转换**     | LabelMe JSON ↔ YOLO TXT 双向转换（导出/导入），支持目标检测/姿态估计/实例分割 |
| **自动标注**     | 加载 ONNX 模型批量推理（CPU / onnxruntime CUDA EP），输出 LabelMe 标注文件 |
| **视频标注**     | 视频抽帧标注（帧间隔/差异阈值可调），含预览播放器与损坏视频保护           |
| **检测类别选择** | 模型加载后自动解析元数据类别，支持复选/全选/取消全选，按类别过滤推理结果 |
| **数据集分析**   | 一键分析数据集标签/任务/方向，数据集按 train/val/test 比例分层划分       |
| **配置管理**     | JSON 格式导入/导出，兼容旧版 camelCase 键                                |

### 支持的任务模式

| 模式      | 说明               | 转换 | 标注     |
| --------- | ------------------ | ---- | -------- |
| `DETECT`  | 目标检测           | ✓    | ✓        |
| `POSE`    | 姿态估计（关键点） | ✓    | ✓        |
| `SEGMENT` | 实例分割           | ✓    | ✓        |
| `OCR`     | 光学字符识别       | ✓    | 未来版本 |

## 2. 技术栈

| 项目          | 版本                |
| ------------- | ------------------- |
| Python        | 3.12.10（严格锁定） |
| PySide6       | 6.11.1              |
| numpy         | 2.4.6               |
| opencv-python | 4.13.0.92           |
| onnxruntime   | 1.28.0              |
| pywin32       | 312                 |

完整依赖见 [requirements.txt](requirements.txt)，GPU 额外依赖见 [requirements-gpu.txt](requirements-gpu.txt)。

## 3. 项目结构

```
VAI_E_SmartAnnotator/
├── smart_annotator/              # 主包
│   ├── __init__.py               # 应用常量
│   ├── __main__.py               # python -m smart_annotator 入口
│   ├── main.py                   # QApplication 入口
│   ├── app.py                    # MainWindow 主窗口（三栏标注编辑器）
│   ├── styles.py                 # 全局 QSS 样式表
│   ├── config.py                 # dataclass 配置 + 枚举
│   ├── version_manager.py        # 版本号管理
│   ├── pages/                    # 页面层（base/convert/annotate）
│   ├── widgets/                  # 公共控件（画布/右栏/对话框/文件列表模型等）
│   ├── workers/                  # QThread 工作线程
│   ├── core/                     # 业务逻辑（转换/标注算法，无 Qt 依赖）
│   └── utils/                    # 工具（日志/文件/路径/颜色/渲染配置）
├── build.py                      # PyInstaller 打包脚本（项目根目录）
├── installer.iss                 # Inno Setup 离线安装器脚本
├── installer_online.iss          # Inno Setup 在线安装器脚本
├── download_config.ini           # Gitee Release 下载 URL 配置
├── app.ico                       # 应用图标
├── docs/                         # 文档（用户说明书 + PDF 生成脚本）
├── requirements.txt              # 依赖列表
├── requirements-gpu.txt          # GPU 额外依赖
├── AGENTS.md                     # AI 编码助手项目规则
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

# GPU 推理需额外安装（onnxruntime-gpu + nvidia 运行库，无需系统级 CUDA Toolkit）
pip install -r requirements-gpu.txt
```

> GPU 模式说明：推理走 onnxruntime CUDA Execution Provider，程序启动时自动注册
> pip 包内的 CUDA 运行库 DLL（cuDNN/cuBLAS/cuFFT/cudart，见
> `smart_annotator/core/annotate/vision/onnxbackend.py` 的 `_ensure_cuda_dlls`），
> 用户机器只需 NVIDIA 显卡驱动，无需安装 CUDA Toolkit。

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
  "classes": ["cat", "dog"],
  "kpt": { "nose_point0": { "isChecked": true, "bbox_size": 10 } },
  "visualize": false,
  "export": false,
  "train_ratio": 0.8,
  "val_ratio": 0.1,
  "test_ratio": 0.1
}
```

> 输入/输出目录为运行期状态，不序列化（导出输入固定为当前工作路径，
> 导入时可指定输入与输出目录）。

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
  "task_type": "DETECT",
  "selected_classes": [0, 1, 2]
}
```

> 配置导入兼容旧版 camelCase 键名（如 `modelPath` → `model_path`）。
> `selected_classes` 为用户选择检测的类别 id 列表，空列表表示不过滤（检测所有类别）。
> `model_path` 仅支持 `.onnx`（GPU 经 onnxruntime CUDA EP 推理，无需模型转换）。

## 6. 打包

```bash
# 在项目根目录执行（GPU 模式需在 VAI_E_Vision_FrameWork conda 环境中运行）
python build.py --mode all      # 构建 CPU + GPU 离线安装器 + 在线安装器
python build.py --mode cpu      # 仅构建 CPU 离线安装器
python build.py --mode gpu      # 仅构建 GPU 离线安装器
python build.py --mode online   # 仅编译在线安装器（上传 zip 到 Gitee 后使用）
```

打包产物位于 `build/dist_{mode}/VAI_E_SmartAnnotator/`：
- `BrilliantAnnotator.exe` — 可执行文件
- `VAI_E_SmartAnnotator/` — 依赖包目录
- `py_packages_list.txt` — 依赖文件清单

安装程序输出到 `build/installer_output/`，zip 分发包输出到 `build/packages/`。

GPU 模式构建说明（2026-09-04 起）：
- GPU 推理走 onnxruntime CUDA Execution Provider（TensorRT / cuda-python 链路已移除）
- 构建时自动将 pip 包 `nvidia-*-cu12` 的运行库 DLL 复制到 exe 目录（cuDNN/cuBLAS/cuFFT/cudart）
- 清理构建机混入的冗余 TensorRT DLL（nvinfer/nvonnxparser 等）

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

- **界面层**（pages/）：BasePage 基类，通过 Signal 与 worker 通信
- **线程层**（workers/）：BaseWorker(QThread) 提供进度/日志/错误信号，耗时任务不阻塞 UI
- **算法层**（core/）：纯 Python 算法，无 Qt 依赖，可独立测试
- **工具层**（utils/）：日志（LOGGER 纯 Python 控制台 + QtLogHandler Qt 适配）、文件扫描、路径解析

### 7.2 配置管理

基于 `@dataclass` 的配置类（`ConvertConfig`/`AnnotateConfig`/`SysConfig`），支持 `to_dict()`/`from_dict()` 序列化与旧版 camelCase 键迁移。

### 7.3 标注编辑器（主界面）

三栏式布局：左侧快捷操作栏（文件/自动标注/标注工具）+ 中间标注画布
（图像显示与形状绘制/编辑）+ 右侧信息栏（标签/对象/文件/关键点列表）。
文件列表采用 QListView + FileListModel 实现 UI 虚拟化，万级目录秒开。

### 7.4 类别选择链路

```
模型路径选择 → getModelClasses()（onnx 解析 metadata["names"]）
→ ClassSelectorWidget（复选列表）
→ AnnotateConfig.selected_classes → Annotator._filter_by_classes()
→ 推理结果按类别过滤（bboxs/scores/labels/keypoints/boundary_points 同步）
```

## 8. 文档

- 用户使用说明书：[docs/VAI_E_SmartAnnotator_用户说明书.pdf](docs/VAI_E_SmartAnnotator_用户说明书.pdf)
  （源文件 [docs/manual.md](docs/manual.md)，修改后需运行 `python docs/generate_manual_pdf.py` 重新生成）

## 9. 贡献规范

- 遵循 [AGENTS.md](AGENTS.md) 项目规则（分支策略、代码风格、验证清单）
- Python 版本严格锁定 3.12.10，依赖版本见 requirements.txt（禁止自行升级/降级）
- 提交信息格式：`<type>(<scope>): <subject>`（type: feat/fix/refactor/docs/chore）
- 修改后最低验证：`python -m py_compile <文件>` + `python -c "import <模块>"`
- 涉及 manual.md 的修改必须重新生成 PDF

## 10. 作者

BaiBnnan
