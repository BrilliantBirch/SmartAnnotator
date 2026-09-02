# -*- coding: utf-8 -*-
"""
ONNX 推理后端

作者: BaiBinnan
创建日期: 2026-08-10
"""

import onnxruntime as ort


class ONNXInfer:
    """ONNX 模型推理封装（基于 onnxruntime）。"""

    def __init__(self, model_path, device="cpu"):
        """初始化 ONNX 推理会话。

        Args:
            model_path: ONNX 模型文件路径。
            device: 推理设备，"cpu" 或 GPU device_id。
        """
        providers = (
            [
                (
                    "CUDAExecutionProvider",
                    {
                        "device_id": device,
                    },
                )
            ]
            if device != "cpu"
            else ["CPUExecutionProvider"]
        )
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        # 获取输入数据类型
        input_tensor = self.session.get_inputs()[0]
        input_type = input_tensor.type  # ONNX 类型字符串，如 "tensor(float16)"
        self.metadata = self.session.get_modelmeta().custom_metadata_map
        self.metadata["fp16"] = (
            "float16" in input_type.lower() or "half" in input_type.lower()
        )
        self.output_name = [x.name for x in self.session.get_outputs()]
        self.imgsz = self.metadata.get("imgsz", "[640,640]")
        self.imgsz = tuple(eval(self.imgsz))

    def predict(self, img):
        """执行推理。

        Args:
            img: 预处理后的输入张量。

        Returns:
            模型输出列表。
        """
        y = self.session.run(self.output_name, {self.input_name: img})
        return y
