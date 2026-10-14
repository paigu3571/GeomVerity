# SPDX-License-Identifier: MPL-2.0
"""SYNTHETIC：重建不可编造闭合、合并不同房名或忽略内孔。"""
import unittest
from types import SimpleNamespace as S
from cst.model import Source,Geometry
from cst.recovery import reconstruct


def source(handle,native='TDbWall',layer='A-Wall'):
    return Source(drawing_hash='A'*64,handle=handle,stable_path=handle,raw_layer=layer,effective_layer=layer,normalized_layer=layer,
        native_dxf_name='TCH_WALL',native_class_name=native,block_path=[],xref_path=[],xref_hashes=[],wcs_transform=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.])


def geometry(coords):
    return Geometry.model_validate({'kind':'multi_path','is_closed':False,'is_exact':True,'extraction_method':'SYNTHETIC',
        'paths':[[{'x':float(x),'y':float(y),'z':0.0} for x,y in coords]],
        'bounds':{'min_x':float(min(x for x,y in coords)),'min_y':float(min(y for x,y in coords)),'min_z':0.0,
        'max_x':float(max(x for x,y in coords)),'max_y':float(max(y for x,y in coords)),'max_z':0.0,'is_valid':True}})


def fixture(open_gap=False,second_label=False,hole=False):
    ox,oy=3e10,4e9;shift=lambda p:[(ox+x,oy+y) for x,y in p]
    paths=[[(0,0),(8000,0),(8000,6000),(0,6000),(0,1000 if open_gap else 0)],[(8000,3000),(6000,3000)]]
    if hole:paths.append([(5000,4000),(6000,4000),(6000,5000),(5000,5000),(5000,4000)])
    walls=[S(primitive_id='wall'+str(i),source=source(str(i)),raw_geometry=geometry(shift(p)),is_semantic_candidate=True,
             adapter_role_hint='Wall',raw_properties={}) for i,p in enumerate(paths)]
    labels=[S(raw_text='配电房',source=source('TEXT','TDbText','A-Spac-Iden-Auto'),geometry=geometry(shift([(2000,2000)])))]
    if second_label:labels.append(S(raw_text='另一个配电房',source=source('TEXT2','TDbText','A-Spac-Iden-Auto'),geometry=geometry(shift([(3000,2000)]))))
    return S(primitives=walls),S(facts=labels),S(objects=[],drawing=S(sha256='A'*64))


class RecoveryTests(unittest.TestCase):
    def test_branch_and_large_coordinates_recover_without_new_walls(self):
        args=fixture();fact,obj,report,*_=reconstruct(*args,'配电房')
        self.assertAlmostEqual(report['area_m2'],48);self.assertEqual(report['added_wall_segments'],0)
        self.assertEqual(report['boundary_unsupported_length_mm'],0);self.assertEqual(report['contained_names'],['配电房'])
        self.assertEqual(obj.status,'review');self.assertFalse(obj.geometry.is_exact)
        self.assertEqual(fact.source_primitive_ids,['wall0']);self.assertFalse(report['text_moved'])
        self.assertEqual(obj.semantic_id,reconstruct(*fixture(),'配电房')[1].semantic_id)
    def test_real_gap_not_invented_closed(self):
        with self.assertRaisesRegex(ValueError,'未得到唯一'):reconstruct(*fixture(open_gap=True),'配电房')
    def test_multiple_room_names_not_merged(self):
        with self.assertRaisesRegex(ValueError,'多个房名'):reconstruct(*fixture(second_label=True),'配电房')
    def test_inner_hole_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError,'内孔'):reconstruct(*fixture(hole=True),'配电房')

    def test_non_electrical_room_general_recovery_does_not_guess_use(self):
        l1,l2,l3=fixture();l2.facts[0].raw_text='设备用房'
        fact,obj,report,*_=reconstruct(l1,l2,l3,'设备用房',handle='TEXT',general=True)
        self.assertEqual(obj.use_code,'UNKNOWN');self.assertEqual(report['area_m2'],48)

    def test_source_opening_closure_retains_handle_not_arbitrary_gap(self):
        l1,l2,l3=fixture(open_gap=True)
        l1.primitives.append(S(primitive_id='opening',source=source('DOOR','TDbOpening'),
            raw_geometry=geometry([(3e10,4e9),(3e10,4e9+1000)]),is_semantic_candidate=True,adapter_role_hint='Opening',raw_properties={}))
        fact,obj,report,*_=reconstruct(l1,l2,l3,'配电房',handle='TEXT',general=True)
        self.assertEqual(report['area_m2'],48);self.assertIn('opening',fact.source_primitive_ids)
        self.assertEqual(report['opening_boundary_handles'],['DOOR']);self.assertTrue(report['source_opening_paths_used'])
        self.assertEqual(report['added_wall_segments'],0)

    def test_small_gap_is_marked_not_closed(self):
        from cst.room_diagnostics import diagnose_label
        l1,l2,l3=fixture(open_gap=True);g=l1.primitives[0].raw_geometry
        g.paths[0][-1].y=4e9+50
        row=diagnose_label(l1,l2,l3,'配电房','TEXT','未得到唯一围合')
        self.assertTrue(any(r['length_mm']==50 for r in row['gap_candidates']))
        self.assertFalse(row['automatic_wall_added'])
        with self.assertRaisesRegex(ValueError,'未得到唯一'):reconstruct(l1,l2,l3,'配电房',general=True)

    def test_offset_text_has_candidate_but_is_not_moved(self):
        from cst.room_diagnostics import diagnose_label
        l1,l2,l3=fixture();l2.facts[0].geometry=geometry([(3e10-300,4e9+2000)])
        row=diagnose_label(l1,l2,l3,'配电房','TEXT','未得到唯一围合')
        self.assertEqual(row['reason_code'],'TEXT_POSITION_CANDIDATE')
        self.assertEqual(row['text_position_candidate']['distance_to_boundary_mm'],300)
        self.assertFalse(row['automatic_text_move']);self.assertEqual(row['point_wcs_mm'],[3e10-300,4e9+2000])

    def test_dictionary_unknown_room_is_target_but_door_tag_is_not(self):
        from cst.room_diagnostics import targets_and_issues
        l1,l2,l3=fixture();l3.findings=[]
        l2.facts[0].raw_text='男卫'
        self.assertEqual(targets_and_issues(l1,l2,l3)[0],[('男卫','TEXT')])
        l2.facts[0].raw_text='FM甲1222'
        self.assertEqual(targets_and_issues(l1,l2,l3)[0],[])
