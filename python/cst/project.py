# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""工作台旁挂项目文件，不修改任何扫描契约或扫描目录。"""
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

FILENAME = 'geomverity-project.json'


class Version(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scan_directory: str = Field(min_length=1)
    note: str = ''


class Project(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['geomverity-project.v1'] = 'geomverity-project.v1'
    name: str = Field(min_length=1)
    versions: list[Version] = Field(default_factory=list)
    current_version_id: str | None = None

    def checked(self):
        ids = [version.id for version in self.versions]
        if len(set(ids)) != len(ids):
            raise ValueError('项目含重复的版本编号')
        if self.current_version_id is not None and self.current_version_id not in ids:
            raise ValueError('当前版本不在项目版本列表中')
        return self

    def add_version(self, name, directory, note=''):
        path = Path(directory).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('扫描目录不存在，请选择已有JSON结果目录')
        if not name.strip():
            raise ValueError('请填写版本名称')
        version = Version(id=uuid4().hex, name=name.strip(), scan_directory=str(path), note=note)
        self.versions.append(version)
        self.current_version_id = version.id
        return version

    def select(self, version_id):
        if version_id not in {version.id for version in self.versions}:
            raise ValueError('找不到所选版本')
        self.current_version_id = version_id


def project_path(path):
    path = Path(path).expanduser().resolve()
    return path / FILENAME if path.is_dir() else path


def read_project(path):
    path = project_path(path)
    project = Project.model_validate_json(path.read_bytes()).checked()
    # 相对引用始终相对于项目文件，重开不受当前工作目录影响。
    for version in project.versions:
        scan = Path(version.scan_directory)
        if not scan.is_absolute():
            version.scan_directory = str((path.parent / scan).resolve())
    return project


def write_project(project, path, *, overwrite=True):
    project.checked()
    path = project_path(path)
    if path.name != FILENAME:
        raise ValueError('项目文件须命名为' + FILENAME)
    if not path.parent.is_dir():
        raise ValueError('保存目录不存在，请先选择已有文件夹')
    if path.exists() and not overwrite:
        raise ValueError('此处已有项目，请打开它或选择其他目录')
    # 先完整写临时文件，再原子替换，失败时保留已有项目。
    descriptor, temporary = tempfile.mkstemp(prefix='.gv-project-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(project.model_dump(), stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(path)


def example_project(root):
    project = Project(name='公开示例项目')
    for label, note in [('A', '公开基准扫描'), ('B', '公开另一张图的扫描'), ('A-change', '公开改图扫描，用于与A比较')]:
        project.add_version(label, Path(root) / 'samples' / label, note)
    project.current_version_id = project.versions[0].id
    return project
