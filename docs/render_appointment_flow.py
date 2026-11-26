# -*- coding: utf-8 -*-
"""从本文档的 ```flow 清单生成总流程 SVG 和 PNG。

改判断、分支和文案：编辑 appointment-classify-consult-flow.md 里的 flow 清单。
然后在仓库里运行：

    py -3 docs/render_appointment_flow.py

不要手改 appointment-flow.svg / appointment-flow.png，它们是生成结果。
"""
from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MD = ROOT / "appointment-classify-consult-flow.md"
SVG = ROOT / "appointment-flow.svg"
PNG = ROOT / "appointment-flow.png"

FONT = 14
LINE = 20
GAP = 34
CANVAS_W = 980
LEFT_CX = 214
RAIL_X = 952

COLORS = {
    "classify": {"fill": "#f7f0fc", "stroke": "#7d5eab", "head": "#7d5eab", "bg": "#faf6fd"},
    "book": {"fill": "#e7f1ff", "stroke": "#3c6eb8", "head": "#3c6eb8", "bg": "#f5f9ff"},
    "consult": {"fill": "#e5f7ef", "stroke": "#2d8d62", "head": "#2d8d62", "bg": "#f3fbf7"},
    "io": {"fill": "#fff4c2", "stroke": "#c89a12", "head": "#c89a12", "bg": "#fff4c2"},
}
INK = "#2c3644"
ARROW = "#3d4756"


class Node:
    def __init__(self, nid, kind, text, band):
        self.id = nid
        self.kind = kind
        self.text = text
        self.band = band
        self.box_w = 220
        self.w = 220
        self.h = 56
        self.lines = [text]


class Edge:
    def __init__(self, src, dst, kind, label):
        self.src = src
        self.dst = dst
        self.kind = kind
        self.label = label


class Box:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    @property
    def left(self):
        return self.x

    @property
    def right(self):
        return self.x + self.w

    @property
    def top(self):
        return self.y

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2


def text_width(text, font=FONT):
    width = 0.0
    for ch in text:
        width += font if ord(ch) > 127 else font * 0.56
    return width


def wrap(text, max_w, font=FONT):
    if not text:
        return [""]
    lines = []
    rest = text
    while rest:
        cut = 1
        for index in range(1, len(rest) + 1):
            if text_width(rest[:index], font) <= max_w:
                cut = index
            else:
                break
        if cut < len(rest):
            if cut < len(rest) and rest[cut - 1].isascii() and rest[cut].isascii():
                word_start = cut
                while word_start > 1 and rest[word_start - 1].isascii() and not rest[word_start - 1].isspace():
                    word_start -= 1
                if word_start > 1 and text_width(rest[:word_start].rstrip(), font) <= max_w:
                    cut = word_start
            window = rest[:cut]
            break_at = -1
            for index, ch in enumerate(window):
                if ch in "，。、；？！":
                    break_at = index
            if break_at >= 0:
                cut = break_at + 1
        line = rest[:cut].strip()
        rest = rest[cut:].strip()
        if rest and all(ch in "，。、；？！" for ch in rest) and text_width(line + rest, font) <= max_w + font:
            line += rest
            rest = ""
        lines.append(line)
    return lines or [""]


def extract_flow(md_text):
    marker = "```flow"
    start = md_text.find(marker)
    if start < 0:
        raise SystemExit("文档里没有 ```flow 清单")
    start = md_text.find("\n", start) + 1
    end = md_text.find("```", start)
    if end < 0:
        raise SystemExit("flow 清单没有结束标记")
    return md_text[start:end]


