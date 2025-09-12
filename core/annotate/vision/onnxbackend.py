"""
Description：onnx的推理后端
Author:BaiBinnan
Date:2025/02/26
LastEdit:2025/02/26
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

import onnxruntime as ort


class ONNXInfer:
    def __init__(self, model_path, device="cpu"):
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
        # ====== 新增：获取输入数据类型 ======
        input_tensor = self.session.get_inputs()[0]
        input_type = input_tensor.type  # 获取ONNX类型字符串，如"tensor(float16)"
        self.metadata = self.session.get_modelmeta().custom_metadata_map
        self.metadata["fp16"] = (
            "float16" in input_type.lower() or "half" in input_type.lower()
        )
        self.output_name = [x.name for x in self.session.get_outputs()]
        self.imgsz = self.metadata.get("imgsz", "[640,640]")
        self.imgsz = tuple(eval(self.imgsz))

    def predict(self, img):
        y = self.session.run(self.output_name, {self.input_name: img})
        return y
