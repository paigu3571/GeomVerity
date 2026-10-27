# SPDX-License-Identifier: MPL-2.0
import json,subprocess,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cst.desktop import Workbench
from cst.reviews import make_review,append_review,read_reviews,apply_reviews,review_recorded
ROOT=Path(__file__).resolve().parents[2]
class ReviewFlowTests(unittest.TestCase):
    def test_disposition_is_explicit_and_ledger_preserves_legacy_records(self):
        f={'id':'f','result':'无法判定','decision':{'inputs':[],'rule':{'id':'R1'}}}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'reviews.json'
            legacy=make_review('confirm','SYNTHETIC','old','room',finding=f,drawing_hash='hash',synthetic=True)
            append_review(path,legacy)
            record=make_review('confirm','SYNTHETIC','需建筑改门','room',finding=f,drawing_hash='hash',synthetic=True,disposition='needs_change')
            append_review(path,record);events=read_reviews(path)
            self.assertNotIn('disposition',events[0]);self.assertEqual(events[1]['disposition'],'needs_change')
            self.assertEqual(f['result'],'无法判定')
            reject=make_review('reject','SYNTHETIC','不同意本条结果，重新核对','room',finding=f,drawing_hash='hash',synthetic=True,disposition='needs_data')
            append_review(path,reject);apply_reviews([f],'hash',read_reviews(path))
            self.assertFalse(review_recorded(f));self.assertEqual(f['result'],'无法判定')
            self.assertEqual(f['decision']['engineer']['state'],'工具结果已驳回')
            self.assertEqual(len(read_reviews(path)),3)

            with self.assertRaises(ValueError):make_review('confirm','S','x','room',finding=f,drawing_hash='hash',disposition='pass')

    def test_local_folder_browser_lists_directories_only_and_rejects_files(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp).resolve();(p/'child').mkdir();(p/'file.txt').write_text('no')
            b=Workbench(p/'out',root=ROOT);b.perform('browse_folders',{'path':str(p)})
            self.assertEqual(b.folder_listing['directories'],[str(p/'child')]);self.assertEqual(b.folder_listing['path'],str(p))
            with self.assertRaises(ValueError):b.perform('browse_folders',{'path':str(p/'file.txt')})

    def test_cached_view_requires_same_content_guard_and_refresh_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            b=Workbench(temp,root=ROOT);current=b.project.versions[0]
            def write(directory,target,**kw):Path(target).write_text('view')
            with patch.object(b._claims_cache(),'_guard',return_value=('stable',)),patch('cst.view.write_view',side_effect=write) as build:
                first=b.ensure_view(current);self.assertEqual(b.ensure_view(current),first);self.assertEqual(build.call_count,1)
                b.ensure_view(current,force=True);self.assertEqual(build.call_count,2)
            with patch.object(b._claims_cache(),'_guard',return_value=('changed',)),patch('cst.view.write_view',side_effect=write) as build:
                self.assertNotEqual(b.ensure_view(current),first);self.assertEqual(build.call_count,1)

    @unittest.skipUnless(shutil.which('node'),'Node needed')
    def test_review_queue_dispositions_are_disjoint_and_back_is_not_an_item(self):
        script=r'''const fs=require('node:fs'),vm=require('node:vm');
function node(text=''){return {textContent:text,children:[],value:'',append(...v){this.children.push(...v)},replaceChildren(){this.children=[]},setAttribute(k,v){this[k]=v}}}
const nodes={},byId=id=>nodes[id] ||= node();
const c={byId,state:{comparison:{engineering_rooms:[]}},GVUI:{Button:(kind,text,fn)=>{let x=node(text);x.onclick=fn;return x},SplitPane(){}},element:(tag,text)=>node(text),showPage(){}};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
vm.runInContext(`reviewRows=[{id:'a',object_name:'room',object_ids:['r'],result:'无法判定',values:{}},{id:'b',object_name:'room',object_ids:['r'],result:'无法判定',values:{},manual_review:{disposition:'needs_change'}},{id:'c',object_name:'room',object_ids:['r'],result:'无法判定',values:{},manual_review:{disposition:'needs_data'}},{id:'rejected',object_name:'room',object_ids:['r'],result:'无法判定',values:{confirmation_inherited:true},manual_review:{action:'reject',disposition:'needs_data'}},{id:'legacy',object_name:'room',object_ids:['r'],result:'无法判定',values:{},manual_review:{}}];renderReviewQueue();`,c);
const labels=byId('reviewQueue').children[0].children.map(n=>n.textContent);console.log(JSON.stringify({labels,backMixed:JSON.stringify(byId('reviewQueue')).includes('返回房间清单')}));'''
        data=json.loads(subprocess.check_output(['node','-e',script,str(ROOT/'python/cst/assets/js/pages/review.js')],encoding='utf-8'))
        self.assertEqual(data['labels'],['待处理 2','待补资料 1','已记录 2']);self.assertFalse(data['backMixed'])
