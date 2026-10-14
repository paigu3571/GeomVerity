# SPDX-License-Identifier: MPL-2.0
"""区分空间标识、文字定位与围合参考图元；Handle与实例路径共同表示来源。"""
from collections import defaultdict
from shapely.geometry import Polygon,Point

class ReferenceIndex:
    def __init__(self,l1,l2):
        self.by_handle=defaultdict(list)
        for p in l1.primitives:self.by_handle[p.source.handle].append(p)
        self.facts={f.geometry_id:f for f in l2.facts}

    def for_object(self,obj):
        derived=obj.source.stable_path.startswith('derived:') or obj.source.native_dxf_name=='DERIVED'
        labels=[]
        polygon=Polygon([(p.x,p.y) for p in obj.geometry.paths[0]]) if obj.geometry.is_closed and obj.geometry.paths else None
        for e in obj.evidence:
            if e.kind!='spatial_text':continue
            matches=[p for p in self.by_handle[e.source_handle] if p.raw_text==e.value]
            if len(matches)>1 and polygon is not None and polygon.is_valid:
                matches=[p for p in matches if p.raw_geometry.paths and polygon.buffer(5).covers(Point(p.raw_geometry.paths[0][0].x,p.raw_geometry.paths[0][0].y))]
            for p in matches:
                labels.append({'type':'房名文字Handle','handle':p.source.handle,'primitive_id':p.primitive_id,'stable_path':p.source.stable_path,'outer_block_handle':p.source.block_path[0].split(':')[0] if p.source.block_path else None,'instance_path':p.source.block_path})
        direct={'type':'围合参考墙Handle（非房间编号）' if derived else 'CAD原生对象Handle','handle':obj.source.handle,'stable_path':obj.source.stable_path}
        target=labels[0] if len(labels)==1 else direct if not derived else None
        return {'space_id':obj.semantic_id,'space_id_type':'程序空间ID' if obj.type in ('space','shaft','zone') else '程序对象ID','room_texts':labels,'geometry_reference':direct,'cad_target':target,'cad_target_state':'嵌套对象定位外层块' if target and target.get('outer_block_handle') else '可定位源对象' if target else '缺少唯一文字来源；在查看器按轮廓定位'}
