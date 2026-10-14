# SPDX-License-Identifier: MPL-2.0
import importlib.util,json,tempfile,unittest
from pathlib import Path
from cst.cloud import cloud,cloud_regions
@unittest.skipUnless(importlib.util.find_spec('ezdxf'),'可选DXF依赖未安装')
class CloudTests(unittest.TestCase):
    def test_synthetic_cloud_coordinates_and_trace_no_source_write(self):
        import ezdxf
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);source=d/'diff.json'
            record={'origin':'SYNTHETIC','geometry_units':'mm','changes':[{'id':'change_1','old':{'handle':'A'},'new':{'handle':'B'},'cloud_bounds':[[30000000000.,4000000000.,30000008000.,4000004000.]]}]}
            source.write_text(json.dumps(record));before=source.read_bytes()
            r=cloud(source,d/'cloud.dxf');self.assertEqual(source.read_bytes(),before);self.assertEqual(r['cloud_count'],1)
            doc=ezdxf.readfile(d/'cloud.dxf');self.assertEqual(doc.units,4)
            entity=next(iter(doc.modelspace()));self.assertEqual(entity.dxf.layer,'CST_CHANGE_CLOUD')
            self.assertEqual(doc.layers.get('CST_CHANGE_CLOUD').dxf.color,6)
            self.assertEqual(entity.dxf.const_width,0)
            self.assertEqual(entity.dxf.lineweight,25)
            pts=list(entity.get_points('xyb'));self.assertTrue(all(p[0]>29999999000 for p in pts));self.assertTrue(any(p[2]!=0 for p in pts))
            self.assertIn((1000,'old:A'),entity.get_xdata('CST_TRACE'))

class CloudRegionTests(unittest.TestCase):
    def test_contained_and_adjacent_details_merge_without_changing_records(self):
        changes=[{'id':'room','cloud_bounds':[[0,0,10000,6000]]},
                 {'id':'door','cloud_bounds':[[200,100,800,500]]},
                 {'id':'wall','cloud_bounds':[[10000,0,12000,6000]]},
                 {'id':'far','cloud_bounds':[[30000,0,31000,1000]]},
                 {'id':'derived','basis':'派生围合差异','cloud_bounds':[[0,0,50000,50000]]}]
        before=json.dumps(changes);regions=cloud_regions({'changes':changes})
        self.assertEqual(len(regions),2)
        self.assertEqual(regions[0]['bounds'],[0,0,12000,6000])
        self.assertEqual(set(regions[0]['change_ids']),{'room','door','wall'})
        self.assertEqual(json.dumps(changes),before)
