# SPDX-License-Identifier: MPL-2.0
"""官方MCP SDK stdio；读取已给定扫描目录，不修改CAD或调用模型。"""
import argparse
from typing import Literal
from .claims import check_claims
from .model import snapshot_session
from mcp.server.fastmcp import FastMCP
from .ai import ReadTools

def main():
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--changes');a=p.parse_args()
    tools=ReadTools(a.directory,a.changes);server=FastMCP('CAD Semantic Trace')
    @server.tool()
    def summary()->dict:
        """读取对象与状态数量。"""
        return tools.summary()
    @server.tool()
    def list_objects(type:str|None=None,use:str|None=None,status:str|None=None,offset:int=0,limit:int=20)->dict:
        """读取分页对象，不修改数据。"""
        return tools.list_objects(type,use,status,offset,limit)
    @server.tool()
    def get_object(id:str)->dict:
        """读取指定真实对象。"""
        return tools.get_object(id)
    @server.tool()
    def get_evidence(id:str)->dict:
        """读取对象的来源引用。"""
        return tools.get_evidence(id)
    @server.tool()
    def list_findings(rule_id:str|None=None,result:str|None=None,offset:int=0,limit:int=20)->dict:
        """读取现有规则结果。"""
        return tools.list_findings(rule_id,result,offset,limit)
    @server.tool()
    def get_changes(offset:int=0,limit:int=20,type:str|None=None)->dict:
        """读取真实两版变更。"""
        return tools.get_changes(offset,limit,type)
    @server.tool()
    def get_impacts(change_id:str|None=None,offset:int=0,limit:int=20)->dict:
        """读取既有变更影响，不自动批准工程判断。"""
        return tools.get_impacts(change_id,offset,limit)
    @server.tool()
    def list_decision_inheritance(offset:int=0,limit:int=20,status:str|None=None)->dict:
        """分页读取原确认的继承/待来源确认/失效；旧记录不补造新策略状态。"""
        return tools.list_decision_inheritance(offset,limit,status)
    @server.tool()
    def claims_check(document:dict,area_tolerance:dict|None=None,rows_only:bool=False,status_basis:Literal['current','frozen_record']='current')->dict:
        """离线核验完整原文中的显式主张；只返回结果，不写文件、不调用模型、不代替人工确认。"""
        with snapshot_session():report=check_claims(a.directory,document,changes=a.changes,area_tolerance=area_tolerance,status_basis=status_basis)
        return {k:report[k] for k in ('validator_version','status_basis','rows','valid','scope')} if rows_only else report
    server.run(transport='stdio')
if __name__=='__main__':main()
