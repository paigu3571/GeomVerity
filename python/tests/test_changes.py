# SPDX-License-Identifier: MPL-2.0
"""SYNTHETIC变更与旧确认继承边界，不是实际变更检出率。"""
import unittest
from types import SimpleNamespace as S
from cst.changes import compare_objects,inherit_reviews,impact_for,conclusion_changes
from cst.l4 import RoomConfirmation

def obj(id,handle,name='配电室',x=0,type='space'):
    points=[(x,0),(x+8000,0),(x+8000,4000),(x,4000)]
    return S(semantic_id=id,type=type,raw_label=name,use_code='ELECTRICAL_ROOM',classification='',status='review',
        source=S(handle=handle,block_path=[],xref_path=[]),
        geometry=S(kind='polygon',is_closed=True,is_exact=True,paths=[[S(x=float(x),y=float(y),z=0.) for x,y in points]]))
def data(objects):return S(objects=objects,drawing=S(geometry_units='mm'))

class ChangeTests(unittest.TestCase):
    def test_handle_tracks_geometry_and_name_change_plus_add_delete(self):
        a=obj('old','A');b=obj('new','A','配电房',10)
        c,m,u,w=compare_objects(data([a,obj('gone','B',x=50000)]),data([b,obj('add','C',x=80000)]))
        self.assertEqual(m['old'],'new');self.assertEqual(len(c),3)
        self.assertEqual(set(c[0]['kinds']),{'几何变化','名称或用途变化'})
        self.assertEqual({x['kinds'][0] for x in c[1:]},{'新增','删除'})
    def test_room_overlap_auxiliary_and_ambiguous_not_forced(self):
        c,m,u,w=compare_objects(data([obj('a','A')]),data([obj('b','B',x=50)]))
        self.assertEqual(m,{'a':'b'});self.assertIn('来源对象变化',c[0]['kinds'])
        c,m,u,w=compare_objects(data([obj('a','A')]),data([obj('b','B'),obj('c','C')]))
        self.assertEqual(m,{})
    def test_instance_handle_disambiguation(self):
        a=obj('a','A');b=obj('b','A');b.source.block_path=['BLOCK2:X']
        c,m,u,w=compare_objects(data([a,b]),data([a,b]))
        self.assertEqual(c,[]);self.assertEqual(len(m),2)
    def test_renumbered_handle_and_renamed_room_use_geometry_not_false_add_delete(self):
        a=obj('old','A',name='设备用房');b=obj('new','B',name='水泵房')
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'old':'new'})
        self.assertEqual(set(c[0]['kinds']),{'名称或用途变化','来源对象变化'})
        self.assertFalse(u)
    def test_grid_rounding_does_not_turn_microscopic_coordinate_noise_into_add_delete(self):
        a=obj('old','A',type='opening',x=30000000000.000499)
        b=obj('new','B',type='opening',x=30000000000.000503)
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'old':'new'});self.assertEqual(c[0]['kinds'],['来源对象变化'])
    def test_multipath_noding_noise_is_not_a_deleted_and_added_door(self):
        a=obj('a','A',type='opening',x=30000000000.)
        b=obj('b','B',type='opening',x=30000000000.00001)
        for o in (a,b):
            o.geometry.is_closed=False;o.geometry.kind='multi_path'
            o.geometry.paths.append([S(x=30000000000.,y=2000.,z=0.),S(x=30000008000.,y=2000.,z=0.)])
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'a':'b'});self.assertEqual(c[0]['kinds'],['来源对象变化'])
    def test_large_wcs_multiline_empty_buffer_does_not_hide_equal_geometry(self):
        a=obj('a','A',type='opening',x=30000000000.)
        b=obj('b','B',type='opening',x=30000000000.00001)
        for o in (a,b):
            o.geometry.is_closed=False;o.geometry.kind='multi_path'
            for pa in o.geometry.paths:
                for pt in pa:pt.y+=4000000000.
            o.geometry.paths.append([S(x=30000000000.,y=4000002000.,z=0.),S(x=30000008000.,y=4000002000.,z=0.)])
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'a':'b'});self.assertEqual(c[0]['kinds'],['来源对象变化'])
    def test_invalid_closed_cad_outline_still_matches_unchanged_raw_lines(self):
        a=obj('a','A',type='wall');b=obj('b','B',type='wall')
        for o in (a,b):o.geometry.paths=[[S(x=x,y=y,z=0.) for x,y in [(0.,0.),(8000.,4000.),(0.,4000.),(8000.,0.)]]]
        a.source.block_path=['OLD:X'];b.source.block_path=['NEW:X']
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'a':'b'});self.assertEqual(c[0]['kinds'],['来源对象变化'])
    def test_room_label_identity_precedes_changed_contour_anchor(self):
        a=obj('a','A');b=obj('b','B','配电房',100)
        for o in (a,b):o.evidence=[S(code='ROOM_LABEL_CONTAINED_TEXT',source_handle='TEXT')]
        c,m,u,w=compare_objects(data([a]),data([b]))
        self.assertEqual(m,{'a':'b'});self.assertEqual(c[0]['match_method'],'unique_room_label_evidence_handle')
    def test_review_inheritance_requires_same_room_and_door_set(self):
        f={'rule_id':'R1','object_ids':['r'],'object_name':'配电室','engineer_reviewed':{'reviewed_by':'SYNTHETIC'},'source_handles':['A'],'values':{'candidate_opening_ids':['d']}}
        n={'rule_id':'R1','object_ids':['nr'],'values':{'candidate_opening_ids':['nd']}}
        f['decision']={'id':'old','rule':{'sha256':'R'},'engineer':{'confirmed_by':'SYNTHETIC'},'inputs':[{'object_id':i,'content_fingerprint':i,'source_identity_sha256':i} for i in ('r','d')],'confirmation_scope':{'kind':'r1_input_conditions','candidate_opening_ids':['d']}}
        from copy import deepcopy
        n['decision']=deepcopy(f['decision']);n['decision']['id']='new'
        for item in n['decision']['inputs']:item['object_id']={'r':'nr','d':'nd'}[item['object_id']]
        n['decision']['confirmation_scope']['candidate_opening_ids']=['nd']
        confirmed=RoomConfirmation(object_id='r',name='配电室',net_length_gt_7=True,entrance_count=2)
        inherited,records=inherit_reviews([f],[n],{'r':'nr','d':'nd'},{'r','d'},{'r':(confirmed,S())})
        self.assertIn('nr',inherited);self.assertEqual(records[0]['state'],'继承')
        for unchanged,doors in [({'r'},['changed']),({'r','d'},['nd','newdoor'])]:
            n['values']['candidate_opening_ids']=doors
            n['decision']['confirmation_scope']['candidate_opening_ids']=doors
            inherited,records=inherit_reviews([f],[n],{'r':'nr','d':'nd'},unchanged,{'r':(confirmed,S())})
            self.assertFalse(inherited);self.assertIn('失效',records[0]['state'])
    def test_far_change_no_impact_and_in_room_change_hits(self):
        room=obj('r','R');far=obj('far','F',x=50000);inside=obj('inside','I',x=100)
        uses={s:{'r':{'category':'DISTRIBUTION_ROOM'}} for s in ['old','new']}
        for o,expected in [(far,'限定范围内未发现影响候选'),(inside,'影响候选，需复核')]:
            d=data([room,o]);change={'old':{'id':o.semantic_id},'new':None}
            self.assertEqual(impact_for(change,d,d,uses)['result'],expected)
    def test_conclusions_and_confirmation_loss_are_not_hidden(self):
        a={'id':'a','rule_id':'R1','object_ids':['r'],'result':'通过','input_confidence':'输入待复核'}
        b={**a,'id':'b','object_ids':['nr'],'result':'不通过'}
        self.assertEqual(conclusion_changes([a],[b],{'r':'nr'})[0]['change'],'由通过变不通过')
        b['result']='无法判定'
        row=conclusion_changes([a],[b],{'r':'nr'})[0]
        self.assertEqual(row['new_result'],'无法判定');self.assertNotEqual(row['change'],'不变')

    def test_missing_referenced_object_does_not_crash_or_assert_no_impact(self):
        d=data([])
        out=impact_for({'old':{'id':'missing'},'new':None},d,d,{'old':{},'new':{}})
        self.assertEqual(out['result'],'无法判定影响')

    def test_geometry_cache_is_scoped_and_does_not_confuse_reused_ids(self):
        from unittest.mock import patch
        from cst.changes import shape,geometry_session,_shape
        a=obj('same','A',x=0);b=obj('same','A',x=100)
        with patch('cst.changes._shape',wraps=_shape) as build:
            with geometry_session():
                first=shape(a);self.assertIs(shape(a),first)
                self.assertNotEqual(shape(b).bounds,first.bounds)
                self.assertEqual(build.call_count,2)
            with geometry_session():shape(a)
            self.assertEqual(build.call_count,3)
