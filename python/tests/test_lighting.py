# SPDX-License-Identifier: MPL-2.0
import unittest,tempfile,math
from pathlib import Path
from types import SimpleNamespace as S
from shapely.geometry import Polygon,Point,LineString
from shapely.strtree import STRtree
from cst.lighting import layout_room,write_dxf,compare_groups
from cst.adjacency import segments
G={'approved':True,'id':'LIGHT-DEMO-001','rule_version':'0.1.0','min_rectangle_ratio':.95,'wall_clearance_m':.6,'max_spacing_m':3.0,'strategy':'rectangular_grid'}
W={'approved':True,'id':'LIGHT-DEMO-002','rule_version':'0.1.0','wall_clearance_m':0,'max_spacing_m':2.0,'strategy':'wall_surface'}
def room(points):return S(geometry=S(is_closed=True,paths=[[S(x=x,y=y) for x,y in points]]))
def context(r,openings=None):
    rows=[(S(semantic_id='wall_'+str(i),source=S(handle='W'+str(i))),seg) for i,seg in enumerate(segments(r))]
    return rows,STRtree([LineString(s[:2]) for _,s in rows]),openings or []
class LightingTests(unittest.TestCase):
    def test_rotated_grid_spacing_and_true_wall_clearance(self):
        angle=.7
        points=[(3e10+x*math.cos(angle)-y*math.sin(angle),4e9+x*math.sin(angle)+y*math.cos(angle)) for x,y in [(0,0),(9000,0),(9000,6000),(0,6000)]]
        result=layout_room(room(points),G,W,'grid');self.assertGreater(len(result['points']),0)
        self.assertLessEqual(result['grid_spacing_x_mm'],3000);self.assertLessEqual(result['grid_spacing_y_mm'],3000)
        poly=Polygon(points)
        for p in result['points']:
            q=Point(p['x'],p['y']);self.assertTrue(poly.contains(q));self.assertGreaterEqual(poly.boundary.distance(q),599.999)
    def test_irregular_keeps_grid_gate_and_uses_separate_wall_rule(self):
        r=room([(0,0),(8000,0),(8000,3000),(3000,3000),(3000,8000),(0,8000)])
        self.assertEqual(layout_room(r,G,W,'grid')['result'],'异形房间需人工布置')
        out=layout_room(r,G,W,'auto',context(r));self.assertEqual(out['rule_id'],'LIGHT-DEMO-002');self.assertTrue(out['points'])
        poly=Polygon([(p.x,p.y) for p in r.geometry.paths[0]])
        for p in out['points']:
            self.assertAlmostEqual(poly.boundary.distance(Point(p['x'],p['y'])),150,places=3)
            self.assertLessEqual(poly.boundary.distance(Point(p['wall_anchor_x'],p['wall_anchor_y'])),.001)
            self.assertTrue(poly.contains(Point(p['x'],p['y'])))
        self.assertFalse(layout_room(r,G,W,'wall')['points'])
        self.assertFalse(layout_room(room([(0,0),(1000,0),(1000,1000),(0,1000)]),G,W)['points'])
    def test_wall_lights_exclude_door_span_and_keep_wall_evidence(self):
        # SYNTHETIC：门洞横跨底墙，门边各300mm应不落点；没有墙不得假装有安装面。
        r=room([(0,0),(8000,0),(8000,4000),(0,4000)])
        opening=S(source=S(handle='DOOR'),geometry=S(bounds=S(min_x=2500,min_y=-100,max_x=4500,max_y=200)))
        out=layout_room(r,G,W,'wall',context(r,[opening]));self.assertTrue(out['points'])
        for p in out['points']:
            self.assertTrue(p['mounting_wall_handle'])
            self.assertFalse(2200<=p['x']<=4800 and -400<=p['y']<=500)
        self.assertEqual(out['excluded_opening_handles'],['DOOR'])
    def test_dxf_block_attributes_and_xdata_and_invalidation(self):
        import ezdxf
        group={'group_id':'g','room_semantic_id':'old','room_name':'SYNTHETIC','room_source_handles':['ABC'],
               'rule_id':'LIGHT-DEMO-001','rule_version':'0.1.0','input_sha256':'a'*64,'state':'生成候选',
               'points':[{'id':'lamp','x':3e10,'y':4e9,'z':0.0}]}
        newer={**group,'room_semantic_id':'new','points':[{'id':'lamp2','x':3e10+2000,'y':4e9,'z':0.0}]}
        new={'groups':[newer]};rows=compare_groups({'groups':[group]},new,{'old':'new'},[{'old':{'id':'old'},'kinds':['几何变化']}])
        self.assertIn('失效',rows[0]['state']);self.assertEqual(new['invalidated_groups'][0]['state'],'失效')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lights.dxf';r=write_dxf(new,p);self.assertEqual(r['candidate_count'],1);self.assertEqual(r['invalid_count'],1)
            doc=ezdxf.readfile(p);ents=list(doc.modelspace().query('INSERT'));self.assertEqual(len(ents),2)
            self.assertEqual(ents[0].get_attrib_text('input_sha256'),'a'*64)
            self.assertTrue(any(t.value=='room_source_handles=ABC' for t in ents[0].get_xdata('CST_TRACE')))
            self.assertAlmostEqual(ents[0].dxf.insert.x,3e10+2000)
    def test_unchanged_room_keeps_group(self):
        g={'group_id':'g','room_semantic_id':'s','room_name':'SYNTHETIC','room_source_handles':['AB'],'points':[{'id':'p'}]}
        n={'groups':[g]};self.assertEqual(compare_groups({'groups':[g]},n,{'s':'s'},[])[0]['state'],'保留候选灯组')

    def test_new_snapshot_ids_do_not_invalidate_identical_lamp_positions(self):
        g={'group_id':'old','room_semantic_id':'s','room_name':'SYNTHETIC','room_source_handles':['AB'],
           'rule_id':'R','rule_version':'1','points':[{'id':'oldlamp','x':100.,'y':200.,'z':0.}]}
        n={'groups':[{**g,'group_id':'new','room_semantic_id':'n','points':[{'id':'newlamp','x':100.,'y':200.,'z':0.}]}]}
        rows=compare_groups({'groups':[g]},n,{'s':'n'},[{'old':{'id':'s'},'kinds':['来源对象变化']}])
        self.assertEqual(rows[0]['state'],'保留候选灯组');self.assertEqual(n['invalidated_groups'],[])
