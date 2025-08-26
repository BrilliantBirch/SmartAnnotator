from enum import Enum

from utils import LOGGER

__APPNAME__ = "VAI_E_SmartAnnotator"
__VERSION__ = "1.0.0"


class TASK(Enum):
    MODIFY = 0
    ANNOTATE = 1
    CONVERT = 2
