# SPDX-License-Identifier: MPL-2.0
"""W18本机串行EXE测量；只留聚合指标，不调用模型、不改输入。需要benchmark可选依赖。"""
import argparse,hashlib,json,os,platform,re,statistics,subprocess,threading,time,urllib.request
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parents[1]
LAYER_NAMES=('cad-primitives.v1.json','building-geometry.v1.json','building-semantics.v1.json')
def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()
def layers(directory):
    found=[]
    for name in LAYER_NAMES:
        p=Path(directory)/name
        if not p.exists():p=p.with_name(p.name+'.gz')
        if not p.exists():raise ValueError('扫描层不完整')
        found.append(p)
    return found

def signatures(directory):return {p.name:sha(p) for p in layers(directory)}

class ExeSession:
    def __init__(self,exe,directory):
        self.directory=directory;directory.mkdir(parents=True,exist_ok=False);self.url_file=directory/'url.txt'
        self.log=(directory/'process.log').open('w',encoding='utf-8');self.monitor_stop=threading.Event();self.peak=0
        self.started=time.perf_counter()
        self.process=subprocess.Popen([str(exe),'--browser','--no-open','--url-output',str(self.url_file),'--output',str(directory/'runtime')],cwd=ROOT,stdout=self.log,stderr=self.log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.memory=psutil.Process(self.process.pid)
        self.monitor=threading.Thread(target=self._monitor,daemon=True);self.monitor.start()
        try:
            until=time.perf_counter()+90
            while not self.url_file.exists():
                if self.process.poll() is not None:raise RuntimeError('EXE启动后退出')
                if time.perf_counter()>until:raise TimeoutError('启动超过90秒')
                time.sleep(.05)
            self.url=self.url_file.read_text(encoding='utf-8-sig').strip()
            page=urllib.request.urlopen(self.url,timeout=15).read().decode('utf-8')
            self.experimental_marker='实验：灯具候选/照度' in page
            # 模板正常格式化后的空格不影响会话token；只读取const声明，不放宽HTTP授权。
            token_match=re.search(r'\bconst\s+token\s*=\s*("[^"\r\n]+")',page)
            if token_match is None:raise ValueError('工作台页面缺少会话token声明')
            self.token=json.loads(token_match.group(1))
        except BaseException:self.close();raise
    def _monitor(self):
        while not self.monitor_stop.is_set():
            try:self.peak=max(self.peak,self.memory.memory_info().rss)
            except psutil.Error:break
            self.monitor_stop.wait(.05)
    def request(self,path,body=None):
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers={'X-GV-Token':self.token,'Content-Type':'application/json'})
        return json.load(urllib.request.urlopen(req,timeout=30))
    def action(self,name,args=None):
        start=time.perf_counter();self.peak=self.memory.memory_info().rss
        job=self.request('api/action',{'name':name,'args':args or {}})
        while True:
            state=self.request('api/state')
            if state['job']['id']==job['id'] and state['job']['status']!='running':
                if state['job']['status']=='error':raise ValueError(name+': '+state['job']['error'])
                return state,{'seconds':time.perf_counter()-start,'peak_working_set_bytes':self.peak,'os_process_peak_working_set_bytes':getattr(self.memory.memory_info(),'peak_wset',None)}
            if time.perf_counter()-start>600:raise TimeoutError(name+'超过600秒')
            time.sleep(.2)
    def close(self):
        self.monitor_stop.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=10)
        if hasattr(self,'monitor'):self.monitor.join(timeout=2)
        self.log.close()


