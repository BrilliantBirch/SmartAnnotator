# BrilliantAnnotator v2.3.0

BrilliantAnnotator 是一款面向深度学习数据准备场景的智能标注工具：内置 labelme 风格的标注编辑器，
支持图片与视频的自动标注、感知区（ROI）裁剪，并提供 LabelMe 与 YOLO 数据格式的双向转换。
标注数据完全兼容 LabelMe JSON 规范，可直接衔接既有标注流程与下游训练框架。

## 1. 功能概述

| 功能              | 说明                                                                                                        |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| **标注编辑器**    | 顶部工具栏 + 中央画布 + 右侧四个信息面板；矩形/点/多边形绘制、属性编辑、复制粘贴、撤销重做、多选            |
| **感知区（ROI）** | 画布绘制与管理感知区（虚线框 + `ROI{id}` 标识、列表联动），按感知区裁剪导出聚焦数据集（跨边界标注自动截断） |
| **自动标注**      | 加载 ONNX 模型，对单张图片、全部图片、视频批量推理，自动生成 LabelMe 标注                                   |
| **模型预加载**    | 模型确认后后台加载与预热（进度弹窗实时显示），模型缓存复用，后续标注秒级启动                                |
| **视频标注**      | 视频抽帧标注（帧间隔/差异阈值可调），含预览播放器与损坏视频保护                                             |
| **检测类别选择**  | 模型加载后自动解析元数据类别，支持复选/全选/取消全选，按类别过滤推理结果                                    |
| **OCR 仅识别**    | 跳过文本检测阶段，仅对已标注区域执行文本识别并回写结果，提升处理效率                                        |
| **格式转换**      | 导出（LabelMe JSON → YOLO TXT，含数据集划分）与导入（YOLO TXT → LabelMe JSON，含 PaddleOCR 互转）           |
| **数据集分析**    | 一键分析数据集标签/任务/方向，数据集按 train/val/test 比例分层划分                                          |
| **配置管理**      | 格式转换与自动标注配置支持 JSON 导入/导出复用，兼容旧版键名                                                 |
| **在线更新**      | 启动静默检查 + 帮助菜单手动检查，确认后自动下载并启动安装器                                                 |
| **内置说明书**    | 帮助 → 使用说明书，程序内直接查阅完整功能说明、快捷键与常见问题                                             |

### 支持的任务模式

| 模式      | 说明               | 转换 | 标注 |
| --------- | ------------------ | ---- | ---- |
| `DETECT`  | 目标检测           | ✓    | ✓    |
| `POSE`    | 姿态估计（关键点） | ✓    | ✓    |
| `SEGMENT` | 实例分割           | ✓    | ✓    |
| `OCR`     | 光学字符识别       | ✓    | ✓    |

## 2. 安装与运行

### 2.1 下载与安装（推荐）

适用于 Windows 10 / 11（64 位）。全部版本与安装包统一发布在 Gitee Releases 发布页：

| 下载入口                                | 链接                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **发布页（全部版本 / 各安装器）**       | [https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases)                                                                                                                                                                                                                                                                                                                                                                                                              |
| 当前版本 CPU 绿色包（v2.3.0）           | [BrilliantAnnotator_CPU_2.3.0.zip](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.3.0/BrilliantAnnotator_CPU_2.3.0.zip)                                                                                                                                                                                                                                                                                                                                                                                         |
| 当前版本 GPU 绿色包（v2.3.0，4 卷分卷） | [part001](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.3.0/BrilliantAnnotator_GPU_2.3.0.zip.part001) · [part002](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.3.0/BrilliantAnnotator_GPU_2.3.0.zip.part002) · [part003](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.3.0/BrilliantAnnotator_GPU_2.3.0.zip.part003) · [part004](https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.3.0/BrilliantAnnotator_GPU_2.3.0.zip.part004) |

**安装方式：**

1. **安装器**（发布页附件）：`BrilliantAnnotator_OnlineSetup.exe`（在线安装器，需联网，会自动下载并解压分卷包）、
   `BrilliantAnnotator_Setup_CPU.exe` / `BrilliantAnnotator_Setup_GPU.exe`（离线安装器，已内置完整程序包）。
   双击运行，按向导选择安装目录完成安装，之后从开始菜单或桌面快捷方式启动。
2. **绿色包**（上表 zip，免安装）：CPU 包直接解压；GPU 分卷包需把 4 个文件下载到同一目录后合并再解压。

```bat
:: GPU 分卷合并（在存放 4 个分卷的目录执行，随后解压 BrilliantAnnotator_GPU_2.3.0.zip）
copy /b BrilliantAnnotator_GPU_2.3.0.zip.part001 + BrilliantAnnotator_GPU_2.3.0.zip.part002 + BrilliantAnnotator_GPU_2.3.0.zip.part003 + BrilliantAnnotator_GPU_2.3.0.zip.part004 BrilliantAnnotator_GPU_2.3.0.zip
```

