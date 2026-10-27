# SPDX-License-Identifier: MPL-2.0
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('external_prepare',ROOT/'scripts/generate_external_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ExternalPrepareTests(unittest.TestCase):
    def test_refuses_missing_cleanup_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            (directory/'manifest.json').write_text('{"sanitized":false}')
            with self.assertRaisesRegex(ValueError,'公开样例'):module.check_public(directory)
            (directory/'manifest.json').write_text('{"sanitized":true,"files":{}}')
            (directory/'cad-primitives.v1.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'清理清单'):module.check_public(directory)

    def test_prepare_is_offline_and_not_a_real_response(self):
        delta={'old_hash':'a','new_hash':'b','change_count':0,'changes':[]}
        def diff(old,new,output):
            output.mkdir();(output/'diff.json').write_text(json.dumps(delta))
        with tempfile.TemporaryDirectory() as folder, patch.object(module,'check_public',return_value={'SYNTHETIC':'hash'}), patch.object(module.api,'diff',side_effect=diff), patch('httpx.Client',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('os.getenv',side_effect=AssertionError('NO_KEY_READ')):
            result=module.prepare(folder)
            self.assertFalse(result['network_used']);self.assertEqual(result['stage'],'PREPARED_NOT_GENERATED')
            requests=[json.loads((Path(folder)/name).read_bytes()) for name in result['proposed_requests']]
            self.assertEqual(len(requests),3)
            self.assertTrue(all('tools' not in r and 'response' not in r for r in requests))
            with self.assertRaisesRegex(ValueError,'已有准备记录'):module.prepare(folder)

    def test_approved_generation_preserves_raw_response_and_has_no_tools_or_secret_in_files(self):
        import httpx
        from unittest.mock import MagicMock
        delta={'old_hash':'a','new_hash':'b','change_count':0,'changes':[]}
        def diff(old,new,output):
            output.mkdir();(output/'diff.json').write_text(json.dumps(delta))
        raw=b'{"model":"SYNTHETIC_mock_provider","choices":[{"finish_reason":"stop","message":{"content":"SYNTHETIC response"}}]}'
        response=httpx.Response(200,content=raw,request=httpx.Request('POST','https://example.invalid'))
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'check_public',return_value={'SYNTHETIC':'hash'}),patch.object(module.api,'diff',side_effect=diff):
            module.prepare(folder)
            client=MagicMock();client.__enter__.return_value=client;client.post.return_value=response
            with patch.object(module.os,'getenv',return_value='SYNTHETIC_SECRET'),patch.object(module.httpx,'Client',return_value=client):
                result=module.generate(folder,'SYNTHETIC测试批准，非真实样本')
                self.assertEqual(result['complete_count'],3)
                self.assertEqual(client.post.call_count,3)
                self.assertTrue(all('tools' not in call.kwargs['json'] for call in client.post.call_args_list))
                self.assertEqual((Path(folder)/'sample-1/response.raw.json').read_bytes(),raw)
                for path in Path(folder).rglob('*'):
                    if path.is_file():self.assertNotIn(b'SYNTHETIC_SECRET',path.read_bytes())
                with self.assertRaisesRegex(ValueError,'已存在'):module.generate(folder,'SYNTHETIC测试批准')
                self.assertEqual(client.post.call_count,3)

    def test_frozen_request_tampering_is_rejected_before_key_or_network(self):
        delta={'old_hash':'a','new_hash':'b','change_count':0,'changes':[]}
        def diff(old,new,output):
            output.mkdir();(output/'diff.json').write_text(json.dumps(delta))
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'check_public',return_value={}),patch.object(module.api,'diff',side_effect=diff):
            module.prepare(folder)
            path=Path(folder)/'proposed-request-1.json';payload=json.loads(path.read_bytes());payload['tools']=[];path.write_text(json.dumps(payload))
            with patch.object(module.os,'getenv',side_effect=AssertionError('NO_KEY_READ')),patch.object(module.httpx,'Client',side_effect=AssertionError('NO_NETWORK')):
                with self.assertRaisesRegex(ValueError,'请求与已批准'):module.generate(folder,'SYNTHETIC批准')
