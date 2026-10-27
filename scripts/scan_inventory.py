# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""从GV_LOCAL_SCANS读取扫描；内部体检结果仅写入仓库dist，不提交。"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'python'))
from cst.inventory import inventory


def cell(value):
    if value is None:
        return '未知'
    return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO / 'dist/scan-inventory')
    args = parser.parse_args(argv)
    source = os.environ.get('GV_LOCAL_SCANS')
    if not source:
        parser.error('请先设置GV_LOCAL_SCANS为已有扫描结果根目录（只读）')
    root = Path(source).resolve()
    output = args.output.resolve()
    if not output.is_relative_to(REPO / 'dist'):
        parser.error('体检报告仅允许输出到当前仓库dist/，避免误提交内部数据')
    if output == root or output.is_relative_to(root):
        parser.error('输出目录不能位于扫描数据内')
    try:
        rows = inventory(root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=True)
    payload = {'scan_count': len(rows), 'loaded_count': sum(row['load_ok'] for row in rows),
               'scan_failed_count': sum('failed' in row['layer_status'].values() for row in rows),
               'note': '内部体检，只读；加载成功不等于扫描成功、识别正确或专业通过。', 'scans': rows}
    (output / 'inventory.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 扫描兼容普查（内部，不提交）', '', payload['note'], '',
             f"共{len(rows)}份；三层加载成功{payload['loaded_count']}份；扫描失败{payload['scan_failed_count']}份。", '',
             '| 目录 | 图纸 | SHA前10位 | 日期 | 插件 / 配置 / 解释器 | L1/L2对象 | 语义对象 | 房间 | 状态 / 原因 | 未读代理 | finding类型计数 | 加载 / 原因 | 结论 |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for row in rows:
        errors = '; '.join(name + ': ' + layer['error'] for name, layer in row['layers'].items() if not layer['loaded'])
        values = [Path(row['directory']).relative_to(root), row['drawing_file'], row['drawing_sha256_short'],
                  row['generated_at_utc'], f"{row['producer_version']} / {row['profile_version']} / {row['fact_provider_id']}",
                  f"{row['primitive_count']} / {row['geometry_fact_count']}", row['objects_by_type'], row['room_count'],
                  f"{row['layer_status']} / {row['reason_codes']}", row['unreadable_proxy_count'], row['findings_by_reason'],
                  '成功' if row['load_ok'] else errors, row['conclusion']]
        lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    (output / 'inventory.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in payload.items() if key != 'scans'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