> GPU 版需要机器具备 NVIDIA 显卡，并已安装 CUDA 运行库（CUDA Toolkit 12.9 + cuDNN 9.x，
> 需确保 cuDNN 的 `bin` 目录在系统 PATH 中）；未满足时程序自动回退 CPU 推理。

### 2.2 源码运行

```bash
# 创建虚拟环境（conda 或 venv 均可）
conda create -n BrilliantAnnotator python=3.12
conda activate BrilliantAnnotator

# 安装依赖
pip install -r requirements.txt

# 启动程序（项目根目录执行）
python -m smart_annotator
```

GPU 推理需额外安装 [requirements-gpu.txt](requirements-gpu.txt) 中的依赖。

### 2.3 更新

程序启动后自动静默检查新版本；也可手动执行 **帮助 → 检查更新**，确认后自动下载安装器并完成覆盖安装。

## 3. 快速上手

1. **打开数据**：文件 → 打开文件夹（Ctrl+O），自动加载目录中的图片并列出文件列表。
2. **人工标注**：选择矩形（R）/ 点（P）/ 多边形（G）工具绘制，绘制完成后在属性弹窗填写标签、描述与困难标记；Ctrl+S 保存（默认开启自动保存）。
3. **自动标注**：工具 → 加载模型 / 自动标注设置，配置模型与推理参数后，执行 工具 → 标注当前图片（Ctrl+1）/ 标注所有图片（Ctrl+2）/ 标注视频。
4. **感知区裁剪**：选择感知区工具（O）在画布上框选关注区域，再经 感知区 → 手动导出感知区数据（Ctrl+Shift+E）生成裁剪后的小图数据集；勾选 自动导出感知区数据 可在每次保存时自动导出。
5. **格式转换**：工具 → 导出标注（JSON → YOLO/PPOCR）/ 导入标注（YOLO/PPOCR → JSON）。
6. **查阅手册**：帮助 → 使用说明书（内置完整说明书，含全部功能、快捷键与常见问题）。

## 4. 配置与数据格式

### 4.1 格式转换配置（convert_config.json）

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

> 输入/输出目录为运行期状态，不序列化（导出输入固定为当前工作路径，导入时可指定输入与输出目录）。

### 4.2 自动标注配置（annotate_config.json）

```json
{
  "device": "GPU",
  "model_path": "",
  "conf": 0.25,
  "kpt_conf": 0.5,
  "nms": 0.7,
  "frame_interval": 30,
  "diff_threshold": 10.0,
  "task_type": "DETECT",
  "selected_classes": [0, 1, 2]
}
```

> - 配置导入兼容旧版键名（如 `modelPath` → `model_path`）。
> - `selected_classes` 为选定检测的类别 id 列表，空列表表示不过滤（检测所有类别）。
> - 模型路径仅支持 `.onnx`。

### 4.3 感知区（ROI）字段（labelme 顶层扩展）

标注 JSON 顶层新增 `ROI` 字段（与 `imagePath` / `imageWidth` / `imageHeight` 同级），记录该图的感知区裁剪框：

```json
{
  "version": "5.5.0",
  "flags": {},
  "shapes": [],
  "imagePath": "a.jpg",
  "imageData": null,
  "imageHeight": 720,
  "imageWidth": 1280,
  "ROI": [
    { "id": 1, "box": [120, 80, 640, 480] },
    { "id": 2, "box": [660, 80, 1100, 480] }
  ]
}
```

> - `box` 采用 `x1 y1 x2 y2` 矩形坐标（图像像素、左上原点），读取时自动归一为左上/右下顺序。
> - `id` 为同图内唯一正整数（从 1 自增、删除后不复用），画布标识文本为 `ROI{id}`。
> - **旧版兼容**：无 `ROI` 字段的 JSON 正常加载（视为无感知区）；感知区为空时不写该字段，老文件保存后不新增键。
> - ROI 不进入 `shapes`，不参与格式转换与标签扫描统计。

### 4.4 数据与配置存放位置

| 内容                                 | 位置                                     |
| ------------------------------------ | ---------------------------------------- |
| 用户配置（界面布局/快捷键/各项开关） | `%APPDATA%/BrilliantAnnotator/`          |
| 标注文件                             | 与图片同目录、同名 `.json`               |
| 感知区裁剪产物                       | `<工作路径>/ROI/`（目录自动创建）        |
| 视频标注抽帧图片与标注               | 视频输出目录（默认 `<输入路径>/Output`） |

## 5. 文档

- 用户说明书：[docs/BrilliantAnnotator_用户说明书.pdf](docs/BrilliantAnnotator_用户说明书.pdf)（源文件 [docs/manual.md](docs/manual.md)，修改后需运行 `python docs/generate_manual_pdf.py` 重新生成）
- 程序内说明书：帮助 → 使用说明书
- 开发与协作规则：[AGENTS.md](AGENTS.md)（AI 编码代理强制规则）；文档维护规则：[docs/AGENTS.md](docs/AGENTS.md)

