# 前端生态重构 — 兼容性分析报告

> 分支：`feat_annotation_workspace`（基于 `pyside_dev` @ `1188bcc` 创建）
> 重构目标：将 VAI_E_SmartAnnotator 重构为「集自动标注、标注预览、格式转换于一体的自动标注工具」，标注格式完全复用 labelme JSON。

---

## 1. 交付内容

### 1.1 分支创建记录

| 项 | 内容 |
| --- | --- |
| 分支名 | `feat_annotation_workspace` |
| 命名规范 | `feat_<功能特性>`（与仓库现有 conventional commit 风格一致，`feat_annotation_workspace` 体现「标注工作台」特性） |
| 基于分支 | `pyside_dev` |
| 基线提交 | `1188bcc refactor(convert): 重构数据集转换与UI适配` |

### 1.2 变更文件清单

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 新增 | `smart_annotator/core/labelme_io.py` | labelme JSON 标准读写（构造/加载/保存/形状/标签提取） |
| 新增 | `smart_annotator/widgets/canvas.py` | 中间画布（图像显示 + 矩形/点/多边形绘制 + 选中/移动/删除） |
| 新增 | `smart_annotator/widgets/left_toolbar.py` | 左侧快捷操作栏（文件/标注/工具按钮） |
| 新增 | `smart_annotator/widgets/right_panel.py` | 右侧信息栏（标签/对象/文件/关键点列表） |
| 新增 | `smart_annotator/workers/single_annotate_worker.py` | 单张自动标注后台线程 |
| 修改 | `smart_annotator/app.py` | 重构为三栏式标注编辑器 + 标准菜单栏 |
| 修改 | `smart_annotator/core/annotate/annotator.py` | 新增 `annotate_image` 单张推理接口 |
| 修改 | `smart_annotator/widgets/__init__.py` | 导出新控件 |
| 修改 | `smart_annotator/pages/__init__.py` | 移除欢迎页引用 |
| 删除 | `smart_annotator/pages/welcome_page.py` | 欢迎页（冗余，由三栏编辑器取代） |

---

## 2. 已兼容功能清单（直接复用，无回归）

| 功能 | 兼容方式 | 说明 |
| --- | --- | --- |
| 自动标注核心链路 | 复用 `Annotator` + 策略模式 `formatters` + `vision` 预测器 | 新增 `annotate_image` 单张接口返回 labelme 形状，与批量 `run` 完全同一套预测/过滤/格式化链路 |
| 类别过滤 | 复用 `_filter_by_classes` | 单张/批量均按 `selected_classes` 同步过滤 bbox/scores/labels/keypoints |
| 模型类别解析 | 复用 `getModelClasses`（onnx/engine 元数据）+ `AnnotatePage` | 加载模型对话框内原样复用 |
| 格式转换 | 复用 `ConvertPage` + `ConvertWorker` + `Converter` + `dataset_analyzer` | 主窗口「格式转换」菜单打开对话框，页面逻辑原样复用 |
| LabelMe JSON 格式 | 新增 `labelme_io` 字段与现有 `generate_labelme_file` 一致 | `version/flags/shapes/imagePath/imageData/imageHeight/imageWidth` 与 shape 的 `label/points/group_id/description/shape_type/flags/mask` 完全对齐 labelme 5.x |
| 后台线程模型 | 复用 `BaseWorker` + `QThread` | 单张/批量标注、转换均在后台执行，不阻塞 UI |

---

## 3. 无法直接兼容功能清单与分析

### 3.1 欢迎页（WelcomePage）

- **处理**：已删除。
- **技术障碍**：无（有意删除的冗余入口）。
- **影响范围**：应用启动不再显示欢迎页，直接进入标注编辑器；原「格式转换 / 自动标注」两个入口按钮由菜单栏「工具」菜单与左侧工具栏替代。
- **解决建议**：无需恢复；如需品牌展示，可在画布中央加启动占位提示或「关于」对话框增强。

### 3.2 侧边栏 / 底部标签栏响应式导航（旧 app.py）

- **处理**：已移除，由经典三栏布局取代。
- **技术障碍**：旧 `NavButton` / `SIDEBAR_THRESHOLD(768px)` / `resizeEvent` 切换逻辑面向「多页面导航」，与新「单一标注工作台」定位冲突。
- **影响范围**：小于 768px 宽度无底部标签栏降级方案，窄屏下三栏可能拥挤。
- **解决建议**：引入 `QSplitter` 使三栏可拖动缩放，或在小屏下折叠侧栏/信息栏；优先级低。

### 3.3 视频抽帧标注（VideoProcessor）

- **处理**：批量标注仍支持（`Annotator.run` 的 `video_files` 分支）；编辑器内**单张/逐帧**标注未集成。
- **技术障碍**：`Canvas` 基于 `QPixmap` 单帧显示，未实现视频时间轴与逐帧交互；`annotate_image` 仅接受图片路径。
- **影响范围**：编辑器只能处理图片；视频标注需通过「自动标注全部 → 标注设置对话框」的批量流程（输入目录含视频）。
- **解决建议**：后续扩展视频加载 + 抽帧缓存 + 时间轴控件，将帧作为虚拟图片接入画布。

### 3.4 OCR 任务类型（MODE.OCR）

- **处理**：未新增。
- **技术障碍**：`Annotator._create_predictor` 的 `predictor_map` 本就不含 OCR，选择 OCR 会抛 `ValueError`；这是既有限制，非本次重构引入。
- **影响范围**：编辑器与批量标注均不支持 OCR 任务。
- **解决建议**：新增 OCR 预测器 + `formatters` 格式化器，并扩展 `yolo_to_labelme` 的 `_CONVERTER_MAP`。

### 3.5 多模式高级预览（掩码叠加 / 关键点连线等）

- **处理**：基础预览已实现（矩形/点/多边形渲染 + 选中高亮 + 缩放），高级「多模式」增强未实现。
- **技术障碍**：`Canvas` 目前按 `shape_type` 统一渲染，未提供多边形填充/描边、关键点连线、掩码 alpha 叠加等可切换预览模式。
- **影响范围**：不影响基础标注编辑，仅缺少高级可视化。
- **解决建议**：为 `Canvas` 增加渲染开关（如 polygon 仅描边 / 半透明填充、pose 关键点按 group_id 连线）。

### 3.6 图像内嵌（imageData）约定

- **处理**：项目约定 `imageData` 恒为 `None`（外链 `imagePath`）。
- **技术障碍**：非不兼容，是与 labelme 默认「可内嵌 base64」行为的差异。
- **影响范围**：跨工具打开依赖 `imagePath` 相对路径有效。
- **解决建议**：保持现状；如需完全自包含，可在保存时按需写入 base64 `imageData`（优先级低）。

---

## 4. 验证结论

- 语法检查（`py_compile`）：全部变更文件通过。
- 模块导入（Python 3.12.10 + PySide6 6.11.1）：`smart_annotator`、`app`、`canvas`、`left_toolbar`、`right_panel`、`single_annotate_worker`、`labelme_io`、`pages`、`widgets` 导入通过。
- 主窗口实例化：`MainWindow` 构造成功，三栏组件与 4 个标准菜单就绪。
- 单元测试：`tests/` 共 15 项全部通过（labelme_io 7 项 + 编辑器组件 8 项）。