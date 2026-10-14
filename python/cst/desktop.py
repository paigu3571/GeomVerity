# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""可选桌面壳；只调用现有Python核心，不包含识图算法。"""
import argparse,json,sys
from pathlib import Path
from . import api
from .view import write_view
SHELL='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>GeomVerity · 几何求真</title><style>body{margin:0;font:15px Microsoft YaHei;background:#edf4f6;color:#17394a}header{padding:18px 24px;background:#17394a;color:white}h1{margin:0;font-size:23px}nav{padding:16px;display:flex;gap:12px;flex-wrap:wrap}button{padding:13px 18px;border:1px solid #bdd2d9;border-radius:7px;background:white;color:#17394a;cursor:pointer}button:disabled{opacity:.5}#state{padding:0 18px 12px;white-space:pre-wrap}iframe{border:0;width:100%;height:calc(100vh - 190px);background:white}</style><header><h1>GeomVerity · 几何求真</h1><div>从几何数据，到可信工程决策。</div></header><nav><button onclick="choose('old')">选择旧版JSON目录</button><button onclick="choose('new')">选择当前JSON目录</button><button onclick="analyze()">分析并查看</button><button onclick="exportBundle()">导出证据包</button></nav><div id="state">选择已扫描的JSON数据目录。本工作台不直接读取DWG。</div><iframe id="viewer" title="工程语义查看器"></iframe><script>let busy=false;function show(t){document.getElementById('state').textContent=t}async function choose(s){if(busy)return;const r=await pywebview.api.choose(s);show(r.message)}async function work(fn){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);show('正在分析，请稍候…');try{const r=await fn();show(r.message);if(r.viewer)document.getElementById('viewer').src=r.viewer}catch(e){show('未完成：'+e.message)}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false)}}function analyze(){work(()=>pywebview.api.analyze())}function exportBundle(){work(()=>pywebview.api.export_bundle())}</script></html>'''
class Workbench:
    def __init__(self,output='dist/workbench'):
        self._window=None;self._selected={};self._output=Path(output).resolve();self._changes=None
    def _serve(self,environ,start_response):
        route=environ.get('PATH_INFO','/')
        if route=='/':payload=SHELL.encode('utf-8')
        elif route=='/semantic_view.html' and (self._output/'semantic_view.html').is_file():payload=(self._output/'semantic_view.html').read_bytes()
        else:start_response('404 Not Found',[('Content-Type','text/plain;charset=utf-8')]);return [b'Not Found']
        start_response('200 OK',[('Content-Type','text/html;charset=utf-8'),('Content-Length',str(len(payload)))]);return [payload]
    def choose(self,slot):
        import webview
        if slot not in ('old','new'):return {'message':'请选择旧版或当前版'}
        paths=self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not paths:return {'message':'已取消选择'}
        try:
            from .model import L1,L2,L3
            for model in (L1,L2,L3):api.load(paths[0],model)
        except (OSError,ValueError) as exc:return {'message':'请选择含L3 JSON的扫描目录：'+str(exc)}
        self._selected[slot]=Path(paths[0]);return {'message':('旧版' if slot=='old' else '当前版')+'已选择：'+Path(paths[0]).name}
    def analyze(self):
        if 'new' not in self._selected:return {'message':'请先选择当前版JSON目录'}
        new=self._selected['new'];folder=self._output;folder.mkdir(parents=True,exist_ok=True)
        try:
            if self._selected.get('old'):
                api.diff(self._selected['old'],new,folder/'changes');self._changes=folder/'changes/diff.json';generated=folder/'changes/lighting_candidates.json'
            else:
                from .lighting import lights
                lights(new,folder/'current');generated=folder/'current/lighting_candidates.json';self._changes=None
            viewed=write_view(new,folder/'semantic_view.html',generated,self._changes)
            return {'message':'分析完成：'+str(viewed['room_count'])+'个房间/井道/区域可查看。结果：'+str(folder),'viewer':'/semantic_view.html'}
        except (OSError,ValueError) as exc:return {'message':'分析未完成：'+str(exc)}
    def export_bundle(self):
        import webview
        if 'new' not in self._selected:return {'message':'请先选择当前版JSON目录'}
        paths=self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not paths:return {'message':'已取消导出'}
        try:
            value=api.bundle(self._selected['new'],Path(paths[0])/'GeomVerity-bundle',self._changes)
            return {'message':'证据包已导出：'+value['output']+'；'+str(value['decision_count'])+'条决策。'}
        except (OSError,ValueError) as exc:return {'message':'导出未完成：'+str(exc)}

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');parser.add_argument('--data');parser.add_argument('--probe-output');args=parser.parse_args(argv)
    try:import webview
    except ImportError:raise SystemExit('请先安装桌面依赖：python -m pip install ".[desktop,dxf]"')
    bridge=Workbench();window=webview.create_window('GeomVerity · 几何求真',url=bridge._serve,js_api=bridge,width=1400,height=900,hidden=args.probe);bridge._window=window
    def probe():
        loaded=window.events.loaded.wait(30)
        try:
            value={'native_window_loaded':loaded,'window_title':'GeomVerity · 几何求真','gui_backend':getattr(webview.guilib,'__name__','unknown')}
            if args.data:
                from .summary import summary
                data=api.load(args.data);value['core_objects']=summary(data)['objects_by_type'];value['findings']=len(api.check(args.data)['findings'])
            if args.probe_output:Path(args.probe_output).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            if sys.stdout is not None:print(json.dumps(value,ensure_ascii=False),flush=True)
        finally:window.destroy()
    webview.start(probe if args.probe else None,gui='edgechromium')
if __name__=='__main__':main()