## 6. 贡献指南

我们欢迎任何形式的贡献：缺陷修复、功能改进、文档完善与问题反馈。

### 6.1 贡献流程总览

```
Fork 仓库 → 克隆到本地 → 创建特性分支 → 开发与自测 → 提交（规范信息）
        → 推送分支 → 提交 Pull Request → 评审与修改 → 合并
```

### 6.2 Fork 与本地准备

1. 打开 [https://github.com/BrilliantBirch/SmartAnnotator](https://github.com/BrilliantBirch/SmartAnnotator)，点击右上角 **Fork** 得到自己的副本。
2. 克隆自己的 Fork，并添加上游仓库以便同步：

```bash
git clone https://github.com/<your-account>/SmartAnnotator.git
cd SmartAnnotator
git remote add upstream https://github.com/BrilliantBirch/SmartAnnotator.git
```

3. 准备开发环境并安装依赖：

```bash
conda create -n BrilliantAnnotator python=3.12
conda activate BrilliantAnnotator
pip install -r requirements.txt
```

4. 开始开发前，先阅读 [AGENTS.md](AGENTS.md)（编码规则、接口约定与验证清单），并同步上游最新代码：

```bash
git fetch upstream
git checkout main
git merge upstream/main
```

### 6.3 分支规范

| 项       | 约定                                                                           |
| -------- | ------------------------------------------------------------------------------ |
| 拉取基线 | 所有开发分支从最新的 `main` 拉出                                               |
| 命名     | `feat_<功能>` / `fix_<问题>` / `docs_<主题>` / `refactor_<模块>`（下划线连接） |
| 粒度     | 一个分支只做一件事；避免在同一分支夹带无关改动                                 |
| 同步     | 开发期间定期 `git merge upstream/main`，减少冲突                               |

```bash
git checkout -b feat_my_feature
```

### 6.4 提交信息规范

格式：`<type>(<scope>): <subject>`

| type       | 含义                   |
| ---------- | ---------------------- |
| `feat`     | 新功能                 |
| `fix`      | 缺陷修复               |
| `refactor` | 重构（不改变外部行为） |
| `docs`     | 文档变更               |
| `chore`    | 构建/依赖/杂项         |
| `release`  | 发版                   |

- `scope` 可选，填写受影响模块（如 `ui`、`annotator`、`convert`）。
- `subject` 简洁描述"做了什么"，正文补充"为什么"与影响范围。
- 示例：`fix(ui): 补全菜单栏缺失的快捷操作入口`、`feat: 实现感知区（ROI）全功能模块`。

### 6.5 提交 Pull Request 规范

**PR 标题**：与提交信息同格式，如 `feat(roi): 支持按感知区批量裁剪导出`。

**PR 描述**：建议包含以下小节：

```markdown
## 变更说明
- 变更点 1（含关键文件/入口）
- 变更点 2

## 关联 Issue
Closes #<issue 编号>

## 自测清单
- [ ] 已完成 编译/导入 最低验证（见 AGENTS.md 的 "Post-change verification checklist" 章节）
- [ ] 涉及 UI 的改动已在本机运行验证
- [ ] 涉及文档的改动已同步（README / docs/manual.md，手册改动需重新生成 PDF）
- [ ] 未包含临时文件、测试数据或与本次改动无关的修改

## 影响与兼容性
- 是否影响既有标注数据/配置文件（默认无）
```

**评审与合并要求**：

1. 评审意见以"提交新 commit"的方式响应，不要强制推送覆盖历史（避免评审上下文丢失）。
2. 合并前保持分支与最新 `main` 同步；冲突请在本地解决并自测。
3. 维护者默认使用 squash 或 ordinary merge 合并，合并后分支可删除。

### 6.6 代码与文档要求

- 最低验证要求：`python -m py_compile <修改的文件>` 与 `python -c "import smart_annotator"` 必须通过。
- 修改 `docs/manual.md` 后必须重新生成 PDF：`python docs/generate_manual_pdf.py`。
- `tests/` 目录已设置为不纳入版本控制，请勿提交测试产物与本地临时文件。
- 打包与发布流程仅由维护者执行，见 [AGENTS.md](AGENTS.md) 的 "Build system invariants" 与 "Git, Branch and Delivery Rules" 章节。

### 6.7 问题反馈（Issue）

提交 Issue 时请尽量包含：

- 运行环境：Windows 版本、CPU/GPU 版安装包、是否加载模型（任务类型）。
- 复现步骤：从打开数据到出现问题的完整操作路径。
- 现象与期望：实际结果、期望结果，必要时附截图。
- 日志信息：进度窗口/状态栏的完整输出或报错信息（可附 `%APPDATA%/BrilliantAnnotator/` 下的日志文件）。

## 7. 作者

BaiBinnan