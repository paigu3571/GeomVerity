# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
from pathlib import Path

def rules_directory():
    checkout=Path(__file__).resolve().parents[2]/'rules'
    if (checkout/'space-uses.draft.yaml').is_file():return checkout
    bundled=Path(__file__).with_name('resources')/'rules'
    if not (bundled/'space-uses.draft.yaml').is_file():raise ValueError('安装包缺少规则资源，请重新安装完整GeomVerity包')
    return bundled
