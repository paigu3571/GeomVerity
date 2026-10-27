# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""桌面与本机浏览器共用页面/接口；专业判断仍由Python核心实现。"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.request import urlopen
from urllib.parse import urlunsplit
from . import api
from .reviews import read_reviews
from .project import Project, example_project, read_project, write_project


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))


class Workbench:
    def __init__(self, output='dist/workbench', root=None, development=False):
        self.development = bool(development)
        self.root = Path(root) if root else resource_root()
        self.output = Path(output).resolve()
        self.project = example_project(self.root)
        self.project_file = None
        self.message = '已打开公开示例，扫描质量尚待体检'
        self.viewer = None
        self.export_output = None
        self.health = {}
        self.comparison = None
        self.viewer_focus = None
        self.viewer_neighbor = None
        self.claims_workspaces = {}
        self.claims_catalog = None
        self.claims_input_cache = None
        self.review_findings = None
        self.review_snapshot = None
        self.engineering_notes = None
        self.folder_listing = None
        self.viewer_cache = {}
        self.viewer_review = None
        self.opened_bundle = None
        self.job = {'id': None, 'status': 'idle', 'error': None}
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)

    def state(self):
        from .engineering_comparison import comparison_table
        with self.lock:
            return {'viewer_review':self.viewer_review,'folder_listing':self.folder_listing,'development': self.development, 'project': self.project.model_dump(), 'project_file': self.project_file,
                    'message': self.message, 'job': dict(self.job), 'engineering_notes':self.engineering_notes,
                    'engineering_comparison':comparison_table(self.claims_workspaces.get(self.project.current_version_id),self.comparison) if not (self.engineering_notes and self.engineering_notes.get('version_id')==self.project.current_version_id) else None,
                    'viewer': '/viewer/' + self.token + '?embed=1&v=' + str(self.viewer.stat().st_mtime_ns) + ('&room='+self.viewer_focus if self.viewer_focus else '')+('&neighbor='+self.viewer_neighbor if self.viewer_neighbor else '') if self.viewer else None,
                    'comparison':self.comparison['display'] if self.comparison else None,
                    'opened_bundle':self.opened_bundle,'review_findings':self.review_findings,'claims_workspace':self.claims_workspaces.get(self.project.current_version_id), 'claims_catalog':self.claims_catalog, 'export_output': self.export_output, 'health': dict(self.health)}

    def _claims_cache(self):
        if self.claims_input_cache is None:
            from .workbench_claims import ClaimsInputCache
            self.claims_input_cache=ClaimsInputCache()
        return self.claims_input_cache

    def notify_view_reviews(self,comparison):
        self.viewer_review={'id':secrets.token_hex(8),'drawing_hash':comparison['report']['new_hash'],
            'findings':comparison['report']['new_check']['findings'],'inheritance':comparison['report'].get('review_inheritance',[])}

    def ensure_view(self,current,comparison=None,force=False):
        from .naming import digest
        from .view import write_view
        signature=self._claims_cache()._guard(current.scan_directory,None,None,'current')
        geometry=digest({'old':comparison['report']['old_hash'],'new':comparison['report']['new_hash'],
            'changes':[{k:c.get(k) for k in ('id','old','new','old_geometry','new_geometry','kinds')} for c in comparison['report']['changes']],'lighting':comparison['report'].get('lighting_changes')}) if comparison else None
        key=digest((current.id,signature,geometry))
        target=self.viewer_cache.get(key)
        if force or not target or not target.is_file():
            target=self.output/'views'/key/'semantic_view.html';target.parent.mkdir(parents=True,exist_ok=True)
            changes=comparison['path'] if comparison else None
            generated=Path(changes).parent/'lighting_candidates.json' if changes else None
            write_view(current.scan_directory,target,changes=changes,generated=generated if generated and generated.is_file() else None)
            if self._claims_cache()._guard(current.scan_directory,None,None,'current')!=signature:raise ValueError('生成图面期间依据改变，请重新比较')
            self.viewer_cache[key]=target
        return target

    def review_path(self):
        return Path(self.project_file).parent/'geomverity-reviews.json' if self.project_file else self.output/'geomverity-reviews.json'

    def start(self, name, args):
        allowed = {'browse_folders','example', 'create', 'open', 'save', 'add', 'select', 'view', 'export', 'inspect', 'compare', 'locate_change', 'claims_save', 'claims_check', 'claims_import', 'claims_demo', 'claims_sources', 'locate_ref', 'review_load', 'review_write', 'review_transfer', 'open_bundle', 'extract_engineering_notes'}
        if name not in allowed:
            raise ValueError('未知操作')
        with self.lock:
            if self.job['status'] == 'running':
                raise ValueError('已有任务进行中，请稍候')
            identifier = secrets.token_hex(8)
            self.job = {'id': identifier, 'status': 'running', 'error': None,'started_at':time.time()}
            self.message = {'inspect':'正在体检，请稍候','view':'正在生成图面，请稍候','export':'正在导出证据包，请稍候','compare':'正在比较两版，请稍候','locate_change':'正在定位，约30秒；完成后会自动打开图面'}.get(name,'正在定位，约30秒；完成后会自动打开图面' if name=='locate_ref' else '正在处理项目')
        threading.Thread(target=self._run, args=(name, args), daemon=True).start()
        return {'id': identifier}

    def _run(self, name, args):
        try:
            self.perform(name, args)
        except Exception as exc:
            # 不把严格模型校验错误携带的输入内容回显到界面。
            from pydantic import ValidationError
            error = ('主张与原文位置不一致或字段无效，请重新选择原文并检查引用/数值' if name in {'claims_save','claims_check'} else '项目文件字段不兼容，请检查文件版本') if isinstance(exc, ValidationError) else '指定文件或目录不存在，请检查路径' if isinstance(exc, FileNotFoundError) else '没有读写权限，请选择有权限的目录' if isinstance(exc, PermissionError) else str(exc)
            with self.lock:
                if name=='claims_check':
                    workspace=self.claims_workspaces.get(self.project.current_version_id)
                    if workspace:workspace.update(report=None,context_stale=True,id=secrets.token_hex(8))
                self.job.update(status='error', error=error)
                self.message = '任务未完成，可检查输入后重试'
        else:
            with self.lock:
                self.job.update(status='done', error=None)

    def perform(self, name, args):
        if name in {'review_write', 'review_transfer'} and args.get('synthetic') is True and not self.development:
            raise ValueError('SYNTHETIC仅允许在开发模式使用')
        def required(key):
            value = args.get(key, '')
            if not isinstance(value, str) or not value.strip():
                raise ValueError('请填写' + {'path': '本机文件夹或文件路径', 'name': '名称', 'directory': '扫描目录'}.get(key, key))
            return value.strip()
        with self.lock:
            project = self.project.model_copy(deep=True)
            filename = self.project_file
        if name=='browse_folders':
            import os
            raw=args.get('path','').strip()
            if not raw:
                roots=[str(Path(f'{letter}:/')) for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:/').is_dir()] if os.name=='nt' else ['/']
                value={'path':'','parent':None,'directories':roots,'notice':'选择目标文件夹，不会上传文件。'}
            else:
                folder=Path(raw).resolve()
                if not folder.is_dir():raise ValueError('请选择已有文件夹')
                dirs=[]
                for p in folder.iterdir():
                    try:
                        if p.is_dir() and not p.name.startswith('.'):dirs.append(str(p))
                    except OSError:continue
                value={'path':str(folder),'parent':str(folder.parent) if folder.parent!=folder else '', 'directories':sorted(dirs,key=str.casefold)[:200],'notice':'只显示前200个子文件夹，可输入完整目录。'}
            with self.lock:self.folder_listing=value;self.message='文件夹已列出；点击使用此文件夹完成选择'
            return
        if name=='open_bundle':
            from .workbench_bundle import open_review_bundle
            result=open_review_bundle(required('path'))
            with self.lock:self.opened_bundle=result;self.message='证据包只读重开：文件校验通过，不代表专业通过' if result['verification']['status']=='verified' else '证据包校验失败，已阻止读取结果'
            return
        if name=='extract_engineering_notes':
            text=required('text')
            if len(text)>200000:raise ValueError('请将意见分成20万字以内的段落再载入')
            with self.lock:self.engineering_notes={'version_id':project.current_version_id,'text':text,'origin':'你粘贴的工程意见'};self.message='已按房间关联工程段落；请查看工程事项，不会自动批准意见'
            return
        if name in {'review_load','review_write','review_transfer'}:
            from copy import deepcopy
            from .reviews import make_review,append_review,apply_reviews
            from .model import snapshot_session
            from .ai import ReadTools
            from .naming import digest
            current=next((v for v in project.versions if v.id==project.current_version_id),None)
            if not current:raise ValueError('请先选择当前版本')
            records=read_reviews(self.review_path())
            with self.lock:comparison=self.comparison
            def guard():
                pair=[v for v in project.versions if comparison and v.id in (comparison['display']['old_version']['id'],comparison['display']['new_version']['id'])] or [current]
                return tuple(self._claims_cache()._guard(v.scan_directory,None,None,'current') for v in pair)
            signature=guard()
            if comparison and comparison.get('input_guard')!=signature:
                raise ValueError('图纸或规则已改变，请重新比较两版后再复核')
            if name=='review_transfer':
                if args.get('identity_ack') is not True:raise ValueError('请明确确认已核对旧、新来源对应关系')
                if not comparison:raise ValueError('请先比较两版')
                report=comparison['report'];identifier=required('old_decision_id')
                row=next((r for r in report['decision_inheritance'] if r['old_decision_id']==identifier and (r.get('status')=='pending_identity' or r.get('identity_confirmation'))),None)
                if not row:raise ValueError('本条不在待来源确认状态，请重新比较')
                old=next(f['decision'] for f in report['old_check']['findings'] if f['decision']['id']==identifier)
                new=next(f['decision'] for f in report['new_check']['findings'] if f['decision']['id']==row['new_decision_id'])
                record=make_review(required('action'),required('name'),required('comment'),required('scope'),old=old,new=new,mapping=report['object_mapping'],synthetic=args.get('synthetic') is True)
                if guard()!=signature:raise ValueError('复核期间图纸或规则改变，请重新比较')
                records=append_review(self.review_path(),record)
                from .workbench_compare import refresh_reviews
                result=refresh_reviews(project,comparison,self.output/'comparisons'/secrets.token_hex(8),records)
                if guard()!=signature:raise ValueError('确认已记录，但图纸或规则改变，请重新比较；不沿用当前显示结果')
                result['display']['id']=secrets.token_hex(8);result['input_guard']=signature
                with self.lock:
                    self.comparison=result;self.review_findings=None;self.review_snapshot=None;self.notify_view_reviews(result)
                    for w in self.claims_workspaces.values():
                        if (w.get('context') or {}).get('status_basis')=='current':w['context']=None
                        w.update(report=None,context_stale=True,id=secrets.token_hex(8))
                    self.message='已保存本房间的处理并更新检查结果；几何比较与布灯未重复执行'
                return
            paired=bool(comparison and comparison['display']['new_version']['id']==current.id)
            if paired:
                findings=deepcopy(comparison['report']['new_check']['findings']);drawing_hash=comparison['report']['new_hash']
            elif self.review_snapshot and self.review_snapshot['version_id']==current.id and self.review_snapshot['signature']==signature:
                findings=deepcopy(self.review_snapshot['findings']);drawing_hash=self.review_snapshot['drawing_hash']
            else:
                with snapshot_session():
                    tools=ReadTools(current.scan_directory);findings=deepcopy(list(tools._findings().values()));drawing_hash=tools.data.drawing.sha256
            if guard()!=signature:raise ValueError('读取期间图纸或规则改变，请重读检查结果')
            if name=='review_write':
                f=next((f for f in findings if f['id']==required('finding_id')),None)
                if not f:raise ValueError('当前版本没有此规则结果')
                record=make_review(required('action'),required('name'),required('comment'),required('scope'),finding=f,drawing_hash=drawing_hash,synthetic=args.get('synthetic') is True,disposition=args.get('disposition'))
                records=append_review(self.review_path(),record)
            apply_reviews(findings,drawing_hash,records)
            with self.lock:
                self.review_snapshot={'version_id':current.id,'signature':signature,'findings':deepcopy(findings),'drawing_hash':drawing_hash}
                self.review_findings={'version_id':current.id,'version_name':current.name,'findings':findings,'events':records}
                if paired:
                    comparison['report']['new_check']['findings']=deepcopy(findings)
                    from .engineering import room_tasks
                    comparison['display']['engineering_rooms']=room_tasks(comparison['report']);comparison['display']['id']=secrets.token_hex(8)
                    if name=='review_write':
                        from .workbench_compare import store_review_report
                        updated=store_review_report(project,comparison,comparison['report'],self.output/'comparisons'/secrets.token_hex(8))
                        updated['input_guard']=signature;updated['display']['id']=secrets.token_hex(8)
                        self.comparison=updated;self.notify_view_reviews(updated)
                        for w in self.claims_workspaces.values():
                            if (w.get('context') or {}).get('status_basis')=='current':w['context']=None
                            w.update(report=None,context_stale=True,id=secrets.token_hex(8))
                self.message=('已保存【'+(f.get('object_name') or '本事项')+'】的复核；'+('已记录驳回意见，本条回到待处理' if record.get('action')=='reject' else '已转入待补资料，可查看刚保存的记录' if record.get('disposition')=='needs_data' else '已移入已记录，可查看刚保存的记录')) if name=='review_write' else '检查事项已载入：先处理与本次改图有关的房间'
            return
        if name == 'claims_demo':
            from .workbench_compare import known_public_lineage
            # 演示文档只对应已比较的公开A→A-change；比较不要求用户先切换当前版。
            with self.lock:comparison=self.comparison
            pair=comparison['display'] if comparison else {}
            old=next((v for v in project.versions if v.id==pair.get('old_version',{}).get('id')),None)
            new=next((v for v in project.versions if v.id==pair.get('new_version',{}).get('id')),None)
            if not old or not new or (known_public_lineage(old.scan_directory) or {}).get('label')!='A' or (known_public_lineage(new.scan_directory) or {}).get('label')!='A-change':
                raise ValueError("请先在‘换版’页比较A和A-change，再载入演示句子")
            if project.current_version_id!=new.id:
                self.perform('select',{'id':new.id})
            source=Path(__file__).with_name('assets')/'demo/claims.json'
            document=json.loads(source.read_bytes())
            self.perform('claims_import',{'path':str(source),'status_basis':'current'})
            with self.lock:self.message=f"已载入{len(document['claims'])}句，正在逐条核验，请稍候"
            self.perform('claims_check',{'document':document})
            with self.lock:self.engineering_notes=None;self.message='演示句子已载入并核对；没有调用AI，也没有写入人工确认'
            return
        if name in {'claims_save','claims_check','claims_sources','locate_ref','claims_import'}:
            current=next((v for v in project.versions if v.id==project.current_version_id),None)
            if not current:raise ValueError('请先选择扫描版本')
            with self.lock:
                comparison=self.comparison
                previous=self.claims_workspaces.get(current.id)
            changes=comparison['path'] if comparison and comparison['display']['new_version']['id']==current.id else None
            from .workbench_claims import save_claims,reference_catalog,locate_reference
            if name=='claims_import':
                from .workbench_claims import import_claims
                result=import_claims(current.scan_directory,required('path'),self.output/'claims'/secrets.token_hex(8),previous=previous,changes=args.get('changes') or changes,status_basis=args.get('status_basis','current'))
                result['id']=secrets.token_hex(8)
                with self.lock:self.claims_workspaces[current.id]=result;self.message=f"已载入{len(result['document']['claims'])}句，点‘运行逐条核验’开始"
            elif name=='claims_sources':
                catalog=reference_catalog(current.scan_directory,changes)
                with self.lock:self.claims_catalog=catalog;self.message='依据目录已读取；原文与主张按声明的人工/AI辅助方式划分'
            elif name=='locate_ref':
                ref=required('ref')
                active=comparison if changes else None
                room=next((r for r in (comparison or {}).get('display',{}).get('engineering_rooms',[]) if r['room_id']==ref and not r['old_only']),None)
                located={'object_id':ref} if room else locate_reference(current.scan_directory,ref,changes)
                if 'change_id' in located:
                    self.perform('locate_change',{'change_id':located['change_id']});return
                neighbor=args.get('neighbor')
                if neighbor:
                    pairs=[(f['object_ids'][0],n['id']) for f in (comparison or {}).get('report',{}).get('new_check',{}).get('findings',[]) if f['object_ids'] for n in f['values'].get('adjacent_candidates',[])]
                    if (ref,neighbor) not in pairs and (neighbor,ref) not in pairs:raise ValueError('没有这两个房间的隔墙关系依据')
                neighbor=args.get('neighbor')
                if neighbor:
                    pairs=[(f['object_ids'][0],n['id']) for f in (comparison or {}).get('report',{}).get('new_check',{}).get('findings',[]) if f['object_ids'] for n in f['values'].get('adjacent_candidates',[])]
                    if (ref,neighbor) not in pairs and (neighbor,ref) not in pairs:raise ValueError('没有这两个房间的隔墙关系依据')
                target=self.ensure_view(current,active)
                from urllib.parse import quote
                self.viewer_neighbor=quote(neighbor,safe='') if neighbor else None
                self.viewer_neighbor=quote(neighbor,safe='') if neighbor else None
                with self.lock:self.viewer=target;self.viewer_focus=quote(located['object_id'],safe='');self.message='已定位核验引用；查看不代表人工确认'
            else:
                result=save_claims(current.scan_directory,args.get('document'),self.output/'claims'/secrets.token_hex(8),previous=previous,changes=changes,run_check=name=='claims_check',review_records=read_reviews(self.review_path()),input_cache=self._claims_cache())
                result['id']=secrets.token_hex(8)
                with self.lock:self.claims_workspaces[current.id]=result;self.message='逐条离线核验完成；未知不表示错误或通过' if name=='claims_check' else '主张划分与修改履历已保存，尚未核验'
            return
        if name == 'compare':
            if self.claims_input_cache:self.claims_input_cache.clear()
            from .workbench_compare import compare_versions
            with self.lock:self.comparison=None
            def progress(message):
                with self.lock:self.message=message
            before=tuple(self._claims_cache()._guard(v.scan_directory,None,None,'current') for v in project.versions if v.id in (required('old_id'),required('new_id')))
            result=compare_versions(project, required('old_id'), required('new_id'), self.output/'comparisons'/secrets.token_hex(8), args.get('same_drawing'),progress=progress,review_records=read_reviews(self.review_path()))
            result['input_guard']=tuple(self._claims_cache()._guard(v.scan_directory,None,None,'current') for v in project.versions if v.id in (required('old_id'),required('new_id')))
            if result['input_guard']!=before:raise ValueError('比较期间图纸或规则改变，结果未接受，请重试')
            result['display']['id']=secrets.token_hex(8)
            with self.lock:
                self.comparison=result
                for workspace in self.claims_workspaces.values():
                    if workspace.get('report'):
                        workspace['report']=None;workspace['context_stale']=True;workspace['id']=secrets.token_hex(8)
                self.message='两版比较完成；影响候选与确认适用范围仍需复核'
            return
        if name == 'locate_change':
            with self.lock:comparison=self.comparison
            if not comparison:raise ValueError('请先运行两版比较')
            identifier=required('change_id')
            row=next((r for r in comparison['display']['changes'] if r['id']==identifier),None)
            if not row or not row['can_locate']:raise ValueError('这条变化没有可定位轮廓，请查看来源和原因')
            new_id=comparison['display']['new_version']['id']
            project.select(new_id)
            current=next(v for v in project.versions if v.id==new_id)
            target=self.ensure_view(current,comparison)
            if filename:write_project(project,filename)
            from urllib.parse import quote
            with self.lock:
                self.project=project
                self.viewer=target
                self.viewer_focus=quote(identifier,safe='');self.viewer_neighbor=None;self.viewer_neighbor=None
                self.message='已在新版图面定位变化，含可用旧轮廓；未识别对象不在覆盖范围'
            return
        if name == 'inspect':
            from .inventory import inspect_scan
            for index,version in enumerate(project.versions,1):
                report=inspect_scan(version.scan_directory)
                with self.lock:
                    self.health[version.id]=report
                    self.message=f'体检 {index}/{len(project.versions)}'
            with self.lock:self.message='体检完成；缺口仍需专业复核'
            return
        if name == 'example':
            project, filename = example_project(self.root), None
        elif name == 'create':
            project = Project(name=required('name'))
            filename = write_project(project, required('path'), overwrite=False)
        elif name == 'open':
            from .project import project_path
            filename = str(project_path(required('path')))
            project = read_project(filename)
        elif name == 'save':
            destination = args.get('path', '').strip() or filename
            if not destination:
                raise ValueError('请填写项目保存文件夹')
            from .project import project_path
            target_project=project_path(destination)
            if target_project.name!='geomverity-project.json':raise ValueError('项目文件须命名为geomverity-project.json')
            if target_project.exists() and str(target_project)!=filename:raise ValueError('此处已有项目，请打开它或选择其他目录')
            from .reviews import copy_review_ledger
            copy_review_ledger(self.review_path(),target_project.parent/'geomverity-reviews.json')
            filename = write_project(project, destination, overwrite=(str(target_project) == filename))
        elif name == 'add':
            directory = required('directory')
            # 引用不完整的扫描也允许入项目，但完全不是扫描的文件夹应立即报错。
            from .model import FILENAMES
            if not any((Path(directory) / (stem + suffix)).is_file() for stem in FILENAMES.values() for suffix in ('', '.gz')):
                raise ValueError('目录中没有正式扫描JSON文件')
            project.add_version(required('name'), directory, args.get('note', ''))
            if filename:
                write_project(project, filename)
        elif name == 'select':
            if project.current_version_id==required('id'):
                with self.lock:self.message='当前版本未变，保留已生成图面'
                return
            project.select(required('id'))
            if filename:
                write_project(project, filename)
        elif name in {'view', 'export'}:
            current = next((v for v in project.versions if v.id == project.current_version_id), None)
            if not current:
                raise ValueError('请先添加并选择版本')
            if name == 'view':
                comparison=self.comparison if self.comparison and self.comparison['display']['new_version']['id']==current.id else None
                target=self.ensure_view(current,comparison,force=args.get('refresh') is True)
                with self.lock:
                    self.viewer = target
                    self.viewer_focus = None
                    self.viewer_neighbor = None
                    self.message = '图面已生成；专业结论以依据和人工复核为准'
            else:
                if args.get('claims_dirty') is True:raise ValueError('AI核验页有未保存或未核验修改，请先保存并重新核验后导出')
                from .workbench_bundle import export_review_bundle
                with self.lock:comparison=self.comparison;workspace=self.claims_workspaces.get(current.id)
                changes=comparison['path'] if comparison and comparison['display']['new_version']['id']==current.id else None
                result=export_review_bundle(current.scan_directory,Path(required('path'))/'GeomVerity-bundle',project.name,current.name,workspace=workspace,changes=changes,review_records=read_reviews(self.review_path()))
                with self.lock:
                    self.export_output=result['output']
                    self.message='证据包、人工履历与HTML/CSV清单已导出；文件校验通过不等于专业通过'

            return
        else:
            raise ValueError('未知操作')
        with self.lock:
            if name in {'create','open','example','add','select'} and self.claims_input_cache:self.claims_input_cache.clear()
            if name in {'create','open','example'}:self.health={};self.claims_workspaces={};self.engineering_notes=None;self.review_snapshot=None
            if name in {'create','open','example','add'}:self.comparison=None
            self.viewer_focus=None;self.viewer_neighbor=None
            self.claims_catalog=None
            self.review_findings=None
            self.project, self.project_file = project, filename
            self.viewer, self.export_output = None, None
            self.message = '项目已保存' if filename else '公开示例已打开，尚未保存'


class NativeDialogs:
    """只由桌面用户点击打开文件夹选择，不对HTTP客户端暴露文件对话框。"""
    def __init__(self):self._window=None

    def choose_folder(self):
        import webview
        if self._window is None:raise ValueError('文件夹选择仅适用于桌面窗口')
        paths=self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return {'path':str(paths[0]) if paths else None,'cancelled':not bool(paths)}

def create_server(workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, payload, content_type='application/json;charset=utf-8'):
            if not isinstance(payload, bytes):
                payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            for key, value in [('Content-Type', content_type), ('Content-Length', str(len(payload))),
                               ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def host_valid(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def authorized(self):
            return secrets.compare_digest(self.headers.get('X-GV-Token', ''), workbench.token)

        def do_GET(self):
            if not self.host_valid():
                self.send(403, {'error': '仅接受本机工作台地址'})
            elif self.path == '/':
                from .ui_assets import render_ui
                html = render_ui('workbench.html', development=workbench.development)
                self.send(200, html.replace('__GV_TOKEN__', json.dumps(workbench.token)).encode('utf-8'), 'text/html;charset=utf-8')
            elif self.path == '/api/state' and self.authorized():
                self.send(200, workbench.state())
            elif self.path.partition('?')[0] == '/viewer/' + workbench.token and workbench.viewer:
                self.send(200, workbench.viewer.read_bytes(), 'text/html;charset=utf-8')
            else:
                self.send(404, {'error': '页面不存在或当前会话无权访问'})

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 1024 * 1024:
                    raise ValueError('请求大小超出范围')
                self.connection.settimeout(10)
                payload = self.rfile.read(length)
            except (ValueError, OSError) as exc:
                self.send(400, {'error': str(exc)})
                return
            origin = self.headers.get('Origin')
            base = urlunsplit(('http', f'127.0.0.1:{self.server.server_port}', '', '', ''))
            if not self.host_valid() or not self.authorized() or (origin and origin != base):
                self.send(403, {'error': '请求不是当前本机工作台会话'})
                return
            if self.path != '/api/action':
                self.send(404, {'error': '操作不存在'})
                return
            try:
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('仅接受JSON请求')
                data = json.loads(payload)
                if not isinstance(data, dict) or not isinstance(data.get('args', {}), dict) or not isinstance(data.get('name'), str):
                    raise ValueError('操作参数格式不正确')
                self.send(202, workbench.start(data['name'], data.get('args', {})))
            except (ValueError, TypeError) as exc:
                self.send(400, {'error': str(exc)})
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--development', action='store_true', help='启用测试复核标记；不得用于真实签字')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--no-open', action='store_true', help='浏览器模式下只打印地址，不自动打开')
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--data')
    parser.add_argument('--probe-output')
    parser.add_argument('--url-output', help='把本机地址写入指定文件，便于本地验收')
    parser.add_argument('--output', default='dist/workbench')
    args = parser.parse_args(argv)
    bridge = Workbench(args.output, development=args.development)
    server = create_server(bridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = urlunsplit(('http', f'127.0.0.1:{server.server_port}', '/', '', ''))
    if args.url_output:
        Path(args.url_output).write_text(url, encoding='utf-8')
    print(url, flush=True)

    def probe(window=None):
        value = {'mode': 'desktop' if window else 'browser', 'page_loaded': False}
        try:
            value['page_loaded'] = 'GeomVerity'.encode() in urlopen(url, timeout=10).read()
            if window:
                value['native_window_loaded'] = window.events.loaded.wait(30)
                import webview
                value['gui_backend'] = getattr(webview.guilib, '__name__', 'unknown')
            if args.data:
                from .summary import summary
                value['core_objects'] = summary(api.load(args.data))['objects_by_type']
                value['findings'] = len(api.check(args.data)['findings'])
            if args.probe_output:
                Path(args.probe_output).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(value, ensure_ascii=False), flush=True)
        finally:
            if window:
                window.destroy()
        return value
    try:
        if args.browser:
            if args.probe:
                probe()
            else:
                if not args.no_open:
                    import webbrowser
                    webbrowser.open(url)
                thread.join()
        else:
            try:
                import webview
            except ImportError:
                raise SystemExit('请安装桌面依赖，或使用 --browser 打开本机浏览器工作台')
            dialogs=NativeDialogs()
            window = webview.create_window('GeomVerity · 几何求真', url=url, js_api=dialogs, width=1400, height=900, hidden=args.probe)
            dialogs._window=window
            webview.start((lambda: probe(window)) if args.probe else None, gui='edgechromium')
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
