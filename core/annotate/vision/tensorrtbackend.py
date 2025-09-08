"""
Description：tensorRT的推理后端
Author:BaiBinnan
Date:2025/02/17
LastEdit:2025/02/27
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

import tensorrt as trt
from cuda import cuda, cudart
import numpy as np
import json


# region cuda
def check_cuda_err(err):
    if isinstance(err, cuda.CUresult):
        if err != cuda.CUresult.CUDA_SUCCESS:
            raise RuntimeError("Cuda Error: {}".format(err))
    if isinstance(err, cudart.cudaError_t):
        if err != cudart.cudaError_t.cudaSuccess:
            raise RuntimeError("Cuda Runtime Error: {}".format(err))
    else:
        raise RuntimeError("Unknown error type: {}".format(err))


def cuda_call(call):
    err, res = call[0], call[1:]
    check_cuda_err(err)
    if len(res) == 1:
        res = res[0]
    return res


def memcpy_host_to_device(device_ptr: int, host_arr: np.ndarray):
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpy(
            device_ptr, host_arr, nbytes, cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        )
    )


def memcpy_device_to_host(host_arr: np.ndarray, device_ptr: int):
    nbytes = host_arr.size * host_arr.itemsize
    cuda_call(
        cudart.cudaMemcpy(
            host_arr, device_ptr, nbytes, cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
        )
    )


def memcpy_async_host_to_device(device_ptr: int, host_arr: np.ndarray, stream):
    """
    异步将数据从主机内存拷贝到设备内存
    :param device_ptr: 设备内存指针
    :param host_arr: 主机上的 numpy 数组
    :param stream: CUDA 流对象，传入流句柄
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
    """
    异步将数据从设备内存拷贝到主机内存
    :param host_arr: 主机上预分配的 numpy 数组，用于接收数据
    :param device_ptr: 设备内存指针
    :param stream: CUDA 流对象，传入流句柄
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
    def __init__(self, engine_path):
        logger = trt.Logger(trt.Logger.ERROR)
        trt.init_libnvinfer_plugins(logger, namespace="")
        runtime = trt.Runtime(logger)
        with open(engine_path, "rb") as f:
            try:
                meta_len = int.from_bytes(
                    f.read(4), byteorder="little"
                )  # read metadata length
                self.metadata = json.loads(f.read(meta_len).decode("utf-8"))
            except UnicodeDecodeError:
                f.seek(0)
                self.metadata = {}
            self.engine = runtime.deserialize_cuda_engine(f.read())
            if self.engine == None:
                raise RuntimeError(f"解析tensorrt文件报错")
        # #获取模型输入图片大小
        self.imgsz = self.engine.get_tensor_shape(self.engine.get_tensor_name(0))[
            2:
        ]  # get the read shape of model, in case user input it wrong
        self.context = self.engine.create_execution_context()
        if self.context == None:
            raise RuntimeError(f"创建引擎推理上下文报错")
        # 设置I/O绑定
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
            # 申请cuda内存
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
        stream = cuda_call(cudart.cudaStreamCreate())
        self.stream = stream

    def input_spec(self):
        return self.inputs[0]["shape"], self.inputs[0]["dtype"]

    def output_spec(self):
        specs = []
        for o in self.outputs:
            specs.append((o["shape"], o["dtype"]))
        return specs

    def predict(self, img):
        # img_contig = np.ascontiguousarray(img)

        # 异步从 host 到 device 的内存拷贝
        memcpy_async_host_to_device(self.inputs[0]["allocation"], img, self.stream)

        # 异步执行推理
        self.context.execute_async_v2(self.allocations, self.stream)

        # 异步从 device 到 host 的内存拷贝，对于每个输出
        for o in self.outputs:
            memcpy_async_device_to_host(
                o["host_allocation"], o["allocation"], self.stream
            )

        # 同步等待 CUDA stream 中所有操作完成
        cuda_call(cudart.cudaStreamSynchronize(self.stream))

        return [o["host_allocation"] for o in self.outputs]
