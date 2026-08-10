# -*- coding: utf-8 -*-
"""
core 子包 — 业务逻辑层（算法移植，非重造）

包含两个子模块：
    - convert: 格式转换器（LabelMe <-> YOLO）
    - annotate: 自动标注（YOLO 推理 + 格式化 + 视频抽帧）

本包不依赖 PySide6，可在无头环境运行与测试。

作者: BaiBinnan
创建日期: 2026-08-10
"""
