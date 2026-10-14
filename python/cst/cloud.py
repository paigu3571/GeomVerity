# SPDX-License-Identifier: MPL-2.0
"""独立变更云线DXF，仅输出新文件，不打开或修改源DWG。"""
import json
from pathlib import Path

def cloud_regions(result, gap_mm=1400):
    """仅合并显示范围；原变化记录、几何和判定保持不动。"""
    regions=[]
    for change in result['changes']:
        if change.get('basis','').startswith('派生') or not change.get('cloud_bounds'):
            continue
        boxes=change['cloud_bounds']
        bounds=[min(b[0] for b in boxes),min(b[1] for b in boxes),
                max(b[2] for b in boxes),max(b[3] for b in boxes)]
        regions.append({'bounds':bounds,'change_ids':[change['id']]})
    # 外框相交或云线留白相碰时只保留一个外框，避免大小圈叠加。
    merged=True
    while merged:
        merged=False
        for i,a in enumerate(regions):
            for j in range(i+1,len(regions)):
                b=regions[j];x=a['bounds'];y=b['bounds']
                if x[0]<=y[2]+gap_mm and y[0]<=x[2]+gap_mm and x[1]<=y[3]+gap_mm and y[1]<=x[3]+gap_mm:
                    a['bounds']=[min(x[0],y[0]),min(x[1],y[1]),max(x[2],y[2]),max(x[3],y[3])]
                    a['change_ids'].extend(b['change_ids']);regions.pop(j);merged=True;break
            if merged:break
    for i,region in enumerate(regions):
        region['id']=f'cloud_region_{i+1}'
    return regions

def cloud(diff_file,output='dist/changes/impact_cloud.dxf'):
    try:
        import ezdxf
        from ezdxf.revcloud import add_entity
    except ImportError:raise ValueError('云线导出需安装可选依赖：python -m pip install -e ".[dxf]"')
    result=json.loads(Path(diff_file).read_bytes())
    if result.get('geometry_units')!='mm':raise ValueError('当前云线导出仅支持毫米单位，不能猜测比例')
    document=ezdxf.new('R2010');document.units=4
    document.layers.new('CST_CHANGE_CLOUD',dxfattribs={'color':6,'lineweight':25})
    document.appids.new('CST_TRACE');layout=document.modelspace();skipped=[];count=0
    skipped=[c['id'] for c in result['changes'] if c.get('basis','').startswith('派生') or not c.get('cloud_bounds')]
    changes={c['id']:c for c in result['changes']}
    regions=cloud_regions(result)
    for region in regions:
        bx0,by0,bx1,by1=region['bounds']
        x0=bx0-700;y0=by0-700;x1=bx1+700;y1=by1+700
        segment=max(700,min(1800,max(x1-x0,y1-y0)/12))
        entity=add_entity(layout,[(x0,y0),(x1,y0),(x1,y1),(x0,y1)],segment,calligraphy=False,dxfattribs={'layer':'CST_CHANGE_CLOUD','lineweight':25,'const_width':0})
        trace=[(1000,region['id'])]
        for change_id in region['change_ids']:
            change=changes[change_id]
            trace.extend([(1000,change_id),(1000,'old:'+str((change['old'] or {}).get('handle',''))),(1000,'new:'+str((change['new'] or {}).get('handle','')))])
        entity.set_xdata('CST_TRACE',trace)
        count+=1
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);document.saveas(path)
    return {'origin':result['origin'],'output':path.as_posix(),'cloud_count':count,'skipped_changes':skipped,
        'regions':regions,'units':'mm','source_modified':False,'note':'原WCS坐标独立DXF；以0,0,0插入点、比例1、旋转0外参附着；尚需CAD显示核对，不是自动电气布置'}
