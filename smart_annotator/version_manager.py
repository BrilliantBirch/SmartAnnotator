# -*- coding: utf-8 -*-
"""
版本号管理器 - 生成与管理工具版本号

版本号策略:
    - 文件版本 (FileVersion): year.month.day.count（如 26.8.10.0），按日期+生成次数自动递增
    - 产品版本 (ProductVersion): 唯一来源为 smart_annotator/__init__.py 的 __version__
      （本模块直接引用，发版时仅需修改 __version__ 一处）

文件版本格式说明:
    - year:  年份后两位（2026 → 26）
    - month: 月份（1-12）
    - day:   日期（1-31）
    - count: 当日生成次数（0 起，每次构建递增）

计数持久化: build/version_counter.txt 文件记录上次构建日期与计数。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 修复 PRODUCT_VERSION_TUPLE 为 4 元组（PyInstaller FixedFileInfo 要求，
      3 元组导致 prodvers[3] IndexError → VSVersionInfo 反序列化失败）
更新: 2026-09-10 PRODUCT_VERSION 改为直接引用 __init__.py 的 __version__（版本号
      单点维护），PRODUCT_VERSION_TUPLE 由 __version__ 自动解析补零生成
"""
from datetime import datetime
from pathlib import Path
from typing import Tuple

from smart_annotator import __version__

# __version__ 解析为整数段（如 "2.1.0" → [2, 1, 0]），供四元组补零使用
_VERSION_PARTS = [int(part) for part in __version__.split(".")]


class VersionManager:
    """版本号生成与管理器。

    每次调用 generate_file_version() 时，读取计数文件判断是否为同日构建：
    - 同日: 计数 +1
    - 跨日: 计数归 0

    Attributes:
        counter_file: 计数文件路径（默认为 build/version_counter.txt）。
    """

    # 公司与产品信息（用于 PyInstaller 版本资源）
    COMPANY_NAME = "BrilliantBirch"
    PRODUCT_NAME = "BrilliantBirchProduct"
    PROGRAM_NAME = "BrilliantAnnotator"
    FILE_DESCRIPTION = "BrilliantAnnotator"

    # 产品版本直接引用 smart_annotator/__init__.py 的 __version__（版本号
    # 唯一来源，发版时仅需修改该处，本模块与构建产物自动联动）
    PRODUCT_VERSION = __version__
    # VS_FIXEDFILEINFO 四段式元组（major.minor.patch.0）；PyInstaller 的
    # FixedFileInfo 要求 filevers/prodvers 必须为 4 元组，缺段会 IndexError。
    # 由 __version__ 自动解析：不足四段补 0（如 "2.1.0" → (2, 1, 0, 0)），
    # 超过四段截断取前四段
    PRODUCT_VERSION_TUPLE = tuple((_VERSION_PARTS + [0, 0, 0, 0])[:4])

    def __init__(self, counter_file: str = "version_counter.txt"):
        """初始化版本管理器。

        Args:
            counter_file: 计数文件路径（相对路径基于 cwd，打包脚本在 build/ 下执行）。
        """
        self.counter_file = Path(counter_file)

    def generate_file_version(self) -> str:
        """生成下一个文件版本号并持久化计数。

        读取计数文件，比较日期。同日则计数递增，跨日则归 0。
        将新日期与计数写回计数文件。

        Returns:
            文件版本号字符串，如 "26.8.10.0"。
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 读取上次构建记录
        last_date, last_count = self._read_counter()

        # 判断计数
        if last_date == today_str:
            new_count = last_count + 1
        else:
            new_count = 0

        # 持久化
        self._write_counter(today_str, new_count)

        # 组装文件版本号: year.month.day.count
        year_short = str(now.year)[-2:]
        return f"{year_short}.{now.month}.{now.day}.{new_count}"

    def generate_version_info_text(self, file_version: str) -> str:
        """生成 PyInstaller Windows 版本信息文件内容。

        文件版本 (filevers) 按日期+次数自动生成，产品版本 (prodvers) 取自
        PRODUCT_VERSION_TUPLE（由 __version__ 解析补零生成）。

        Args:
            file_version: 文件版本号字符串，如 "26.8.10.0"。

        Returns:
            VSVersionInfo 格式的文本内容，供 PyInstaller version 参数使用。
        """
        file_parts = file_version.split(".")
        file_v_tuple = ", ".join(file_parts)
        prod_v_tuple = ", ".join(str(v) for v in self.PRODUCT_VERSION_TUPLE)
        return f"""# UTF-8
#
# PyInstaller Windows 版本信息文件 - 由 VersionManager 自动生成
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({file_v_tuple}),
    prodvers=({prod_v_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', '{self.COMPANY_NAME}'),
        StringStruct('FileDescription', '{self.FILE_DESCRIPTION}'),
        StringStruct('FileVersion', '{file_version}'),
        StringStruct('InternalName', '{self.PROGRAM_NAME}'),
        StringStruct('OriginalFilename', '{self.PROGRAM_NAME}.exe'),
        StringStruct('ProductName', '{self.PRODUCT_NAME}'),
        StringStruct('ProductVersion', '{self.PRODUCT_VERSION}'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [0x804, 1200])])
  ]
)
"""

    def _read_counter(self) -> Tuple[str, int]:
        """读取计数文件，返回上次构建日期与计数。

        Returns:
            (date_str, count) 元组。文件不存在时返回 ("", -1)。
        """
        if not self.counter_file.exists():
            return ("", -1)

        try:
            lines = self.counter_file.read_text(encoding="utf-8").strip().splitlines()
            date_str = ""
            count = -1
            for line in lines:
                if line.startswith("date="):
                    date_str = line.split("=", 1)[1].strip()
                elif line.startswith("count="):
                    count = int(line.split("=", 1)[1].strip())
            return (date_str, count)
        except (IOError, ValueError):
            return ("", -1)

    def _write_counter(self, date_str: str, count: int) -> None:
        """写入计数文件。

        Args:
            date_str: 当前日期字符串（YYYY-MM-DD）。
            count: 当前计数。
        """
        try:
            self.counter_file.write_text(
                f"date={date_str}\ncount={count}\n",
                encoding="utf-8",
            )
        except IOError:
            pass
