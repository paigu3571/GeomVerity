# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import tempfile
import unittest
from cst.project import Project, FILENAME, read_project, write_project, example_project


class ProjectTests(unittest.TestCase):
    def test_round_trip_versions_notes_and_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project(name='SYNTHETIC项目')
            first = project.add_version('旧版', folder, '原始记录')
            project.add_version('新版', folder, '待复核')
            project.select(first.id)
            path = write_project(project, folder)
            reopened = read_project(path)
            self.assertEqual(project.model_dump(), reopened.model_dump())
            with self.assertRaisesRegex(ValueError, '已有项目'):
                write_project(project, folder, overwrite=False)
            self.assertEqual(project.model_dump(), read_project(folder).model_dump())

    def test_invalid_reference_and_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project(name='SYNTHETIC项目')
            first = project.add_version('旧版', folder)
            with self.assertRaisesRegex(ValueError, '所选版本'):
                project.select('missing')
            project.versions.append(first)
            with self.assertRaisesRegex(ValueError, '重复'):
                write_project(project, folder)
            self.assertFalse((Path(folder) / FILENAME).exists())

    def test_relative_scan_resolves_from_project_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / FILENAME
            path.write_text(json.dumps({'name': 'SYNTHETIC', 'versions': [{'id': 'v1', 'name': '旧版', 'scan_directory': 'scans'}], 'current_version_id': 'v1'}), encoding='utf-8')
            project = read_project(path)
            self.assertEqual(project.versions[0].scan_directory, str((path.parent / 'scans').resolve()))

    def test_missing_scan_does_not_create_or_modify_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / 'missing'
            with self.assertRaisesRegex(ValueError, '目录不存在'):
                Project(name='SYNTHETIC').add_version('旧版', missing)
            self.assertFalse(missing.exists())

    def test_public_example_has_three_versions_without_writing_to_samples(self):
        project = example_project(Path(__file__).resolve().parents[2])
        self.assertEqual([v.name for v in project.versions], ['A', 'B', 'A-change'])
        self.assertEqual(project.current_version_id, project.versions[0].id)
