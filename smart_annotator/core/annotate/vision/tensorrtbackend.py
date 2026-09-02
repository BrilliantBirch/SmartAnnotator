# -*- coding: utf-8 -*-
"""
TensorRT 推理后端（兼容 TensorRT 10.x）

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-06-24 适配 TensorRT 10.x API（set_tensor_address + execute_async_v3）
"""

import tensorrt as trt
from cuda import cuda, cudart
import numpy as np
import json


# region cuda 辅助函数
def check_cuda_err(err):
    """检查 CUDA 调用返回值，失败时抛出 RuntimeError。"""
    if isinstance(err, cuda.CUresult):
        if err != cuda.CUresult.CUDA_SUCCESS:
            raise RuntimeError("Cuda Error: {}".format(err))
    if isinstance(err, cudart.cudaError_t):
        if err != cudart.cudaError_t.cudaSuccess:
            raise RuntimeError("Cuda Runtime Error: {}".format(err))
    else:
        raise RuntimeError("Unknown error type: {}".format(err))


def cuda_call(call):
    """统一处理 CUDA 调用的 (err, result) 返回模式。"""
    err, res = call[0], call[1:]
    check_cuda_err(err)
    if len(res) == 1:
        res = res[0]
    return res


def memcpy_host_to_device(device_ptr: int, host_arr: np.ndarray):
    """同步将数据从主机内存拷贝到设备内存。"""
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpy(
            device_ptr, host_arr, nbytes, cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        )
    )


def memcpy_device_to_host(host_arr: np.ndarray, device_ptr: int):
    """同步将数据从设备内存拷贝到主机内存。"""
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpy(
            host_arr, device_ptr, nbytes, cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
        )
    )


def memcpy_async_host_to_device(device_ptr: int, host_arr: np.ndarray, stream):
    """异步将数据从主机内存拷贝到设备内存。

    Args:
        device_ptr: 设备内存指针。
        host_arr: 主机上的 numpy 数组。
        stream: CUDA 流句柄。
    """
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpyAsync(
            device_ptr,
            host_arr,
            nbytes,
            cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
            stream,
        )
    )


def memcpy_async_device_to_host(host_arr: np.ndarray, device_ptr: int, stream):
    """异步将数据从设备内存拷贝到主机内存。

    Args:
        host_arr: 主机上预分配的 numpy 数组，用于接收数据。
        device_ptr: 设备内存指针。
        stream: CUDA 流句柄。
    """
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpyAsync(
            host_arr,
            device_ptr,
            nbytes,
            cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
            stream,
        )
    )


# endregion


class TensorRTInfer:
    """TensorRT 引擎推理封装（兼容 TensorRT 10.x）。"""

    def __init__(self, engine_path):
        """加载 TensorRT 引擎并分配 CUDA 内存。

        Args:
            engine_path: .engine 模型文件路径。

        Raises:
            RuntimeError: 引擎解析或上下文创建失败。
            ValueError: 批次大小或 I/O 缓存异常。
        """
        logger = trt.Logger(trt.Logger.ERROR)
        trt.init_libnvinfer_plugins(logger, namespace="")
        runtime = trt.Runtime(logger)
        with open(engine_path, "rb") as f:
            try:
                meta_len = int.from_bytes(
                    f.read(4), byteorder="little"
                )  # 读取 metadata 长度
                self.metadata = json.loads(f.read(meta_len).decode("utf-8"))
            except UnicodeDecodeError:
                f.seek(0)
                self.metadata = {}
            self.engine = runtime.deserialize_cuda_engine(f.read())
            if self.engine == None:
                raise RuntimeError(f"解析tensorrt文件报错")
        # 获取模型输入图片大小
        self.imgsz = self.engine.get_tensor_shape(self.engine.get_tensor_name(0))[
            2:
        ]  # 读取模型输入形状，防止用户输入错误
        self.context = self.engine.create_execution_context()
        if self.context == None:
            raise RuntimeError(f"创建引擎推理上下文报错")
        # 设置 I/O 绑定
        self.inputs = []
        self.outputs = []
        self.allocations = []

        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            dtype = self.engine.get_tensor_dtype(name)
            dtype = np.dtype(trt.nptype(dtype))
            if dtype == np.float16:
                self.metadata["fp16"] = True
            else:
                self.metadata["fp16"] = False
            shape = self.engine.get_tensor_shape(name)
            size = dtype.itemsize
            for s in shape:
                size *= s
            # 申请 cuda 内存
            allocation = cuda_call(cudart.cudaMalloc(size))
            self.allocations.append(allocation)

            is_input = self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
            host_allocation = None if is_input else np.zeros(shape, dtype)
            # 设置绑定
            binding = {
                "index": i,
                "name": name,
                "dtype": dtype,
                "shape": list(shape),
                "allocation": allocation,
                "size": size,
                "host_allocation": host_allocation,
            }
            if is_input:
                self.batch_size = shape[0]
                self.inputs.append(binding)
            else:
                self.outputs.append(binding)
            if self.batch_size <= 0:
                raise ValueError(f"模型批次大小错误，批次解析值为{self.batch_size}")

        if (
            not len(self.inputs) > 0
            or not len(self.outputs) > 0
            or not len(self.allocations) > 0
        ):
            raise ValueError(f"模型输入输出缓存错误")

        # TensorRT 10.x: 使用 set_tensor_address 绑定地址
        for binding in self.inputs + self.outputs:
            self.context.set_tensor_address(binding["name"], binding["allocation"])

        stream = cuda_call(cudart.cudaStreamCreate())
        self.stream = stream

    def input_spec(self):
        """返回输入张量的 (shape, dtype)。"""
        return self.inputs[0]["shape"], self.inputs[0]["dtype"]

    def output_spec(self):
        """返回所有输出张量的 (shape, dtype) 列表。"""
        specs = []
        for o in self.outputs:
            specs.append((o["shape"], o["dtype"]))
        return specs

    def predict(self, img):
        """执行异步推理。

        Args:
            img: 预处理后的输入张量。

        Returns:
            输出张量列表（主机内存）。
        """
        # 异步从 host 到 device 的内存拷贝
        memcpy_async_host_to_device(self.inputs[0]["allocation"], img, self.stream)

        # TensorRT 10.x: 异步执行推理，使用 CUDA 流实现拷贝与计算的并行重叠
        self.context.execute_async_v3(self.stream)

        # 异步从 device 到 host 的内存拷贝
        for o in self.outputs:
            memcpy_async_device_to_host(
                o["host_allocation"], o["allocation"], self.stream
            )

        # 同步等待 CUDA stream 中所有操作完成
        cuda_call(cudart.cudaStreamSynchronize(self.stream))

        return [o["host_allocation"] for o in self.outputs]
