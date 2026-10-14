# SPDX-License-Identifier: MPL-2.0
import unittest
from types import SimpleNamespace as S
from cst.adjacency import between_segments

def seg(a,b):
    import math
    return a,b,math.dist(a,b)
C={'parallel_angle_degrees':1.0,'thickness_tolerance_mm':20.0,'min_overlap_m':0.5,'max_search_gap_mm':2000.0}
class AdjacencyTests(unittest.TestCase):
    def test_requires_same_wall_two_faces_and_overlap(self):
        a=seg((0,0),(4000,0));b=seg((4000,200),(0,200));w=S(semantic_id='wall',source=S(handle='AB'),status='review')
        faces=[(w,a),(w,b)]
        r=between_segments(a,b,faces,C);self.assertEqual(r[0]['wall_thickness_mm'],200)
        self.assertEqual(r[0]['overlap_mm'],4000)
        self.assertEqual(between_segments(a,b,[],C),[])
        self.assertEqual(between_segments(a,b,[(w,a)],C),[])
        self.assertEqual(between_segments(a,seg((3900,200),(4400,200)),faces,C),[])
        self.assertEqual(between_segments(a,seg((4000,600),(0,600)),faces,C),[])
    def test_rotated_large_coordinates_and_nonparallel(self):
        import math
        def tr(p):return (3e10+p[0]*math.cos(.7)-p[1]*math.sin(.7),4e9+p[0]*math.sin(.7)+p[1]*math.cos(.7))
        a=seg(tr((0,0)),tr((3000,0)));b=seg(tr((3000,300)),tr((0,300)))
        w=S(semantic_id='w',source=S(handle='H'),status='review')
        self.assertAlmostEqual(between_segments(a,b,[(w,a),(w,b)],C)[0]['wall_thickness_mm'],300,places=2)
        self.assertEqual(between_segments(a,seg(tr((0,100)),tr((3000,800))),[(w,a),(w,b)],C),[])