def parse(flow_text):
    bands = []
    nodes = {}
    order = []
    edges = []
    current = None
    raw_edges = []
    for lineno, raw in enumerate(flow_text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("band "):
            parts = [p.strip() for p in line[5:].split("|")]
            if len(parts) != 4:
                raise SystemExit(f"第 {lineno} 行 band 需要 4 段：编号 | 分组 | 标题 | 做什么")
            current = {
                "id": parts[0],
                "group": parts[1],
                "place": parts[2],
                "title": parts[3],
                "duty": "",
                "nodes": [],
            }
            bands.append(current)
            continue
        if line.startswith("duty "):
            if current is None:
                raise SystemExit(f"第 {lineno} 行 duty 不在 band 里")
            current["duty"] = line[5:].strip()
            continue
        head = line.split(" ", 1)[0]
        if head in {"io", "ask", "step", "out"}:
            if current is None:
                raise SystemExit(f"第 {lineno} 行节点不在 band 里")
            body = line[len(head) + 1 :]
            if "|" not in body:
                raise SystemExit(f"第 {lineno} 行节点缺少 |")
            nid, text = [p.strip() for p in body.split("|", 1)]
            if nid in nodes:
                raise SystemExit(f"节点重复：{nid}")
            node = Node(nid, head, text, current["id"])
            nodes[nid] = node
            order.append(nid)
            current["nodes"].append(nid)
            continue
        if line.startswith("edge "):
            raw_edges.append((lineno, line[5:].strip()))
            continue
        raise SystemExit(f"第 {lineno} 行无法识别：{line}")

    for lineno, body in raw_edges:
        if "|" in body:
            left, label = body.split("|", 1)
            label = label.strip()
        else:
            left, label = body, ""
        bits = left.split()
        if len(bits) != 3:
            raise SystemExit(f"第 {lineno} 行 edge 需要：从 到 类型 | 线上的字")
        src, dst, kind = bits
        if src not in nodes or dst not in nodes:
            raise SystemExit(f"第 {lineno} 行 edge 指向了不存在的节点：{src} -> {dst}")
        if kind not in {"down", "right", "yes", "no", "join", "loop"}:
            raise SystemExit(f"第 {lineno} 行未知类型 {kind}")
        edges.append(Edge(src, dst, kind, label))
    return bands, nodes, order, edges


def band_of(bands, nid):
    for band in bands:
        if nid in band["nodes"]:
            return band
    return None


def same_band(nodes, a, b):
    return nodes[a].band == nodes[b].band


def mark_branch(nodes, edges):
    branch = set()
    for edge in edges:
        if edge.kind == "right" and same_band(nodes, edge.src, edge.dst):
            branch.add(edge.dst)
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge.kind in {"down", "yes", "no"} and edge.src in branch and edge.dst not in branch:
                if same_band(nodes, edge.src, edge.dst):
                    branch.add(edge.dst)
                    changed = True
    return branch


def outgoing(edges, src, kind):
    return [edge for edge in edges if edge.src == src and edge.kind == kind]


def measure_node(node):
    if node.kind == "ask":
        inner = node.box_w * 0.60
        node.lines = wrap(node.text, inner)
        node.w = node.box_w
        node.h = max(90, len(node.lines) * LINE + 54)
    else:
        node.lines = wrap(node.text, node.box_w - 28)
        node.w = node.box_w
        node.h = max(48, len(node.lines) * LINE + 22)


def assign_sizes(bands, nodes, branch, edges):
    band_place = {band["id"]: band["place"] for band in bands}
    for nid, node in nodes.items():
        place = band_place[node.band]
        kids = [
            edge
            for edge in edges
            if edge.src == nid and edge.kind in {"down", "yes", "no"} and edge.dst in branch
        ]
        if nid in branch and any(edge.dst == nid and edge.kind in {"yes", "no"} for edge in edges):
            node.box_w = 196
        elif nid in branch and node.kind == "ask":
            node.box_w = 188
        elif nid in branch and kids:
            node.box_w = 236
        elif nid in branch:
            node.box_w = 228 if place == "full" else 214
        elif place == "left" and node.kind == "ask":
            node.box_w = 252
        elif place == "left":
            node.box_w = 236
        elif place == "right" and node.kind == "ask":
            node.box_w = 214
        elif place == "right":
            node.box_w = 214
        elif node.kind == "ask":
            node.box_w = 252
        else:
            node.box_w = 236
        measure_node(node)


def header_height(title, duty, width):
    duty_lines = wrap(duty, width - 28, 12) if duty else []
    return 28 + (len(duty_lines) * 16 if duty_lines else 0) + 14, duty_lines


def spine_of(band, branch):
    return [nid for nid in band["nodes"] if nid not in branch]


def place_tree(root, center_x, top, nodes, edges, pos):
    node = nodes[root]
    pos[root] = Box(center_x - node.w / 2, top, node.w, node.h)
    yes = outgoing(edges, root, "yes")
    no = outgoing(edges, root, "no")
    cursor = top + node.h + (34 if yes and no else 16)
    down = outgoing(edges, root, "down")
    if yes and no:
        left_n = nodes[yes[0].dst]
        right_n = nodes[no[0].dst]
        gap = 14
        total = left_n.w + gap + right_n.w
        left = center_x - total / 2
        row_h = max(left_n.h, right_n.h)
        pos[yes[0].dst] = Box(left, cursor, left_n.w, left_n.h)
        pos[no[0].dst] = Box(left + left_n.w + gap, cursor, right_n.w, right_n.h)
        return cursor + row_h
    if down:
        return place_tree(down[0].dst, center_x, cursor, nodes, edges, pos)
    return top + node.h


def layout_panel(band, anchor_cy, nodes, edges, branch, pos, panels, prev_bottom):
    spine = spine_of(band, branch)
    if not spine:
        raise SystemExit(f"{band['title']} 没有主线上的节点")
    rel = {}
    cursor = 0
    bottoms = []
    for nid in spine:
        node = nodes[nid]
        rel[nid] = Box(0, cursor, node.w, node.h)
        bottom = cursor + node.h
        right = outgoing(edges, nid, "right")
        if right and same_band(nodes, nid, right[0].dst):
            child = nodes[right[0].dst]
            child_top = cursor + node.h / 2 - child.h / 2
            if child_top < cursor:
                child_top = cursor
            tree_bottom = place_tree(right[0].dst, 0, child_top, nodes, edges, rel)
            # place_tree used center 0; shift x later. Keep y.
            bottom = max(bottom, tree_bottom)
        cursor = bottom + GAP
        bottoms.append(bottom)
    entry = spine[0]
    entry_cy = rel[entry].y + rel[entry].h / 2
    shift = anchor_cy - entry_cy
    content_top = min(box.y for box in rel.values()) + shift
    content_bottom = max(box.bottom for box in rel.values()) + shift
    head_h, duty_lines = header_height(band["title"], band["duty"], 500)
    header_top = content_top - head_h - 8
    if prev_bottom is not None and header_top < prev_bottom + 10:
        extra = prev_bottom + 10 - header_top
        shift += extra
        header_top += extra
        content_top += extra
        content_bottom += extra
    ask_cx = 560
    out_cx = 812
    for nid, box in rel.items():
        node = nodes[nid]
        cx = ask_cx if nid not in branch else out_cx
        if nid in branch and node.kind == "ask":
            cx = out_cx
        if nid in branch and any(edge.dst == nid and edge.kind in {"yes", "no"} for edge in edges):
            # pair members keep the x that place_tree will not have set (center 0)
            pass
        pos[nid] = Box(cx - node.w / 2, box.y + shift, node.w, node.h)
    # Re-place branch trees with real x, because the relative pass used center 0
    # and pair nodes were stored in `rel` not separated. Rebuild branch x cleanly.
    for nid in spine:
        right = outgoing(edges, nid, "right")
        if not (right and same_band(nodes, nid, right[0].dst)):
            continue
        parent = pos[nid]
        child_id = right[0].dst
        # remove previous absolute boxes for this tree and place again
        tree_ids = []

        def collect(cur):
            tree_ids.append(cur)
            for kind in ("down", "yes", "no"):
                for edge in outgoing(edges, cur, kind):
                    if edge.dst in branch:
                        collect(edge.dst)

        collect(child_id)
        child = nodes[child_id]
        child_top = parent.cy - child.h / 2
        if child_top < parent.top:
            child_top = parent.top
        place_tree(child_id, out_cx, child_top, nodes, edges, pos)
        content_bottom = max(content_bottom, max(pos[tid].bottom for tid in tree_ids))
    panel = {
        "band": band,
        "header_top": header_top,
        "head_h": head_h,
        "duty_lines": duty_lines,
        "bottom": content_bottom + 12,
        "left": 430,
        "right": 936,
    }
    panels.append(panel)
    # The anchor node may now sit above the pushed panel. Caller handles anchor push.
    return panel, shift - (anchor_cy - entry_cy)


def layout(bands, nodes, order, edges, branch):
    pos = {}
    panels = []
    left_bands = [band for band in bands if band["place"] == "left"]
    full_bands = [band for band in bands if band["place"] == "full"]
    left_spine = []
    for band in left_bands:
        left_spine.extend(spine_of(band, branch))

    legend_h = 92
    y = 16 + legend_h
    left_title = left_bands[0]["title"] if left_bands else "归类机器人"
    left_duty = left_bands[0]["duty"] if left_bands else ""
    left_head_h, left_duty_lines = header_height(left_title, left_duty, 340)
    regions = {
        "legend_h": legend_h,
        "left_header": Box(72, y, 340, left_head_h),
        "left_duty_lines": left_duty_lines,
        "left_title": left_title,
    }
    y += left_head_h + 12
    prev_panel_bottom = None
    anchor_shift_note = []
    for nid in left_spine:
        entry = None
        for edge in outgoing(edges, nid, "right"):
            if not same_band(nodes, nid, edge.dst):
                entry = edge
                break
        node = nodes[nid]
        if entry and prev_panel_bottom is not None:
            y = max(y, prev_panel_bottom + 78)
        pos[nid] = Box(LEFT_CX - node.w / 2, y, node.w, node.h)
        if entry:
            target_band = band_of(bands, entry.dst)
            panel, extra = layout_panel(
                target_band, pos[nid].cy, nodes, edges, branch, pos, panels, prev_panel_bottom
            )
            if extra:
                pos[nid] = Box(pos[nid].x, pos[nid].y + extra, pos[nid].w, pos[nid].h)
                anchor_shift_note.append((nid, extra))
            prev_panel_bottom = panel["bottom"]
            y = panel["bottom"] + GAP
        else:
            y = pos[nid].bottom + GAP
    regions["upper_bottom"] = y
    regions["panels"] = panels
    regions["left_bottom"] = max([pos[nid].bottom for nid in left_spine] + [y])

    # Full-width commit spine
    commit_top = regions["left_bottom"] + 8
    regions["commit_top"] = commit_top
    if not full_bands:
        regions["canvas_h"] = commit_top + 20
        return pos, regions
    band = full_bands[0]
    head_h, duty_lines = header_height(band["title"], band["duty"], CANVAS_W - 80)
    regions["commit_header"] = Box(48, commit_top, CANVAS_W - 70, head_h)
    regions["commit_head_h"] = head_h
    regions["commit_duty_lines"] = duty_lines
    regions["commit_title"] = band["title"]
    y = commit_top + head_h + 16
    commit_out_cx = 690
    for nid in spine_of(band, branch):
        node = nodes[nid]
        pos[nid] = Box(LEFT_CX - node.w / 2, y, node.w, node.h)
        bottom = pos[nid].bottom
        right = outgoing(edges, nid, "right")
        if right and same_band(nodes, nid, right[0].dst):
            child = nodes[right[0].dst]
            child_top = pos[nid].cy - child.h / 2
            if child_top < pos[nid].top:
                child_top = pos[nid].top
            tree_bottom = place_tree(right[0].dst, commit_out_cx, child_top, nodes, edges, pos)
            bottom = max(bottom, tree_bottom)
        y = bottom + GAP
    regions["canvas_h"] = y + 24
    return pos, regions


def esc(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def draw_lines(cx, cy, lines, fill, font, weight="400"):
    parts = []
    start = cy - (len(lines) - 1) * LINE / 2
    for index, line in enumerate(lines):
        parts.append(
            f'<text x="{cx:.1f}" y="{start + index * LINE:.1f}" text-anchor="middle" '
            f'dominant-baseline="central" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="{font}" font-weight="{weight}" fill="{fill}">{esc(line)}</text>'
        )
    return "".join(parts)


def draw_shape(node, box, color):
    if node.kind == "ask":
        points = (
            f"{box.cx:.1f},{box.top:.1f} {box.right:.1f},{box.cy:.1f} "
            f"{box.cx:.1f},{box.bottom:.1f} {box.left:.1f},{box.cy:.1f}"
        )
        body = (
            f'<polygon points="{points}" fill="{color["fill"]}" stroke="{color["stroke"]}" stroke-width="1.8"/>'
        )
    elif node.kind in {"io", "out"}:
        skew = 16
        points = (
            f"{box.left + skew:.1f},{box.top:.1f} {box.right:.1f},{box.top:.1f} "
            f"{box.right - skew:.1f},{box.bottom:.1f} {box.left:.1f},{box.bottom:.1f}"
        )
        body = (
            f'<polygon points="{points}" fill="{COLORS["io"]["fill"]}" stroke="{COLORS["io"]["stroke"]}" stroke-width="1.6"/>'
        )
    else:
        body = (
            f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{box.w:.1f}" height="{box.h:.1f}" rx="6" '
            f'fill="#ffffff" stroke="{color["stroke"]}" stroke-width="1.6"/>'
        )
    return body + draw_lines(box.cx, box.cy, node.lines, INK, FONT)


def draw_label(x, y, text):
    if not text:
        return ""
    width = text_width(text, 12) + 12
    height = 18
    return (
        f'<rect x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" height="{height}" rx="4" '
        f'fill="#ffffff" stroke="#d5dbe3"/>'
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(text)}</text>'
    )


def path_of(points, dotted=False, arrow=True):
    if len(points) < 2:
        return ""
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    dash = ' stroke-dasharray="7 5"' if dotted else ""
    marker = ' marker-end="url(#arrow)"' if arrow else ""
    return (
        f'<path d="{d}" fill="none" stroke="{ARROW}" stroke-width="1.5"{dash}{marker}/>'
    )


def label_on(a, b, text, long_from_start=False):
    if not text:
        return ""
    x1, y1 = a
    x2, y2 = b
    if long_from_start or (abs(y2 - y1) > 90 and abs(x2 - x1) < 30):
        return draw_label(x1 + 28, y1 + 18, text)
    if abs(x2 - x1) >= abs(y2 - y1):
        return draw_label((x1 + x2) / 2, y1 - 14, text)
    return draw_label(x1 + 26, (y1 + y2) / 2, text)


def overlaps(a, b, pad=6):
    return not (
        a.right + pad <= b.left
        or b.right + pad <= a.left
        or a.bottom + pad <= b.top
        or b.bottom + pad <= a.top
    )


def render(bands, nodes, edges, branch, pos, regions):
    parts = []
    height = int(regions["canvas_h"])
    width = CANVAS_W
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
    )
    # Legend: three robot chips
    chips = [
        ("classify", "归类机器人", "拆句并分流。进度和闲聊自己答"),
        ("book", "预约机器人", "确认完整摘要后才写入"),
        ("consult", "咨询机器人", "带上问句和草稿里已知槽位"),
    ]
    chip_w = 304
    for index, (key, title, duty) in enumerate(chips):
        x = 18 + index * (chip_w + 12)
        color = COLORS[key]
        parts.append(
            f'<rect x="{x}" y="14" width="{chip_w}" height="62" rx="8" fill="{color["bg"]}" stroke="{color["stroke"]}"/>'
        )
        parts.append(
            f'<rect x="{x}" y="14" width="8" height="62" rx="3" fill="{color["head"]}"/>'
        )
        parts.append(
            f'<text x="{x + 20}" y="36" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="15" font-weight="700" fill="{color["head"]}">{esc(title)}</text>'
        )
        parts.append(
            f'<text x="{x + 20}" y="58" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="12" fill="{INK}">{esc(duty)}</text>'
        )
    parts.append(
        '<text x="20" y="96" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="#5c6773">'
        "平行四边形是输入或输出，菱形是判断，矩形是处理。向下继续判断，向右是这一支的结果。虚线是回路。"
        "</text>"
    )

    # Left column background
    if "left_header" in regions:
        header = regions["left_header"]
        bottom = regions["left_bottom"]
        parts.append(
            f'<rect x="64" y="{header.y:.1f}" width="348" height="{bottom - header.y + 8:.1f}" rx="12" '
            f'fill="{COLORS["classify"]["bg"]}" stroke="{COLORS["classify"]["stroke"]}" stroke-width="1.4"/>'
        )
        parts.append(
            f'<rect x="64" y="{header.y:.1f}" width="348" height="28" rx="8" fill="{COLORS["classify"]["head"]}"/>'
        )
        parts.append(
            f'<text x="80" y="{header.y + 18:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="14" font-weight="700" fill="#ffffff">{esc(regions["left_title"])}</text>'
        )
        for index, line in enumerate(regions["left_duty_lines"]):
            parts.append(
                f'<text x="80" y="{header.y + 46 + index * 16:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
                f'font-size="12" fill="{INK}">{esc(line)}</text>'
            )

    for panel in regions["panels"]:
        band = panel["band"]
        group = band["group"]
        color = COLORS[group]
        x = panel["left"]
        y = panel["header_top"]
        w = panel["right"] - panel["left"]
        h = panel["bottom"] - panel["header_top"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" '
            f'fill="{color["bg"]}" stroke="{color["stroke"]}" stroke-width="1.6"/>'
        )
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="28" rx="8" fill="{color["head"]}"/>'
        )
        parts.append(
            f'<text x="{x + 14:.1f}" y="{y + 18:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="14" font-weight="700" fill="#ffffff">{esc(band["title"])}</text>'
        )
        for index, line in enumerate(panel["duty_lines"]):
            parts.append(
                f'<text x="{x + 14:.1f}" y="{y + 46 + index * 16:.1f}" '
                f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(line)}</text>'
            )

    if "commit_header" in regions:
        header = regions["commit_header"]
        color = COLORS["book"]
        bottom = regions["canvas_h"] - 12
        parts.append(
            f'<rect x="28" y="{header.y:.1f}" width="{CANVAS_W - 44}" height="{bottom - header.y:.1f}" rx="12" '
            f'fill="{color["bg"]}" stroke="{color["stroke"]}" stroke-width="1.6"/>'
        )
        # Leave a channel on the spine so the incoming arrow does not cross the title.
        parts.append(
            f'<rect x="250" y="{header.y:.1f}" width="{CANVAS_W - 280}" height="28" rx="8" fill="{color["head"]}"/>'
        )
        parts.append(
            f'<text x="266" y="{header.y + 18:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="14" font-weight="700" fill="#ffffff">{esc(regions["commit_title"])}</text>'
        )
        for index, line in enumerate(regions["commit_duty_lines"]):
            parts.append(
                f'<text x="266" y="{header.y + 46 + index * 16:.1f}" '
                f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(line)}</text>'
            )

    # Edges
    edge_svg = []
    for edge in edges:
        if edge.kind in {"join", "loop"}:
            continue
        if edge.src not in pos or edge.dst not in pos:
            continue
        src = pos[edge.src]
        dst = pos[edge.dst]
        if edge.kind == "right":
            a = (src.right, src.cy)
            b = (dst.left, dst.cy if abs(dst.cy - src.cy) < 36 else dst.cy)
            if abs(a[1] - b[1]) < 8:
                edge_svg.append(path_of([a, b]))
                edge_svg.append(label_on(a, b, edge.label))
            else:
                mid_x = (a[0] + b[0]) / 2
                edge_svg.append(path_of([a, (mid_x, a[1]), (mid_x, b[1]), b]))
                edge_svg.append(draw_label(mid_x, (a[1] + b[1]) / 2, edge.label))
        elif edge.kind == "down":
            a = (src.cx, src.bottom)
            b = (dst.cx, dst.top)
            if abs(a[0] - b[0]) < 8:
                edge_svg.append(path_of([a, b]))
                edge_svg.append(label_on(a, b, edge.label))
            else:
                mid_y = (a[1] + b[1]) / 2
                edge_svg.append(path_of([a, (a[0], mid_y), (b[0], mid_y), b]))
                edge_svg.append(draw_label((a[0] + b[0]) / 2, mid_y - 12, edge.label))
        elif edge.kind in {"yes", "no"}:
            a = (src.cx - 28 if edge.kind == "yes" else src.cx + 28, src.bottom)
            b = (dst.cx, dst.top)
            edge_svg.append(path_of([a, b]))
            edge_svg.append(draw_label((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 8, edge.label))

    # Joins share a rail per target
    joins = {}
    for edge in edges:
        if edge.kind == "join":
            joins.setdefault(edge.dst, []).append(edge)
    def hits_node(x1, x2, y, skip):
        left, right = min(x1, x2), max(x1, x2)
        for nid, box in pos.items():
            if nid in skip:
                continue
            if box.top + 3 < y < box.bottom - 3 and box.left < right and box.right > left:
                return True
        return False

    for target, group in joins.items():
        if target not in pos:
            continue
        dst = pos[target]
        rail_x = RAIL_X
        rows = {}
        for edge in group:
            src = pos[edge.src]
            rows.setdefault(round(src.cy / 6), []).append(edge)
        ys = []
        for row in rows.values():
            boxes = [(edge, pos[edge.src]) for edge in row]
            needs_bus = len(boxes) > 1 or any(
                hits_node(box.right, rail_x, box.cy, {edge.src}) for edge, box in boxes
            )
            if not needs_bus:
                edge, box = boxes[0]
                edge_svg.append(path_of([(box.right, box.cy), (rail_x, box.cy)], arrow=False))
                ys.append(box.cy)
                continue
            bus_y = max(box.bottom for _, box in boxes) + 16
            left_x = min(box.cx for _, box in boxes)
            for _, box in boxes:
                edge_svg.append(path_of([(box.cx, box.bottom), (box.cx, bus_y)], arrow=False))
            edge_svg.append(path_of([(left_x, bus_y), (rail_x, bus_y)], arrow=False))
            ys.append(bus_y)
        top_y = min(ys)
        edge_svg.append(path_of([(rail_x, top_y), (rail_x, dst.cy), (dst.right, dst.cy)]))
        edge_svg.append(draw_label((rail_x + dst.right) / 2, dst.cy - 14, "汇合"))

    loops = [edge for edge in edges if edge.kind == "loop"]
    loops.sort(key=lambda edge: abs(pos[edge.src].cy - pos[edge.dst].cy), reverse=True)
    for index, edge in enumerate(loops):
        lane = 18 + index * 28
        src = pos[edge.src]
        dst = pos[edge.dst]
        edge_svg.append(
            path_of(
                [(src.left, src.cy), (lane, src.cy), (lane, dst.cy), (dst.left, dst.cy)],
                dotted=True,
            )
        )
        label_w = text_width(edge.label, 12) + 12
        label_x = dst.left - 8 - label_w / 2
        if label_x < label_w / 2 + 4:
            label_x = label_w / 2 + 4
        edge_svg.append(draw_label(label_x, dst.cy - 16, edge.label))

    parts.extend(edge_svg)
    band_group = {band["id"]: band["group"] for band in bands}
    for nid, node in nodes.items():
        if nid not in pos:
            continue
        group = band_group[node.band]
        color = COLORS.get(group, COLORS["classify"])
        parts.append(draw_shape(node, pos[nid], color))

    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        f'<path d="M 0 1.2 L 8 5 L 0 8.8 z" fill="{ARROW}"/></marker></defs>\n'
        + "\n".join(parts)
        + "\n</svg>\n"
    )
    return svg


