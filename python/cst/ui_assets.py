# SPDX-License-Identifier: MPL-2.0
"""共享UI资源装配：源码分离，生成的工作台/图面仍为离线单文件。"""
import base64
from pathlib import Path
import re
from xml.etree import ElementTree

ASSETS = Path(__file__).with_name("assets")


def asset_text(relative):
    path = (ASSETS / relative).resolve()
    if not path.is_relative_to(ASSETS.resolve()) or not path.is_file():
        raise ValueError("UI资源不存在或路径越界")
    return path.read_text(encoding="utf-8")


def icon_sprite():
    symbols = []
    for path in sorted((ASSETS / "icons").glob("*.svg")):
        raw = path.read_text(encoding="utf-8")
        root = ElementTree.fromstring(raw)
        if root.tag.rsplit("}", 1)[-1] != "svg":
            raise ValueError("本地图标格式无效")
        content = raw[raw.index(">") + 1:raw.rindex("</svg>")]
        symbols.append(
            '<symbol id="ti-' + path.stem + '" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.75" '
            'stroke-linecap="round" stroke-linejoin="round">' + content + '</symbol>'
        )
    return '<svg class="gv-icon-sprite" aria-hidden="true">' + "".join(symbols) + '</svg>'


def render_ui(name, development=False):
    if name not in {"workbench.html", "view.html"}:
        raise ValueError("未知UI模板")
    text = Path(__file__).with_name(name).read_text(encoding="utf-8")

    if name == "workbench.html" and not development:
        # Keep the test-only markup inert: production DOM has no checkbox to select.
        text = re.sub(r'(<label\s+id="reviewSyntheticLabel".*?</label\s*>)',
                      r'<template id="syntheticControl">\1</template>', text, flags=re.S)

    def stylesheet(match):
        relative = match.group(1).removeprefix("assets/")
        return '<style data-ui-source="' + relative + '">\n' + asset_text(relative) + '\n</style>'

    def script(match):
        relative = match.group(1).removeprefix("assets/")
        code = asset_text(relative).replace("</script", "<\\/script")
        return '<script data-ui-source="' + relative + '">\n' + code + '\n</script>'

    text = re.sub(r'<link\b[^>]*href="(assets/[^"]+\.css)"[^>]*>', stylesheet, text)
    text = re.sub(r'<script\s+src="(assets/[^"]+\.js)"[^>]*>\s*</script\s*>', script, text)
    if 'href="assets/brand/logo-original.png"' in text:
        data = base64.b64encode((ASSETS / "brand/logo-original.png").read_bytes()).decode("ascii")
        text = text.replace('assets/brand/logo-original.png', 'data:image/png;base64,' + data)
    return text.replace("__GV_ICON_SPRITE__", icon_sprite())