def local_inputs(root):
    if not root:return {}
    root=Path(root).resolve();wanted={60875149:'regular60',334624983:'stress335'};found={}
    for p in root.rglob('building-geometry.v1.json'):
        alias=wanted.get(p.stat().st_size)
        if alias and alias not in found:
            try:layers(p.parent)
            except ValueError:continue
            found[alias]=p.parent
    return found


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--scenarios',default='startup,example,compare,claims,export,regular60,stress335,size')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--defer-stress',action='store_true',help='按维护者决定记录资源不足，335MB三次留待空闲后补测')
    parser.add_argument('--claims',default='dist/blind-label/review13/sample-1/claims.json')
    parser.add_argument('--changes',default='dist/changes/w10-external-2/diff.json')
    parser.add_argument('--local-root',default=os.getenv('GV_LOCAL_SCANS'))
    args=parser.parse_args();exe=Path(args.exe).resolve();out=Path(args.output).resolve()
    if not out.is_relative_to(ROOT/'dist'):raise ValueError('测量输出必须在原仓库dist内')
    if (out/'results.json').exists():raise ValueError('已有测量结果，拒绝覆盖')
    if args.repeats!=3:raise ValueError('W18要求三次实测')
    scenarios=set(args.scenarios.split(','));allowed={'startup','example','compare','claims','export','regular60','stress335','size'}
    if not scenarios<=allowed:raise ValueError('未知场景')
    out.mkdir(parents=True,exist_ok=True);local=local_inputs(args.local_root) if scenarios&{'regular60','stress335'} else {}
    doc=json.loads((ROOT/args.claims).read_bytes())
    inputs={'claims':{'sha256':sha(ROOT/args.claims),'count':len(doc['claims'])},'configured_fallback_changes_sha256':sha(ROOT/args.changes),'local':{}}
    for alias,path in local.items():inputs['local'][alias]={'geometry_file_bytes':(path/'building-geometry.v1.json').stat().st_size,'files_sha256':signatures(path)}
    machine={'platform':platform.platform(),'cpu':platform.processor(),'physical_cores':psutil.cpu_count(logical=False),'logical_cores':psutil.cpu_count(),'ram_bytes':psutil.virtual_memory().total,'psutil_version':psutil.__version__}
    package_files=[p for p in exe.parent.rglob('*') if p.is_file()];package_bytes=sum(p.stat().st_size for p in package_files)
    result={'schema_version':'workbench-benchmark.v1','date_local':time.strftime('%Y-%m-%d %H:%M:%S %z'),'machine':machine,'exe_sha256':sha(exe),'exe':str(exe),'package_directory_bytes':package_bytes,'inputs':inputs,'mode':'EXE --browser --no-open；HTTP数据/任务完成计时，非原生窗口点击验收','cold_definition':'每轮新EXE进程；不清系统文件缓存，不称冷磁盘启动；已加载复用另以缓存标记为准','memory_definition':'50ms RSS采样峰值；另报进程启动以来OS峰值（不是比较增量）','rows':[],'conditions':[],'network_model_used':False}
    def save():
        groups={}
        for row in result['rows']:
            if row['status']=='ok':groups.setdefault(row['scenario'],[]).append(row)
        result['medians']={key:{'trials':len(rows),'seconds':statistics.median(r['seconds'] for r in rows) if 'seconds' in rows[0] else None,'peak_working_set_bytes':statistics.median(r['peak_working_set_bytes'] for r in rows) if 'peak_working_set_bytes' in rows[0] else None,'bytes':statistics.median(r['bytes'] for r in rows) if 'bytes' in rows[0] else None} for key,rows in groups.items()}
        (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for index in range(1,4):
        result['conditions'].append({'trial':index,'cpu_percent_before':psutil.cpu_percent(interval=.5),'available_ram_bytes':psutil.virtual_memory().available,'unrelated_processes_not_terminated':True})
        print('trial',index,flush=True);session=None
        def record(key,metrics,**extra):
            row={'scenario':key,'trial':index,'status':'ok',**metrics,**extra};result['rows'].append(row);save();print(key,round(metrics.get('seconds',0),3),flush=True)
        try:
            session=ExeSession(exe,out/f'trial-{index}')
            state,init=session.action('inspect');assert len(state['health'])==3 and all(h['load_ok'] for h in state['health'].values())
            if 'startup' in scenarios:record('startup',{**init,'seconds':time.perf_counter()-session.started},phase='new_process_to_three_health_cards_ready',experimental_marker_in_html=session.experimental_marker)
            if 'example' in scenarios:
                t=time.perf_counter();session.action('example');state,metrics=session.action('inspect');metrics['seconds']=time.perf_counter()-t;record('example',metrics,phase='warm_process_example_plus_inspect')
            state=session.request('api/state');a,_,b=state['project']['versions'];session.action('select',{'id':b['id']})
            if scenarios&{'compare','export'}:
                state,metrics=session.action('compare',{'old_id':a['id'],'new_id':b['id'],'same_drawing':True})
                assert state['comparison']['change_count']==180
                if 'compare' in scenarios:record('compare',metrics,changes=180)
            if scenarios&{'claims','export'}:
                import_args={'path':str((ROOT/args.claims).resolve()),'status_basis':'current'}
                if not scenarios&{'compare','export'}:import_args['changes']=str((ROOT/args.changes).resolve())
                state,_=session.action('claims_import',import_args)
                result.setdefault('actual_claims_contexts',[]).append({'trial':index,**state['claims_workspace']['context']})
                state,metrics=session.action('claims_check',{'document':doc});assert len(state['claims_workspace']['report']['rows'])==len(doc['claims'])
                if 'claims' in scenarios:record('claims_first',metrics,claim_count=len(doc['claims']),phase='first_check_in_process_includes_loading',cache=state['claims_workspace'].get('cache'))
                first_rows=state['claims_workspace']['report']['rows']
                state,metrics=session.action('claims_check',{'document':doc})
                assert state['claims_workspace']['report']['rows']==first_rows
                if 'claims' in scenarios:record('claims_repeat',metrics,claim_count=len(doc['claims']),phase='second_check_same_process',report_rows_equal=True,cache=state['claims_workspace'].get('cache'))
            if 'export' in scenarios:
                state,metrics=session.action('export',{'path':str(out/f'trial-{index}'/'export'),'claims_dirty':False});assert state['export_output'];record('export',metrics,claims=82,phase='includes_recheck_and_full_bundle')
            for alias in ('regular60','stress335'):
                if alias not in scenarios:continue
                if (alias=='stress335' and args.defer_stress) or psutil.virtual_memory().available<(14 if alias=='stress335' else 6)*1024**3:
                    result['rows'].append({'scenario':alias,'trial':index,'status':'not_measured','reason':'维护者决定本轮资源不足，空闲后补测' if alias=='stress335' and args.defer_stress else '资源保护：可用内存低于6GiB常规/14GiB压力门槛，未启动任务','available_ram_bytes':psutil.virtual_memory().available});save();continue
                if alias not in local:
                    result['rows'].append({'scenario':alias,'trial':index,'status':'not_measured','reason':'未发现与既有记录字节数一致的授权本机扫描'});save();continue
                path=local[alias]
                session.action('add',{'name':alias,'directory':str(path),'note':'本机只读性能测量，不向模型发送扫描'})
                state,metrics=session.action('view');viewer=urllib.request.urlopen(session.url.rstrip('/')+state['viewer'],timeout=30).read();assert b'<svg' in viewer
                unchanged=signatures(path)==inputs['local'][alias]['files_sha256'];assert unchanged
                record(alias,metrics,input_sha256_unchanged=True,geometry_file_bytes=inputs['local'][alias]['geometry_file_bytes'],viewer_http_bytes=len(viewer),scope='生成计时；随后HTTP可达性验证另行执行，未测浏览器绘制或专业正确性')
            if 'size' in scenarios:record('size',{'bytes':sum(p.stat().st_size for p in package_files)},scope='完整审核目录，不是MSI安装器')
        except BaseException as error:
            result['rows'].append({'scenario':'trial','trial':index,'status':'error','error':type(error).__name__+': '+str(error)});save();raise
        finally:
            if session:session.close()
    for alias,path in local.items():assert signatures(path)==inputs['local'][alias]['files_sha256']
    save();print(json.dumps(result['medians'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
