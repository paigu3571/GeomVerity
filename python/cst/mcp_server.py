# SPDX-License-Identifier: MPL-2.0
"""官方MCP SDK stdio；读取已给定扫描目录，不修改CAD或调用模型。"""
import argparse
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
    server.run(transport='stdio')
if __name__=='__main__':main()