def report_overlaps(nodes, pos):
    ids = [nid for nid in nodes if nid in pos]
    hits = []
    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1 :]:
            if overlaps(pos[left_id], pos[right_id]):
                hits.append((left_id, right_id))
    for left_id, right_id in hits:
        a = pos[left_id]
        b = pos[right_id]
        print(f"overlap {left_id} {a.x:.0f},{a.y:.0f} {a.w:.0f}x{a.h:.0f}  {right_id} {b.x:.0f},{b.y:.0f}")
    return hits


def export_png(width, height):
    edge_candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    edge = next((path for path in edge_candidates if path.exists()), None)
    if edge is None:
        print("png skipped: Edge not found")
        return
    port = 8771
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    cwd = os.getcwd()
    os.chdir(ROOT)
    thread.start()
    url = f"http://127.0.0.1:{port}/{SVG.name}?v={SVG.stat().st_mtime_ns}"
    try:
        subprocess.run(
            [
                str(edge),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--screenshot={PNG}",
                url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        server.shutdown()
        os.chdir(cwd)
    print(f"png {PNG.stat().st_size}")


def main():
    flow = extract_flow(MD.read_text(encoding="utf-8"))
    bands, nodes, order, edges = parse(flow)
    branch = mark_branch(nodes, edges)
    assign_sizes(bands, nodes, branch, edges)
    pos, regions = layout(bands, nodes, order, edges, branch)
    missing = [nid for nid in nodes if nid not in pos]
    if missing:
        raise SystemExit("这些节点没有排上位置：" + ", ".join(missing))
    hits = report_overlaps(nodes, pos)
    svg = render(bands, nodes, edges, branch, pos, regions)
    SVG.write_text(svg, encoding="utf-8")
    print(f"svg {CANVAS_W}x{int(regions['canvas_h'])} nodes {len(pos)} overlaps {len(hits)}")
    export_png(CANVAS_W, int(regions["canvas_h"]))


if __name__ == "__main__":
    main()
