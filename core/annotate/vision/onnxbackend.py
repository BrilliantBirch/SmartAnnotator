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
        self.output_name = [x.name for x in self.session.get_outputs()]
        self.metadata = self.session.get_modelmeta().custom_metadata_map
        self.imgsz = self.metadata.get("imgsz", "[640,640]")
        self.imgsz = tuple(eval(self.imgsz))

    def predict(self, img):
        y = self.session.run(self.output_name, {self.input_name: img})
        return y
