# SPDX-License-Identifier: MPL-2.0
import unittest,math,tempfile,hashlib,yaml
from pathlib import Path
from types import SimpleNamespace as S
from cst.l4 import envelope_dimensions,shared_boundary_mm,evidence_chain,opening_candidates,read_r1_confirmations

def geom(points,closed=True):return S(is_closed=closed,paths=[[S(x=x,y=y,z=0.0) for x,y in points]])
class L4Tests(unittest.TestCase):
    def test_rotated_large_coordinate_dimensions(self):
        a=0.7;points=[(3e10+x*math.cos(a)-y*math.sin(a),4e9+x*math.sin(a)+y*math.cos(a)) for x,y in [(0,0),(8000,0),(8000,3000),(0,3000)]]
        self.assertAlmostEqual(envelope_dimensions(geom(points))['long_side_m'],8,places=5)
        self.assertIsNone(envelope_dimensions(geom(points,False)))
    def test_common_boundary_not_point_contact_or_gap(self):
        a=geom([(0,0),(1000,0),(1000,1000),(0,1000)])
        self.assertEqual(shared_boundary_mm(a,geom([(1000,0),(2000,0),(2000,1000),(1000,1000)])),1000)
        self.assertEqual(shared_boundary_mm(a,geom([(1000,1000),(2000,1000),(2000,2000),(1000,2000)])),0)
        self.assertEqual(shared_boundary_mm(a,geom([(1010,0),(2010,0),(2010,1000),(1010,1000)])),0)
    def test_broken_chain_visible(self):
        obj=S(semantic_id='s',source=S(handle='H'),evidence=[S(kind='geometry_fact',value='missing')])
        self.assertFalse(evidence_chain(obj,{}, {})['chains'][0]['complete'])

    def test_opening_overlap_and_far_candidates(self):
        room=S(geometry=geom([(0,0),(8000,0),(8000,4000),(0,4000)]))
        def opening(id,handle,x,y,path):
            return S(semantic_id=id,source=S(drawing_hash='draw',handle=handle,xref_hashes=[],stable_path=path),geometry=geom([(x,y),(x+100,y+100)],False))
        a=opening('a','H',100,0,'block1/H');alias=opening('alias','H',100,0,'block2/H')
        far=opening('far','H',100,1000,'other/H')
        result=opening_candidates(room,[a,alias,far])
        self.assertEqual(result['raw_opening_relation_count'],3)
        self.assertEqual(result['coincident_opening_count'],2)
        self.assertEqual(result['candidate_opening_count'],1)
        self.assertEqual(result['opening_candidate_audit'][0]['object_ids'],['a','alias'])
    def test_confirmation_not_reused_for_changed_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);source=d/'building-semantics.v1.json';source.write_bytes(b'scan1')
            record={'schema_version':'r1-confirmations.v1','origin':'ENGINEER_REVIEW','drawing_sha256':'d1','snapshot_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'reviewed_by':'工程师','reviewed_date':'2026-10-12','screenshot_sha256':[],'rooms':[{'object_id':'r','name':'配电房','net_length_gt_7':True,'entrance_count':2}]}
            (d/'l4_confirmations.yaml').write_text(yaml.safe_dump(record,allow_unicode=True),encoding='utf-8')
            self.assertIn('r',read_r1_confirmations(d,'d1')[0])
            self.assertEqual(read_r1_confirmations(d,'d2')[0],{})
            source.write_bytes(b'scan2');self.assertEqual(read_r1_confirmations(d,'d1')[0],{})
