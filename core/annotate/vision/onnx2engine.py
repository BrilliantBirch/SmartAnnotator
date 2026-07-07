"""
Description：模型转换 onnx->tensorrt->用于在首次部署的机器上转换tensorrt模型
Author:BaiBinnan
Date:2025/04/03
LastEdit:2026/06/25
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
update：
    1. 2026/06/25: 添加 init_libnvinfer_plugins 插件库初始化，修复 pybind11 空指针错误
    2. 2026/06/25: 修复 metadata 解析异常信息被吞掉的问题
    3. 2026/06/25: 添加动态形状配置，兼容不同 batch size 的 ONNX 模型
"""

from cfg import LOGGER
import json


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
        # 初始化插件库（YOLO模型依赖EfficientNMS_TRT等自定义插件）
        trt.init_libnvinfer_plugins(logger, namespace="")
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
                custom_metadata[meta.key] = meta.value
        except Exception as ex:
            raise RuntimeError(f"解析模型元数据失败: {ex}")

        inputs = [network.get_input(i) for i in range(network.num_inputs)]
        outputs = [network.get_output(i) for i in range(network.num_outputs)]
        for inp in inputs:
            LOGGER.info(f' 输入 "{inp.name}" 大小{inp.shape} {inp.dtype}')
        for out in outputs:
            LOGGER.info(f' 输出 "{out.name}" 大小{out.shape} {out.dtype}')

        # 配置动态形状优化（兼容不同batch size的ONNX模型）
        if is_trt10:
            profile = builder.create_optimization_profile()
            for inp in inputs:
                shape = inp.shape
                if -1 in shape:
                    min_shape = list(shape)
                    opt_shape = list(shape)
                    max_shape = list(shape)
                    for i, s in enumerate(shape):
                        if s == -1:
                            min_shape[i] = 1
                            opt_shape[i] = 2
                            max_shape[i] = 8
                    profile.set_shape(inp.name, min_shape, opt_shape, max_shape)
                    LOGGER.info(
                        f' 动态形状 "{inp.name}": min={min_shape}, opt={opt_shape}, max={max_shape}'
                    )
            config.add_optimization_profile(profile)

        LOGGER.info(
            f" 构建 {'FP' + ('16' if half_flag else '32')} engine as {engine_file.name}"
        )
        if half_flag:
            config.set_flag(trt.BuilderFlag.FP16)

        # 写入engine文件
        try:
            if is_trt10:
                engine = builder.build_serialized_network(network, config)
                if engine is None:
                    raise RuntimeError("构建tensorrt引擎失败，请检查ONNX模型是否包含不支持的操作")
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
        except Exception as ex:
            raise RuntimeError(f"构建tensorrt引擎失败: {ex}")
        LOGGER.info(f"模型转换完毕：{str(engine_file)}")
        return engine_file