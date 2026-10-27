# SPDX-License-Identifier: MPL-2.0
"""Export the same current-confirmation comparison shown by the workbench, without a model call."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from cst.engineering_comparison import comparison_table


def export_table(claims_path, changes_path, output):
    claims_path,changes_path,output=map(Path,(claims_path,changes_path,output))
    checked=json.loads(claims_path.read_bytes());changes=json.loads(changes_path.read_bytes())
    data=comparison_table({'report':checked},{'report':changes})
    if not data['rows']:raise ValueError('没有对应当前比较的已核验工程原句，未生成图片')
    output.parent.mkdir(parents=True,exist_ok=True)
    font_root=Path(os.environ['WINDIR'])/'Fonts'
    regular=font_root/'msyh.ttc';bold=font_root/'msyhbd.ttc'
    if not regular.is_file() or not bold.is_file():raise ValueError('导出需要本机Microsoft YaHei字体')
    font=lambda size,strong=False:ImageFont.truetype(str(bold if strong else regular),size)
    image=Image.new('RGB',(1920,1080),'white');draw=ImageDraw.Draw(image)
    ink='#172B4D';blue='#1D4ED8';pale='#EFF6FF';line='#CBD5E1'
    draw.text((72,65),'AI说的 vs 图纸实际',font=font(60,True),fill=ink)
    draw.text((76,161),'同一次改图，两间房的旧确认结局不同。',font=font(30),fill=ink)
    draw.text((76,212),'从已核验原文摘录 · 对照当前两版的原确认结果',font=font(23),fill=ink)
    xs=[72,622,1622,1848];top=278;header=80;available=520
    draw.rectangle((xs[0],top,xs[-1],top+header),fill=blue)
    for i,label in enumerate(('AI原句（关键半句）','图纸实际','一致吗')):
        draw.text((xs[i]+24,top+22),label,font=font(28,True),fill='white')
    height=available/len(data['rows']);size=30 if len(data['rows'])<=3 else 21 if len(data['rows'])<=6 else 15
    body_font=font(size);leading=size+14
    def wrapped(text,width,max_lines):
        lines=[];current=''
        for char in text:
            if draw.textlength(current+char,font=body_font)>width and current:
                lines.append(current);current=char
            else:current+=char
        if current:lines.append(current)
        return lines if len(lines)<=max_lines else lines[:max_lines-1]+[lines[max_lines-1][:-1]+'…']
    for n,row in enumerate(data['rows']):
        y=top+header+n*height
        draw.rectangle((xs[0],int(y),xs[-1],int(y+height)),fill=pale if row['verdict']=='不一致' else 'white',outline=line,width=2)
        for i,key in enumerate(('ai_excerpt','drawing_fact','verdict')):
            if i:draw.line((xs[i],y,xs[i],y+height),fill=line,width=2)
            lines=wrapped(row[key],xs[i+1]-xs[i]-48,max(1,int((height-42)/leading)))
            for j,text in enumerate(lines):draw.text((xs[i]+24,y+28+j*leading),text,font=body_font,fill=ink)
    draw.text((76,936),'关键区别：引用找得到，不代表“原确认失效”的说法正确。',font=font(28,True),fill=blue)
    draw.text((76,996),'仅核对所列原确认状态；实际出口仍需看图，最终由工程师确认。',font=font(23),fill=ink)
    image.save(output)
    metadata=dict(data,image_size=[1920,1080],claims_sha256=hashlib.sha256(claims_path.read_bytes()).hexdigest(),
                  changes_sha256=hashlib.sha256(changes_path.read_bytes()).hexdigest())
    output.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'rows':len(data['rows']),'image_size':[1920,1080],'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--claims-check',required=True);parser.add_argument('--changes',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(export_table(args.claims_check,args.changes,args.output),ensure_ascii=False))
