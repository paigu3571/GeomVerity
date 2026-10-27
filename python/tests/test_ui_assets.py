# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from cst.ui_assets import ASSETS, asset_text, render_ui

ROOT = Path(__file__).resolve().parents[2]


class UIAssetsTests(unittest.TestCase):
    def test_html_css_and_js_colors_only_come_from_tokens(self):
        pattern = re.compile(r"#[0-9a-fA-F]{3,8}(?![\w-])")
        files = [*ASSETS.rglob("*.css"), *ASSETS.rglob("*.js"),
                 ROOT / "python/cst/workbench.html", ROOT / "python/cst/view.html"]
        violations = []
        for path in files:
            if path.name != "tokens.css" and pattern.search(path.read_text(encoding="utf-8")):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_assets_are_self_contained_and_original_element_ids_survive(self):
        contract = json.loads(Path(__file__).with_name("fixtures").joinpath("ui-u1-ids.json").read_text(encoding="utf-8"))
        for name in ("workbench", "view"):
            with self.subTest(page=name):
                page = render_ui(name + ".html")
                ids = set(re.findall(r'\bid="([^"]+)"', page))
                self.assertTrue(set(contract["ids"][name]) <= ids)
                self.assertNotIn("__GV_ICON_SPRITE__", page)
                self.assertFalse(re.search(r'<(?:script|link)\b[^>]*(?:src|href)="assets/', page), "仍有未装配的本地资源标签")
                self.assertIn('id="ti-circle-check"', page)
                self.assertIn("--status-support-color", page)
        self.assertIn("__GV_TOKEN__", render_ui("workbench.html"))
        self.assertIn("__PAYLOAD__", render_ui("view.html"))
        with self.assertRaises(ValueError):
            asset_text("../desktop.py")
        with self.assertRaises(ValueError):
            render_ui("../desktop.py")

    def test_legacy_colors_can_only_shrink_and_u2_overlays_are_gone(self):
        budget = json.loads(Path(__file__).with_name("fixtures").joinpath("ui-legacy-colors.json").read_text(encoding="utf-8"))
        names = set(re.findall(r"(--legacy-color-[\w-]+)\s*:", asset_text("css/tokens.css")))
        self.assertLess(len(names), 60)
        self.assertLessEqual(len(names), budget["maximum"])
        self.assertLessEqual(names, set(budget["allowed"]), "不得新增遗留颜色；删除后同步缩减预算")
        for page in ("shell", "project"):
            self.assertFalse((ASSETS / ("css/pages/u2-" + page + ".css")).exists())
        html = render_ui("workbench.html")
        self.assertNotIn("u2-shell.css", html)
        self.assertNotIn("u2-project.css", html)

    @unittest.skipUnless(shutil.which("node"), "显示组件执行测试需要本机Node")
    def test_compact_health_label_keeps_backend_tone_even_when_counts_exist(self):
        script = "const fs=require('node:fs'),vm=require('node:vm');const c={window:{}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),c);console.log(JSON.stringify([null,{tone:'unknown',gap_record_count:162},{tone:'failed',gap_record_count:0},{tone:'warning',gap_record_count:162},{tone:'available',gap_record_count:0}].map(x=>c.window.GVUI.HealthLabel(x))));"
        output = subprocess.check_output(["node", "-e", script, str(ASSETS / "js/components.js")], encoding="utf-8")
        self.assertEqual(json.loads(output), ["等待体检", "资料未知", "扫描失败", "需复核 · 162条缺口", "可用于分析"])

    def test_package_verifier_rejects_deleted_resource_even_when_current_files_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            dest = package / "_internal/cst"
            dest.mkdir(parents=True)
            for source in (ROOT / "python/cst").iterdir():
                if source.is_file() and source.suffix in {".py", ".html", ".yaml", ".json"}:
                    shutil.copy2(source, dest / source.name)
            shutil.copytree(ASSETS, dest / "assets")
            output = Path(temporary) / "check.json"
            command = [sys.executable, str(ROOT / "scripts/verify_desktop_resources.py"), "--package", str(package), "--output", str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            (dest / "assets/css/pages/deleted-ui.css").write_text("/* stale */", encoding="utf-8")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["unexpected_assets"], ["css/pages/deleted-ui.css"])
            self.assertFalse(result["all_same"])

    def test_all_css_variables_resolve_and_four_status_pairs_have_contrast(self):
        source = "\n".join(p.read_text(encoding="utf-8") for p in ASSETS.rglob("*.css"))
        self.assertNotRegex(source, r"var\([^)]*\)[-\w]*\s*:", "变量不能代替CSS属性名")
        definitions = set(re.findall(r"(--[\w-]+)\s*:", source))
        uses = set(re.findall(r"var\((--[\w-]+)", source))
        self.assertEqual(uses - definitions, set())
        tokens = dict(re.findall(r"(--status-[\w-]+):\s*(#[0-9A-Fa-f]{6})", asset_text("css/tokens.css")))
        def luminance(value):
            rgb = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
            return sum(x * y for x, y in zip(linear, (.2126, .7152, .0722)))
        for key in ("support", "review", "contradiction", "unknown"):
            colors = sorted([luminance(tokens["--status-" + key + suffix]) for suffix in ("-color", "-bg")])
            self.assertGreaterEqual((colors[1] + .05) / (colors[0] + .05), 4.5, key)

    @unittest.skipUnless(shutil.which("node"), "状态组件执行测试需要本机Node；浏览器运行不需要Node")
    def test_status_badge_returns_class_official_icon_and_text_without_judgment(self):
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
function node(tag){return {tag,attrs:{},dataset:{},children:[],setAttribute(k,v){this.attrs[k]=v},append(...v){this.children.push(...v)}}}
const context={window:{},document:{createElement:node,createElementNS:(ns,tag)=>node(tag),createTextNode:text=>({text})}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
console.log(JSON.stringify(['支持','需复核','矛盾','未知','pending_identity','unconfirmed','unexpected','无法判定','不通过'].map(state=>{let n=context.window.GVUI.StatusBadge(state);return {state,className:n.className,icon:n.children[0].dataset.icon,text:n.children[1].text}})));
'''
        output = subprocess.check_output(["node", "-e", script, str(ASSETS / "js/components.js")], encoding="utf-8")
        rows = json.loads(output)
        expected = [("support", "circle-check", "支持"), ("review", "alert-triangle", "需复核"),
                    ("contradiction", "circle-x", "矛盾"), ("unknown", "help-circle", "未知")]
        for row, (key, icon, text) in zip(rows, expected):
            self.assertEqual(row["className"], "gv-status gv-status--" + key)
            self.assertEqual(row["icon"], icon)
            self.assertEqual(row["text"], text)
        self.assertEqual(rows[4]["className"], "gv-status gv-status--review")
        self.assertEqual(rows[4]["text"], "待来源确认")
        self.assertEqual(rows[5]["className"], "gv-status gv-status--unknown")
        self.assertEqual(rows[5]["text"], "无人工确认")
        self.assertEqual(rows[6]["text"], "未知")
        self.assertEqual(rows[7]["className"], "gv-status gv-status--unknown")
        self.assertEqual(rows[8]["className"], "gv-status gv-status--contradiction")

    @unittest.skipUnless(shutil.which("node"), "来源对应展示测试需要本机Node")
    def test_transfer_evidence_matches_old_decision_not_first_finding(self):
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
function node(tag,text=''){return {tag,textContent:text,children:[],dataset:{},value:'other',append(...n){this.children.push(...n)},replaceChildren(){this.children=[]},setAttribute(){}}}
const nodes={};const byId=id=>nodes[id] ||= node(id);
const context={byId,element:node,showPage:p=>context.cancelDestination=p,technical:(title,data)=>node('details',title+JSON.stringify(data)),state:{comparison:{review_context:[{old_decision_id:'decision-target',old:{object_name:'target-room',rule_title:'R1',source_handles:['OLD'],values:{candidate_opening_handles:['D1','D2']}},new:{object_name:'target-room',source_handles:['NEW'],values:{candidate_opening_handles:['N1','N2']}},engineer:{confirmed_by:'original-reviewer',scope:'original-scope'}}]}},GVUI:{Button:(v,t)=>node("button",t),SplitPane(){},StatusBadge:s=>node('badge',s),CodeText:s=>node('code',s)}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
vm.runInContext("reviewRows=[{id:'other',reason:'wrong-room-reason'}];reviewTransfer='decision-target';renderReviewMode();",context);
function text(n){return n.textContent+' '+n.children.map(text).join(' ')}
byId('reviewCancelTransfer').onclick();
console.log(JSON.stringify({cancelDestination:context.cancelDestination,queue:text(byId('reviewQueue')),text:text(byId('reviewFindingDetail')),id:byId('reviewFindingDetail').dataset.oldDecisionId,hidden:byId('reviewFindingLabel').hidden}));'''
        output = subprocess.check_output(["node", "-e", script, str(ASSETS / "js/pages/review.js")], encoding="utf-8")
        result = json.loads(output)
        self.assertEqual(result['id'], 'decision-target')
        self.assertEqual(result['cancelDestination'], 'changes')
        self.assertTrue(result['hidden'])
        for expected in ('target-room', 'OLD', 'NEW', 'D1', 'D2', 'N1', 'N2', 'original-reviewer', 'original-scope'):
            self.assertIn(expected, result['text'])
        self.assertNotIn('wrong-room-reason', result['text'])
        self.assertIn('正在复核：target-room', result['queue'])
        self.assertNotIn('待处理', result['queue'])
        self.assertNotIn('选择一间房', result['queue'])

    @unittest.skipUnless(shutil.which("node"), "点击优先级执行测试需要Node")
    def test_lamp_hit_tolerance_takes_priority_over_room_ten_times(self):
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(process.argv[1],'utf8');const start=code.indexOf('function drawingTarget('),end=code.indexOf('svg.onclick',start);
const lamp={dataset:{id:'lamp'},getClientRects:()=>[{}],querySelector:()=>({cx:{baseVal:{value:100}},cy:{baseVal:{value:100}}})};
const c={svg:{classList:{contains:()=>false},getScreenCTM:()=>({}),querySelectorAll:()=>[lamp]},DOMPoint:class {constructor(x,y){this.x=x;this.y=y}matrixTransform(){return this}}};
vm.createContext(c);vm.runInContext(code.slice(start,end),c);
const result=Array.from({length:10},()=>c.drawingTarget({clientX:113,clientY:100,target:{closest:()=>({dataset:{id:'room'}})}}));
result.push(c.drawingTarget({clientX:115,clientY:100,target:{closest:()=>({dataset:{id:'room'}})}}));console.log(JSON.stringify(result));'''
        values=json.loads(subprocess.check_output(["node","-e",script,str(ASSETS/'js/pages/view-events.js')],encoding='utf-8'))
        self.assertEqual(values, ['lamp']*10+['room'])

    def test_bundled_demo_claims_are_valid_and_do_not_contain_private_paths(self):
        from cst.claims import ClaimsDocument
        raw=(ASSETS/'demo/claims.json').read_text(encoding='utf-8')
        doc=ClaimsDocument.model_validate_json(raw)
        self.assertEqual(len(doc.claims),82)
        self.assertTrue(all(c.extraction=='model' and c.generated_by=='Codex' for c in doc.claims))
        self.assertIsNone(re.search(r'[A-Za-z]:[\\/]',raw))

    @unittest.skipUnless(shutil.which("node"), "工程意见显示检查需要Node")
    def test_engineering_paragraphs_omit_metadata_keep_rooms_and_render_tables_as_text(self):
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
const c={byId:()=>({}),element:(tag,text)=>({tag,text,children:[],append(...v){this.children.push(...v)}})};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
const source="**致：** 建筑机电工程师\n**旧版哈希：** ABCDEF0123456789ABCDEF0123456789\n| 房间 | 核对事项 |\n| --- | --- |\n| 预留充电桩配电房 | **核对出口** |\n<script>bad()</script>";
console.log(JSON.stringify({notes:c.engineeringParagraphs(source,[{room_id:'room1',name:'预留充电桩配电房'}]),render:c.readableMarkdown(source)}));'''
        value=json.loads(subprocess.check_output(["node","-e",script,str(ASSETS/'js/pages/engineering.js')],encoding='utf-8'))
        self.assertFalse(any('旧版哈希' in x['text'] or '工程师' in x['text'] for x in value['notes']))
        row=next(x for x in value['notes'] if x['rooms'])
        self.assertEqual(row['rooms'],['room1']);self.assertNotIn('**',row['text'])
        self.assertTrue(any(x['tag']=='table' for x in value['render']['children']))
        self.assertTrue(any(x.get('text')=='<script>bad()</script>' for x in value['render']['children']))

    @unittest.skipUnless(shutil.which("node"), "意见来源隔离检查需要Node")
    def test_pasted_opinion_does_not_display_another_documents_technical_results(self):
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
function node(){return {open:true,children:[],append(...v){this.children.push(...v)},replaceChildren(){this.children=[]}}}
const nodes={},byId=id=>nodes[id] ||= node();
const c={byId,element:node,GVUI:{Button:node}};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
const s={project:{current_version_id:'new'},engineering_notes:{version_id:'new',text:'本房间应核对出口',origin:'你粘贴的工程意见'},claims_workspace:{id:'old-work',document:{original_text:'另一份旧意见'}}};
c.renderEngineering(s);const own={hidden:byId('claimsTechnical').hidden,open:byId('claimsTechnical').open};
s.engineering_notes=null;c.renderEngineering(s);console.log(JSON.stringify({own,restoredHidden:byId('claimsTechnical').hidden}));'''
        value=json.loads(subprocess.check_output(["node","-e",script,str(ASSETS/'js/pages/engineering.js')],encoding='utf-8'))
        self.assertTrue(value['own']['hidden']);self.assertFalse(value['own']['open'])
        self.assertFalse(value['restoredHidden'])

    @unittest.skipUnless(shutil.which("node"), "灯具图层开关检查需要Node")
    def test_demo_light_switch_hides_only_lamps_and_restores(self):
        self.assertIn('id="toggleLights"', (ROOT / "python/cst/view.html").read_text(encoding="utf-8"))
        script = r'''const fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(process.argv[1],'utf8'),nodes={},classes=new Set();
const c={window:{addEventListener(){}},el:id=>nodes[id] ||= {setAttribute(k,v){this[k]=v}},svg:{classList:{toggle(k){if(classes.has(k)){classes.delete(k);return false}classes.add(k);return true}}}};
vm.createContext(c);vm.runInContext(code.slice(code.indexOf('el("toggleLights").onclick'),code.indexOf('// Parent review updates')),c);
nodes.toggleLights.onclick();const hidden={text:nodes.toggleLights.textContent,classes:[...classes]};
nodes.toggleLights.onclick();console.log(JSON.stringify({hidden,shown:{text:nodes.toggleLights.textContent,classes:[...classes]}}));'''
        result=json.loads(subprocess.check_output(["node","-e",script,str(ASSETS/'js/pages/view-events.js')],encoding='utf-8'))
        self.assertEqual(result['hidden']['classes'],['hide-lamps'])
        self.assertEqual(result['hidden']['text'],'显示实验灯具')
        self.assertEqual(result['shown']['classes'],[])
        self.assertEqual(result['shown']['text'],'隐藏实验灯具')

    @unittest.skipUnless(shutil.which("node"),"房间入口检查需要Node")
    def test_uncovered_room_never_opens_another_rooms_rule_form(self):
        script=r'''const fs=require('node:fs'),vm=require('node:vm');let called=0,message='';
const c={byId:()=>({}),action:()=>called++,showError:text=>message=text};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
c.engineeringReview({old_only:false,checks:[]});console.log(JSON.stringify({called,message}));'''
        result=json.loads(subprocess.check_output(['node','-e',script,str(ASSETS/'js/pages/engineering.js')],encoding='utf-8'))
        self.assertEqual(result['called'],0);self.assertIn('未纳入',result['message'])

    @unittest.skipUnless(shutil.which("node"), "复核跳转需要Node")
    def test_mismatch_routes_exact_finding_and_uncovered_change_without_wrong_form(self):
        script=r'''const fs=require('node:fs'),vm=require('node:vm');let reviewed=[],located=[];
const c={state:{comparison:{engineering_rooms:[{room_id:'a',name:'同名房',checks:[{id:'fa'}]},{room_id:'b',name:'同名房',checks:[{id:'fb'}]}]}},byId:()=>({}),GVUI:{Button:(kind,label,fn)=>({label,onclick:fn})},showPage(){}};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
c.engineeringReview=async(room,id)=>reviewed.push([room.room_id,id]);c.action=async(name,args)=>{located.push([name,args]);return true};
(async()=>{const exact=c.comparisonReviewButton({review_target:{room_id:'b',finding_id:'fb'}});await exact.onclick();
const uncovered=c.comparisonReviewButton({review_target:{room_id:'missing',change_id:'change_7'}});await uncovered.onclick();
const unavailable=c.comparisonReviewButton({room_name:'同名房'});console.log(JSON.stringify({reviewed,located,disabled:unavailable.disabled}));})();'''
        value=json.loads(subprocess.check_output(['node','-e',script,str(ASSETS/'js/pages/engineering.js')],encoding='utf-8'))
        self.assertEqual(value['reviewed'],[['b','fb']]);self.assertEqual(value['located'],[['locate_change',{'change_id':'change_7'}]])
        self.assertTrue(value['disabled'])
