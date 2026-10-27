# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cst.desktop import Workbench, create_server

ROOT = Path(__file__).resolve().parents[2]


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bridge = Workbench(self.temp.name, root=ROOT)
        self.server = create_server(self.bridge)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = __import__('urllib.parse',fromlist=['urlunsplit']).urlunsplit(('http', f'127.0.0.1:{self.server.server_port}', '', '', ''))

    def test_demo_switches_to_compared_public_new_version_and_preserves_old_work(self):
        old, _, new = self.bridge.project.versions
        self.bridge.project.select(old.id)
        comparison = {'display': {'old_version': {'id': old.id}, 'new_version': {'id': new.id}}, 'path': 'unused-test-diff'}
        self.bridge.comparison = comparison
        original = {'document': {'original_text': '未保存的旧版文字'}}
        self.bridge.claims_workspaces[old.id] = original
        self.bridge.engineering_notes={'version_id':new.id,'text':'SYNTHETIC自贴意见','origin':'你粘贴的工程意见'}
        doc = json.loads((ROOT / 'python/cst/assets/demo/claims.json').read_bytes())
        with patch('cst.workbench_claims.import_claims', return_value={'document': doc, 'history': []}) as imported, patch('cst.workbench_claims.save_claims', return_value={'document': doc, 'history': [], 'report': {'items': []}}) as checked:
            self.bridge.perform('claims_demo', {})
        self.assertEqual(self.bridge.project.current_version_id, new.id)
        self.assertIs(self.bridge.comparison, comparison)
        self.assertEqual(self.bridge.claims_workspaces[old.id], original)
        self.assertIn(new.id, self.bridge.claims_workspaces)
        self.assertIsNone(self.bridge.engineering_notes)
        self.assertEqual(Path(imported.call_args.args[0]), Path(new.scan_directory))
        self.assertEqual(Path(checked.call_args.args[0]), Path(new.scan_directory))
        self.assertFalse(self.bridge.review_path().exists())

    def test_demo_requires_forward_public_comparison_before_switching(self):
        old, other, new = self.bridge.project.versions
        for pair in [None, (new, old), (other, new), (old, other)]:
            self.bridge.comparison = None if pair is None else {'display': {'old_version': {'id': pair[0].id}, 'new_version': {'id': pair[1].id}}}
            self.bridge.project.select(old.id)
            with self.subTest(pair=pair):
                with self.assertRaisesRegex(ValueError, '换版.*比较A和A-change'):
                    self.bridge.perform('claims_demo', {})
                self.assertEqual(self.bridge.project.current_version_id, old.id)
                self.assertFalse(self.bridge.claims_workspaces)

    def test_synthetic_review_requires_explicit_development_mode(self):
        for name in ('review_write', 'review_transfer'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, '仅允许在开发模式'):
                    self.bridge.perform(name, {'synthetic': True})
        self.assertFalse(self.bridge.state()['development'])
        dev = Workbench(self.temp.name, root=ROOT, development=True)
        self.assertTrue(dev.state()['development'])
        with self.assertRaisesRegex(ValueError, '已核对旧、新来源'):
            dev.perform('review_transfer', {'synthetic': True})
        self.assertFalse(self.bridge.review_path().exists())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        head = {'X-GV-Token': self.bridge.token, 'Content-Type': 'application/json'}
        head.update(headers or {})
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=head)
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def action(self, operation, **args):
        job = self.request('/api/action', {'name': operation, 'args': args})
        end = time.monotonic() + 3
        while time.monotonic() < end:
            state = self.request('/api/state')
            if state['job']['id'] == job['id'] and state['job']['status'] != 'running':
                return state
            time.sleep(.02)
        self.fail('本机工作台操作超时')

    def test_same_page_loads_and_session_is_required(self):
        with urlopen(self.base + '/', timeout=3) as response:
            self.assertIn('项目与体检', response.read().decode('utf-8'))
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/api/state', timeout=3)
        self.assertEqual(error.exception.code, 404)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/action', {'name': 'example'}, {'Origin': 'https://example.invalid'})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError):
            self.request('/api/state', headers={'Host': 'example.invalid'})

    def test_create_add_select_save_and_reopen_via_http(self):
        state = self.action('create', name='SYNTHETIC项目', path=self.temp.name)
        self.assertEqual(state['job']['status'], 'done')
        state = self.action('add', name='旧版', directory=str(ROOT / 'samples/A'), note='公开')
        first = state['project']['current_version_id']
        state = self.action('add', name='新版', directory=str(ROOT / 'samples/A-change'))
        state = self.action('select', id=first)
        saved = state['project']
        self.assertEqual(self.action('save', path=self.temp.name)['job']['status'], 'done')
        self.action('example')
        reopened = self.action('open', path=self.temp.name)
        self.assertEqual(reopened['project'], saved)

    def test_error_is_visible_and_next_action_recovers(self):
        state = self.action('open', path=str(Path(self.temp.name) / 'missing.json'))
        self.assertEqual(state['job']['status'], 'error')
        self.assertEqual(state['project']['name'], '公开示例项目')
        self.assertEqual(self.action('example')['job']['status'], 'done')

    def test_long_task_keeps_state_available_and_rejects_overlap(self):
        entered, release = threading.Event(), threading.Event()
        original = self.bridge.perform
        def slow(name, args):
            entered.set()
            release.wait(3)
            original(name, args)
        with patch.object(self.bridge, 'perform', side_effect=slow):
            self.request('/api/action', {'name': 'example'})
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.request('/api/state')['job']['status'], 'running')
                with self.assertRaises(HTTPError) as error:
                    self.request('/api/action', {'name': 'example'})
                self.assertEqual(error.exception.code, 400)
            finally:
                release.set()
            end = time.monotonic() + 3
            while self.bridge.state()['job']['status'] == 'running' and time.monotonic() < end:
                time.sleep(.02)
            self.assertEqual(self.bridge.state()['job']['status'], 'done')


    def test_version_switch_clears_previous_view_and_query_serves_generated_file(self):
        viewer = Path(self.temp.name) / 'view.html'
        viewer.write_text('<p>SYNTHETIC current version</p>', encoding='utf-8')
        self.bridge.viewer = viewer
        route = self.bridge.state()['viewer']
        with urlopen(self.base + route, timeout=3) as response:
            self.assertIn(b'SYNTHETIC current version', response.read())
        project = self.bridge.state()['project']
        self.action('select', id=project['versions'][1]['id'])
        self.assertIsNone(self.bridge.state()['viewer'])

    def test_health_endpoint_uses_shared_inventory_and_clears_on_open(self):
        with patch('cst.inventory.inspect_scan',return_value={'tone':'warning','room_count':0}) as inspect:
            state=self.action('inspect')
        self.assertEqual(inspect.call_count,3)
        self.assertEqual(len(state['health']),3)
        self.assertTrue(all(h['tone']=='warning' for h in state['health'].values()))
        self.assertEqual(self.action('example')['health'],{})

    def test_native_folder_bridge_handles_cancel_and_selection_without_io(self):
        import sys
        from types import SimpleNamespace
        from cst.desktop import NativeDialogs
        dialog=NativeDialogs()
        self.assertEqual([name for name in dir(dialog) if not name.startswith('_')],['choose_folder'])
        window=SimpleNamespace(create_file_dialog=lambda mode:[])
        dialog._window=window
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER='SYNTHETIC_FOLDER'))}):
            self.assertTrue(dialog.choose_folder()['cancelled'])
            window.create_file_dialog=lambda mode:[self.temp.name]
            self.assertEqual(dialog.choose_folder()['path'],self.temp.name)
