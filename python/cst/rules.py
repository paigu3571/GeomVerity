# SPDX-License-Identifier: MPL-2.0
"""固定六谓词与三值规则骨架；无eval/通用DSL，未批准规则不执行真实数据。"""
from pathlib import Path
from typing import Literal
import yaml
import math
from pydantic import BaseModel,ConfigDict,model_validator

PREDICATES={"space_use_in","long_side_gt","opening_count_ge","adjacent_to_use","directly_below_use","shaft_shared_with"}

class Clause(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str
    code_version:str|None=None
    article:str
    text:str
    strength:Literal["应","宜"]

class Rule(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id:str
    title:str
    rule_version:str="1"
    approved:bool=False
    approved_by:str|None=None
    clauses:list[Clause]
    applies_to:list[str]
    check:dict
    on_missing:str
    scope:str
    @model_validator(mode="after")
    def validate_rule(self):
        if not self.clauses:raise ValueError("必须有规范引用")
        if self.approved and not self.approved_by:raise ValueError("批准规则必须有approved_by")
        checks=[self.check.get("when"),self.check.get("require")] if "when" in self.check else [self.check]
        for check in checks:
            if not isinstance(check,dict) or check.get("predicate") not in PREDICATES:raise ValueError("只支持固定六谓词")
            if set(check)-{"predicate","values","threshold","value","expect"}:raise ValueError("未知判断字段")
            if 'expect' in check and type(check['expect']) is not bool:raise ValueError('expect必须为布尔值')
            name=check['predicate']
            if name in ('space_use_in','adjacent_to_use','directly_below_use','shaft_shared_with'):
                values=check.get('values')
                if not isinstance(values,list) or not values or any(not isinstance(v,str) or not v for v in values):raise ValueError('判断必须有用途值列表')
            elif name=='long_side_gt':
                value=check.get('threshold')
                if type(value) not in (int,float) or value<0 or not math.isfinite(value):raise ValueError('长度阈值必须为非负有限数字')
            elif type(check.get('value')) is not int or check['value']<0:raise ValueError('出入口数量必须为非负整数')
        return self

def load_rule(path):return Rule.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

def predicate(check,item):
    name=check["predicate"]
    if name=="space_use_in":
        return (item.get("use") in check.get("values",[]),"") if item.get("use") else (None,"缺少已确认用途")
    if name=="long_side_gt":
        confirmed=item.get("length_threshold_confirmation")
        if confirmed and confirmed.get("threshold")==check["threshold"] and type(confirmed.get("value")) is bool:
            return confirmed["value"],""
        value=item.get("long_side_m")
        return (value>check["threshold"],"") if value is not None else (None,"缺少可用房间长度")
    if name=="opening_count_ge":
        value=item.get("opening_count")
        if value is None or not item.get("opening_complete",False):return None,"缺少完整出入口信息"
        return value>=check["value"],""
    field={"adjacent_to_use":"adjacent_uses","directly_below_use":"above_uses","shaft_shared_with":"shared_uses"}[name]
    values=item.get(field)
    if values is None:return None,{"adjacent_uses":"缺少贴邻关系数据","above_uses":"缺少上一层语义","shared_uses":"缺少井道共用关系"}[field]
    found=bool(set(values)&set(check.get("values",[])))
    if not found and not item.get(field+"_complete",False):return None,"关系数据不完整，不能从未发现推定不存在"
    return found,""

def evaluate(rule,item,synthetic=False):
    if not rule.approved and not synthetic:raise ValueError("规则未批准，禁止真实数据结论")
    if synthetic and item.get("origin")!="SYNTHETIC":raise ValueError("合成测试必须标SYNTHETIC")
    check=rule.check
    applicable=True
    if item.get("use") in (None,"","UNKNOWN"):
        value,missing=None,"缺少已确认用途"
    elif item.get("use") not in rule.applies_to:
        value,missing=None,"对象用途不在适用范围";applicable=False
    elif "when" in check:
        trigger,missing=predicate(check["when"],item)
        if trigger is not None:trigger=trigger==check['when'].get('expect',True)
        if trigger is None:value=None
        elif not trigger:value=None;missing="本条适用条件未触发";applicable=False
        else:
            value,missing=predicate(check["require"],item)
            if value is not None:value=value==check['require'].get('expect',True)
    else:
        value,missing=predicate(check,item)
        if value is not None:value=value==check.get("expect",True)
    statuses=[item.get("status","review")]+item.get("input_statuses",[])
    confidence="输入已确认" if all(status=="accepted" for status in statuses) else "输入待复核"
    result="不适用" if not applicable else "无法判定" if value is None else "通过" if value else "不通过"
    strength="应" if any(c.strength=="应" for c in rule.clauses) else "宜"
    return {"rule_id":rule.id,"object_ids":[item["id"]],"result":result,"reason":missing if value is None or missing else "本条已实现条件判定",
            "input_confidence":confidence,"level":"提示" if strength=="宜" else "辅助审查",
            "source_handles":item.get("source_handles",[]),"values":{k:item[k] for k in ("long_side_m","length_threshold_confirmation","opening_count","above_uses","adjacent_uses","shared_uses") if k in item},
            "clauses":[c.model_dump() for c in rule.clauses],"scope":rule.scope,"origin":"SYNTHETIC" if synthetic else "REAL"}


def load_rules(directory):
    directory=Path(directory)
    rules=[load_rule(p) for p in sorted(directory.glob('R*.yaml'))]
    for path in sorted((directory/'drafts').glob('*.yaml')):
        rule=load_rule(path)
        if rule.approved:
            if any(r.id==rule.id for r in rules):raise ValueError('规则ID重复：'+rule.id)
            if any(c.code=='待核' or c.article=='待核' for c in rule.clauses):raise ValueError('批准前必须填写核实后的规范引用')
            rules.append(rule)
    return rules
