# SPDX-License-Identifier: MPL-2.0
"""工作台人工划分主张与修改履历，复用离线claims-check，不调用模型。"""
from datetime import datetime, timezone
import json
from pathlib import Path
from .claims import ClaimsDocument, check_claims
from .model import snapshot_session
from .ai import ReadTools
from .evidence import default_registry

def save_claims(directory,document,output,*,previous=None,changes=None,run_check=False,review_records=None,context=None,edit_method="manual",source_sha256=None,input_cache=None):
    doc=ClaimsDocument.model_validate(document)
    if doc.original_text_origin!='full_original':raise ValueError('工作台需要完整原文，不能把拼接主张当全文')
    if run_check and not doc.claims:raise ValueError('请先从原文选出至少一条主张')
    if edit_method not in ('manual','model_import'):raise ValueError('未知编辑来源')
    context=context if context is not None else (previous or {}).get('context')
    if context:
        from hashlib import sha256
        if sha256(Path(context['changes']).read_bytes()).hexdigest()!=context['changes_sha256']:raise ValueError('导入的核验依据已变化，请重新导入并核对')
        if context['status_basis'] not in ('current','frozen_record'):raise ValueError('核验依据模式无效')
        changes=context['changes']
    payload=doc.model_dump();history=list((previous or {}).get('history',[]))
    if payload!=(previous or {}).get('document') or context!=(previous or {}).get('context') or edit_method=='model_import':
        history.append({'at':datetime.now(timezone.utc).isoformat(),'method':edit_method,'actor':'Codex' if edit_method=='model_import' else None,'source_sha256':source_sha256,'context':context,'before':(previous or {}).get('document'),'after':payload})
    target=Path(output);target.mkdir(parents=True,exist_ok=True)
    (target/'claims.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'claims-edit-history.json').write_text(json.dumps({'schema_version':'claims-edit-history.v1','events':history},ensure_ascii=False,indent=2),encoding='utf-8')
    report=None
    options={'changes':changes,'output':target,'review_records':review_records,'status_basis':context['status_basis'] if context else 'current'}
    if run_check:
        if input_cache is not None:report=input_cache.check(directory,payload,**options)
        else:
            with snapshot_session():report=check_claims(directory,payload,**options)
    return {'document':payload,'context':context,'history':history,'cache':dict(input_cache.info) if input_cache and run_check else None,'report':report,'path':str(target/'claims-check.json') if report else None,'directory':str(target)}

def reference_catalog(directory,changes=None):
    with snapshot_session():
        tools=ReadTools(directory,changes)
        return {'rooms':tools.list_objects(type='space',limit=100),'findings':tools.list_findings(limit=100),'changes':tools.get_changes(limit=100),
                'note':'只列前100项供选择；引用缺少验证器与主张错误分别呈现。'}

def locate_reference(directory,ref,changes=None):
    with snapshot_session():
        tools=ReadTools(directory,changes);resolved=default_registry().resolve(tools,ref)
        if not resolved.found:raise ValueError('该引用不存在或没有可用解析器')
        if resolved.kind=='change':return {'change_id':ref}
        if resolved.kind=='finding':
            ids=resolved.raw.get('object_ids',[])
            if ids:return {'object_id':ids[0]}
        if resolved.kind=='decision':
            ids=resolved.raw.get('inputs',[])
            if ids:return {'object_id':ids[0]['object_id']}
        if resolved.kind=='object' and tools.objects[ref].type in ('space','shaft','zone','door','opening'):return {'object_id':ref}
        raise ValueError('此引用没有可直接定位的图面对象，请展开依据核查')


def import_claims(directory,path,output,*,previous=None,changes=None,status_basis='current'):
    """W07显式导入AI辅助划分；保留全文、每条归属与来源哈希，不生成标签。"""
    from hashlib import sha256
    source=Path(path);raw=source.read_bytes();doc=ClaimsDocument.model_validate(json.loads(raw))
    if not doc.claims or any(c.extraction!='model' or c.generated_by!='Codex' for c in doc.claims):
        raise ValueError('AI辅助导入要求每条extraction=model、generated_by=Codex；不伪称人工划分')
    if status_basis not in ('current','frozen_record'):raise ValueError('核验依据模式无效')
    if status_basis=='frozen_record' and not changes:raise ValueError('冻结记录核验必须提供已冻结的diff路径')
    context={}
    if changes:
        with snapshot_session():ReadTools(directory,changes)  # 验证新版哈希，不运行核验或写标签。
        context={'changes':str(Path(changes).resolve()),'changes_sha256':sha256(Path(changes).read_bytes()).hexdigest(),'status_basis':status_basis}
    return save_claims(directory,doc.model_dump(),output,previous=previous,changes=changes,context=context,edit_method='model_import',source_sha256=sha256(raw).hexdigest())


class ClaimsInputCache:
    """仅工作台核验的单组只读模型/摘要缓存；绝不缓存主张判定。"""
    def __init__(self):
        import threading
        self._lock=threading.RLock();self._models={};self._signature=None;self.info={}

    def clear(self):
        with self._lock:self._models.clear();self._signature=None;self.info={}

    def _guard(self,directory,changes,review_records,status_basis):
        import hashlib
        from .resources import rules_directory
        from .naming import digest
        directory=Path(directory).resolve()
        paths=set(p for p in directory.iterdir() if p.is_file() and p.name.endswith(('.json','.json.gz','.yaml')))
        paths.update(rules_directory().rglob('*.yaml'))
        if changes:
            path=Path(changes)
            if not path.is_file() and path.with_name(path.name+'.gz').is_file():path=path.with_name(path.name+'.gz')
            paths.add(path)
        signature=[]
        for path in sorted(paths):
            before=path.stat();raw=path.read_bytes();after=path.stat()
            if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size):raise ValueError('核验依据读取时发生变化，请重试')
            signature.append((str(path.resolve()),before.st_mtime_ns,before.st_size,hashlib.sha256(raw).hexdigest()))
        return (str(directory),tuple(signature),digest(review_records or []),status_basis)

    def check(self,directory,document,**options):
        import time
        output=options.pop('output',None)
        with self._lock:
            try:
                start=time.perf_counter();signature=self._guard(directory,options.get('changes'),options.get('review_records'),options.get('status_basis','current'))
                reused=signature==self._signature and bool(self._models)
                if not reused:self.clear()
                guarded=time.perf_counter()-start
                with snapshot_session(shared_cache=self._models):report=check_claims(directory,document,**options)
                if signature!=self._guard(directory,options.get('changes'),options.get('review_records'),options.get('status_basis','current')):
                    raise ValueError('核验过程中依据变化，结果未接受，请重试')
                self._signature=signature
                self.info={'models_reused':reused,'input_guard':'SHA256+文件签名；单组输入','guard_before_seconds':guarded,'result_recomputed':True}
                if output:
                    path=Path(output)/'claims-check.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                return report
            except BaseException:
                self.clear();raise
