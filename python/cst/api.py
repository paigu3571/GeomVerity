# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""公开SDK薄入口：沿用已有计算与输出，不依赖Viewer或Desktop。"""
from .model import load
from .l4 import check
from .changes import diff
from .notify import notify
from .decisions import bundle
__all__=['load','check','diff','notify','bundle']
