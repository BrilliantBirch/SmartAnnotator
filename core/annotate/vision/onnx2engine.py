"""
Description：模型转换 onnx->tensorrt->用于在首次部署的机器上转换tensorrt模型
Author:BaiBinnan
Date:2025/04/03
LastEdit:2025/09/05
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

from cfg import LOGGER
import json


# import gc
class Onnx2Engine:
    def __init__(self, onnxfile, half=True):
        self.onnxfile = onnxfile
        self.half = half

    def run(self):
        import tensorrt as trt

        LOGGER.info(f"当前tensorrt版本{trt.__version__}")
        is_trt10 = int(trt.__version__.split(".", 1)[0]) >= 10
        if not self.onnxfile.exists():
            raise FileNotFoundError(f"{self.onnxfile}模型文件不存在")
        engine_file = self.onnxfile.with_suffix(".engine")

        # trt推理引擎创建
        logger = trt.Logger(trt.Logger.INFO)
        builder = trt.Builder(logger)
        config = builder.create_builder_config()
        # 4GB工作空间
        workspace = int(4 * (1 << 30))
        if is_trt10:
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace)
        else:
            config.max_workspace_size = workspace
        # 显示批次标记
        flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        network = builder.create_network(flag)
        # 是否启用半精度
        half_flag = builder.platform_has_fast_fp16 and self.half
        # 解析onnx模型
        parser = trt.OnnxParser(network, logger)
        try:
            with open(self.onnxfile, "rb") as f:
                if not parser.parse(f.read()):
                    error_msgs = "\n".join(
                        [
                            f"{idx}: {err.desc()}"
                            for idx, err in enumerate(parser.errors)
                        ]
                    )
                    raise RuntimeError(f"解析onnx模型失败:\n{error_msgs}")
        except Exception as ex:
            raise RuntimeError(f"解析onnx模型失败:\n{ex}")

        # 解析metadata
        try:
            import onnx

            onnx_model = onnx.load(str(self.onnxfile))
            custom_metadata = {}
            for meta in onnx_model.metadata_props:
                if meta.key == "names":
                    meta.value = json.dumps(eval(meta.value))
                # 存储所有metadata键值对（可根据需要筛选特定键）
                custom_metadata[meta.key] = meta.value

        except Exception as ex:
            raise RuntimeError(f"ex")
        inputs = [network.get_input(i) for i in range(network.num_inputs)]
        outputs = [network.get_output(i) for i in range(network.num_outputs)]
        for inp in inputs:
            LOGGER.info(f' 输入 "{inp.name}" 大小{inp.shape} {inp.dtype}')
        for out in outputs:
            LOGGER.info(f' 输出 "{out.name}" 大小{out.shape} {out.dtype}')

        LOGGER.info(
            f" 构建 { 'FP' + ('16' if half_flag else '32')} engine as {engine_file.name}"
        )
        if half_flag:
            config.set_flag(trt.BuilderFlag.FP16)

        # 写入engine文件
        if is_trt10:
            engine = builder.build_serialized_network(network, config)
            if engine is None:
                raise RuntimeError("构建tensorrt引擎失败")
            with open(engine_file, "wb") as t:
                if custom_metadata:
                    meta = json.dumps(custom_metadata)
                    t.write(len(meta).to_bytes(4, byteorder="little", signed=True))
                    t.write(meta.encode())
                t.write(engine)
        else:
            with builder.build_engine(network, config) as engine, open(
                engine_file, "wb"
            ) as t:
                if custom_metadata:
                    meta = json.dumps(custom_metadata)
                    t.write(len(meta).to_bytes(4, byteorder="little", signed=True))
                    t.write(meta.encode())
                t.write(engine.serialize())
        LOGGER.info(f"模型转换完毕：{str(engine_file)}")
        return engine_file
        # gc.collect()
