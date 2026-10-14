# SPDX-License-Identifier: MPL-2.0
import unittest
from types import SimpleNamespace as S
from cst.references import ReferenceIndex
class ReferenceTests(unittest.TestCase):
 def test_shared_wall_handle_is_not_room_identity_or_cad_room_target(self):
  def source(handle,derived=False):return S(handle=handle,stable_path=('derived:wall-loop/'+handle if derived else 'BLOCK/'+handle),native_dxf_name='DERIVED' if derived else 'TEXT',block_path=[])
  p=S(primitive_id='text_1',raw_text='水泵房',source=source('TEXT1'))
  index=ReferenceIndex(S(primitives=[p]),S(facts=[]))
  room=S(type='space',semantic_id='ROOM1',source=source('SHARED_WALL',True),geometry=S(is_closed=False,paths=[]),evidence=[S(kind='spatial_text',source_handle='TEXT1',value='水泵房')])
  ref=index.for_object(room)
  self.assertEqual(ref['space_id'],'ROOM1');self.assertEqual(ref['cad_target']['handle'],'TEXT1')
  self.assertIn('非房间编号',ref['geometry_reference']['type']);self.assertNotEqual(ref['cad_target']['handle'],ref['geometry_reference']['handle'])
