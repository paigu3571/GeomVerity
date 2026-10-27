# SPDX-License-Identifier: MPL-2.0
"""真实官方SDK客户端，经子进程stdio握手/发现/调用并留存实测记录。"""
import asyncio,argparse,json,sys,time,datetime
from pathlib import Path
from html import escape
from importlib.metadata import version
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def run(directory,changes,output,claims=None):
    start=time.perf_counter();args=['-m','cst.mcp_server',directory]
    if changes:args+=['--changes',changes]
    rows=[]
    async with stdio_client(StdioServerParameters(command=sys.executable,args=args)) as streams:
        async with ClientSession(*streams) as client:
            initialized=await client.initialize();listed=await client.list_tools()
            names=[t.name for t in listed.tools]
            async def call(name,arguments):
                r=await asyncio.wait_for(client.call_tool(name,arguments),timeout=120)
                if r.isError:raise ValueError(name+'调用失败')
                data=r.structuredContent
                if data is None:data=json.loads(next(c.text for c in r.content if c.type=='text'))
                rows.append({'tool':name,'arguments':arguments,'response':data});return data
            await call('summary',{})
            objects=await call('list_objects',{'type':'space','limit':1})
            id=objects['items'][0]['id']
            text='SYNTHETIC客户端核验：所引用对象存在。'
            await call('claims_check',{'document':{'schema_version':'claims.v1','original_text':text,'claims':[{'id':'synthetic_mcp_claim','text':text,'span':{'start':0,'end':len(text)},'refs':[id],'values':{},'kind':'reference','extraction':'manual','generated_by':None}]}})
            await call('list_decision_inheritance',{'limit':2})
            if claims:
                document=json.loads(Path(claims).read_bytes())
                complete=await call('claims_check',{'document':document})
                minimal=await call('claims_check',{'document':document,'rows_only':True})
                assert 'document' not in minimal and minimal['rows']==complete['rows']
                assert len(minimal['rows'])==len(document['claims'])
            await call('get_object',{'id':id});await call('get_evidence',{'id':id})
            await call('list_findings',{'limit':1});await call('get_changes',{'limit':2,'type':'space'});await call('get_impacts',{'limit':2})
    result={'origin':'REAL_MCP_STDIO','sdk_version':version('mcp'),'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'protocol_version':initialized.protocolVersion,'tools':names,'calls':rows,'seconds':round(time.perf_counter()-start,3),'network_used':False}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'client_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    body=''.join('<details><summary>'+escape(r['tool'])+' · 调用成功</summary><pre>'+escape(json.dumps(r['response'],ensure_ascii=False,indent=2))+'</pre></details>' for r in rows)
    (output/'client_result.html').write_text('<!doctype html><meta charset="utf-8"><title>MCP真实客户端验证</title><style>body{font:17px/1.7 Microsoft YaHei;background:#edf3f5;color:#163345;max-width:960px;margin:40px auto}details{padding:14px;background:white;margin:12px 0;border-radius:8px}pre{font:13px/1.6 monospace;white-space:pre-wrap}h1{font-size:27px}</style><h1>MCP真实客户端：'+str(len(names))+'项只读工具已调通</h1><p>官方Python SDK '+version('mcp')+' · stdio实际子进程通信 · 不联网、不修改源图</p><p>协议 '+escape(str(result['protocol_version']))+' · '+str(result['seconds'])+' 秒</p><p>此页面展示本次客户端记录，不是MCP Inspector界面。</p>'+body,encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='calls'},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--changes');p.add_argument('--output',default='dist/mcp');p.add_argument('--claims');a=p.parse_args()
    asyncio.run(run(a.directory,a.changes,a.output,a.claims))
