# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
from pathlib import Path
from shutil import copy2
from setuptools import setup
from setuptools.command.build_py import build_py
class BuildWithRules(build_py):
    def run(self):
        super().run()
        for source in Path('rules').rglob('*.yaml'):
            target=Path(self.build_lib)/'cst/resources/rules'/source.relative_to('rules')
            target.parent.mkdir(parents=True,exist_ok=True);copy2(source,target)
setup(cmdclass={'build_py':BuildWithRules},options={'build':{'build_base':'.local/package-build'}})
