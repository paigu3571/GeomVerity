# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""将离线显示坐标还原为CAD WCS窗口；不伪造生成对象或嵌套图元选中。"""
import math
import re


def cad_location(record, origin_wcs_mm):
    if record.get('类型') == 'generated_light':
        return {'state': 'not_in_source', 'command': None,
                'message': '生成灯具候选尚未写入源图，CAD中没有这盏灯；请定位来源房间。'}
    box = record.get('view_bounds')
    if not box or len(box) != 4 or len(origin_wcs_mm) != 2:
        return {'state': 'unavailable', 'command': None, 'message': '缺少源图坐标，不能生成CAD定位命令。'}
    values = [*box, *origin_wcs_mm]
    if not all(type(v) in (int, float) and math.isfinite(v) for v in values) or box[2] < 0 or box[3] < 0:
        return {'state': 'unavailable', 'command': None, 'message': '定位坐标无效。'}
    x, y, w, h = box
    ox, oy = origin_wcs_mm
    margin = max(1000., max(w, h) * 100.)
    lower = [ox + x * 1000. - margin, oy - (y + h) * 1000. - margin, 0.]
    upper = [ox + (x + w) * 1000. + margin, oy - y * 1000. + margin, 0.]
    reference = record.get('定位字段', {}).get('cad_target') or {}
    nested = bool(reference.get('outer_block_handle') or record.get('外层块Handle') or record.get('source', {}).get('block_path'))
    handle = reference.get('handle') or record.get('source', {}).get('handle')
    handle = handle.upper() if isinstance(handle, str) and re.fullmatch(r'[0-9a-fA-F]+', handle) else None
    def number(value):
        text = format(value, '.15g')
        return text if '.' in text or 'e' in text.lower() else text + '.0'
    def point(p): return "(vlax-3d-point '(" + ' '.join(number(v) for v in p) + '))'
    zoom_try = "(setq gv_result (vl-catch-all-apply 'vla-ZoomWindow (list (vlax-get-acad-object) " + point(lower) + ' ' + point(upper) + ')))'
    # All variables stay local. Do not switch layouts, change PICKFIRST or edit the drawing.
    select = '(sssetfirst nil (ssadd gv_entity))' if handle and not nested else ''
    done = '(progn ' + zoom_try + ' (if (vl-catch-all-error-p gv_result) (princ "\nGeomVerity: zoom failed; return to top plan view and retry.") (progn ' + select + ' (princ "\nGeomVerity: source area located.' + (' Nested entity is not selected.' if nested else '') + '"))))'
    if handle:
        done = '(if (and (setq gv_entity (handent "' + handle + '")) (entget gv_entity)) ' + done + ' (princ "\nGeomVerity: source Handle not found. Open the matching scanned DWG/version."))'
    body = '(cond ((> (getvar "CMDACTIVE") 0) (princ "\nGeomVerity: press Esc twice and retry.")) ((and (= (getvar "TILEMODE") 0) (= (getvar "CVPORT") 1)) (princ "\nGeomVerity: switch to model space and retry.")) (T ' + done + '))'
    command = '((lambda (/ gv_entity gv_result) (vl-load-com) ' + body + ' (princ)))'
    command = command.replace(chr(10), chr(92) + 'n')
    return {'state': 'area_zoom', 'command': command, 'source_handle': handle,
            'window_wcs_mm': [lower, upper], 'nested': nested,
            'message': '粘贴后，CAD缩放到对应范围；块内文字不会单独选中。' if nested else '缩放到源图对应范围；可解析的直接源对象同时选中。',
            'boundary': '请在对应扫描源图和版本中执行；Handle存在不等于已验证图纸版本。命令不修改图元。'}
