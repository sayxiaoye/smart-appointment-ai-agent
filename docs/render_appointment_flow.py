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
GAP = 28
CANVAS_W = 1980

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
        inner = node.box_w * 0.62
        node.lines = wrap(node.text, inner)
        node.w = node.box_w
        node.h = max(92, len(node.lines) * LINE + 52)
    else:
        node.lines = wrap(node.text, node.box_w - 28)
        node.w = node.box_w
        node.h = max(48, len(node.lines) * LINE + 22)


def assign_sizes(bands, nodes, branch, edges):
    del bands
    for nid, node in nodes.items():
        paired = any(edge.dst == nid and edge.kind in {"yes", "no"} for edge in edges)
        if paired:
            node.box_w = 196
        elif node.kind == "ask":
            node.box_w = 236
        elif nid in branch:
            node.box_w = 210
        else:
            node.box_w = 220
        measure_node(node)


def spine_of(band, branch):
    return [nid for nid in band["nodes"] if nid not in branch]


def side_child(edges, nodes, nid):
    for edge in outgoing(edges, nid, "right"):
        if same_band(nodes, nid, edge.dst):
            return edge.dst
    return None


def place_tree(root, center_x, top, nodes, edges, pos):
    node = nodes[root]
    pos[root] = Box(center_x - node.w / 2, top, node.w, node.h)
    yes = outgoing(edges, root, "yes")
    no = outgoing(edges, root, "no")
    down = outgoing(edges, root, "down")
    if yes and no:
        left_n = nodes[yes[0].dst]
        right_n = nodes[no[0].dst]
        row_top = pos[root].bottom + 36
        gap = 18
        left = center_x - (left_n.w + gap + right_n.w) / 2
        pos[yes[0].dst] = Box(left, row_top, left_n.w, left_n.h)
        pos[no[0].dst] = Box(left + left_n.w + gap, row_top, right_n.w, right_n.h)
        return max(pos[yes[0].dst].bottom, pos[no[0].dst].bottom)
    if down and same_band(nodes, root, down[0].dst):
        return place_tree(down[0].dst, center_x, pos[root].bottom + GAP, nodes, edges, pos)
    return pos[root].bottom


def place_column(band, nodes, edges, branch, spine_cx, side_cx, top, pos):
    y = top
    bottoms = [top]
    for nid in spine_of(band, branch):
        node = nodes[nid]
        pos[nid] = Box(spine_cx - node.w / 2, y, node.w, node.h)
        row_bottom = pos[nid].bottom
        child_id = side_child(edges, nodes, nid)
        if child_id:
            child = nodes[child_id]
            follows = any(outgoing(edges, child_id, kind) for kind in ("down", "yes", "no"))
            child_top = pos[nid].cy - child.h / 2
            if child_top < y:
                shift = y - child_top
                pos[nid] = Box(pos[nid].x, pos[nid].y + shift, pos[nid].w, pos[nid].h)
                child_top = y
            if follows:
                row_bottom = max(row_bottom, place_tree(child_id, side_cx, child_top, nodes, edges, pos))
            else:
                pos[child_id] = Box(side_cx - child.w / 2, child_top, child.w, child.h)
                row_bottom = max(pos[nid].bottom, pos[child_id].bottom)
        bottoms.append(row_bottom)
        y = row_bottom + GAP
    return max(bottoms)


def duty_lines(text, width):
    return wrap(text, width - 36, 12) if text else []


def header_block(text, width):
    lines = duty_lines(text, width)
    return 36 + len(lines) * 16 + 8, lines


def layout(bands, nodes, order, edges, branch):
    del order
    global CANVAS_W
    by_id = {band["id"]: band for band in bands}
    margin_l, margin_r = 34, 28
    book_w, class_w, consult_w = 620, 760, 640
    gap_l, gap_r = 108, 96
    book_x = margin_l
    class_x = book_x + book_w + gap_l
    consult_x = class_x + class_w + gap_r
    canvas_w = consult_x + consult_w + margin_r

    ask_w, out_w = 236, 220
    book_rail = book_x + 40
    book_side_cx = book_rail + 18 + out_w / 2
    book_spine_cx = book_x + book_w - 16 - ask_w / 2
    class_spine_cx = class_x + 56 + ask_w / 2
    class_side_cx = class_spine_cx + ask_w / 2 + 84 + out_w / 2
    consult_spine_cx = consult_x + 18 + ask_w / 2
    consult_side_cx = consult_spine_cx + ask_w / 2 + 72 + out_w / 2
    commit_side_cx = class_spine_cx + ask_w / 2 + 56 + (196 + 18 + 196) / 2

    legend_bottom = 96
    y_above = 112
    y_hand = 132
    col_top = 150
    heads = {
        key: header_block(by_id[key]["duty"], width)
        for key, width in (("book", book_w), ("classify", class_w - 40), ("consult", consult_w))
    }
    head_h = max(item[0] for item in heads.values())
    content_top = col_top + head_h + 14

    pos = {}
    class_bottom = place_column(by_id["classify"], nodes, edges, branch, class_spine_cx, class_side_cx, content_top, pos)
    # 预约改草稿从「上下文补全」下方空出一条带：上沿给「还有片段」横穿，再往下才是交给预约
    book_top = pos["q_ctx"].bottom + 64
    book_bottom = place_column(by_id["book"], nodes, edges, branch, book_spine_cx, book_side_cx, book_top, pos)
    consult_bottom = place_column(by_id["consult"], nodes, edges, branch, consult_spine_cx, consult_side_cx, content_top, pos)

    bus_y = book_bottom + 14
    column_bottom = max(book_bottom, class_bottom, consult_bottom)
    commit_top = column_bottom + 76
    commit_head, commit_duty = header_block(by_id["commit"]["duty"], canvas_w - 160)
    commit_content = commit_top + commit_head + 12
    commit_bottom = place_column(
        by_id["commit"], nodes, edges, branch, class_spine_cx, commit_side_cx, commit_content, pos
    )
    commit_rights = [pos[nid].right for nid in by_id["commit"]["nodes"]]
    commit_rail = max(commit_rights) + 32
    canvas_w = max(canvas_w, int(commit_rail + 36))
    loop_y = commit_bottom + 28
    canvas_h = loop_y + 22
    CANVAS_W = canvas_w

    hand_x = pos["q_ask"].right + 34
    if hand_x > class_x + class_w - 14:
        hand_x = class_x + class_w - 14
    regions = {
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "y_above": y_above,
        "y_hand": y_hand,
        "content_top": content_top,
        "legend_bottom": legend_bottom,
        "bus_y": bus_y,
        "loop_y": loop_y,
        "commit_rail": commit_rail,
        "spine_cx": class_spine_cx,
        "lanes": {
            "outer": 16,
            "drop": book_x + book_w + 26,
            "join": book_x + book_w + 40,
            "class_return": class_x + 16,
            "class_loop": pos["input"].left - 20,
            "back": pos["q_ask"].right + 16,
            "hand": hand_x,
            "gap_r": class_x + class_w + 42,
            "consult_rail": consult_x + consult_w - 16,
            "book_rail": book_rail,
        },
        "columns": [],
        "commit": {
            "x": 30,
            "y": commit_top,
            "w": canvas_w - 46,
            "h": loop_y - commit_top - 8,
            "head_h": commit_head,
            "duty_lines": commit_duty,
            "notch": class_spine_cx,
            "title": by_id["commit"]["title"],
        },
    }
    frames = [
        ("book", book_x, book_w, book_bottom + 8),
        ("classify", class_x, class_w, class_bottom),
        ("consult", consult_x, consult_w, consult_bottom),
    ]
    for key, x, width, bottom in frames:
        head, lines = heads[key]
        regions["columns"].append(
            {
                "band": by_id[key],
                "x": x,
                "y": col_top,
                "w": width,
                "h": bottom - col_top + 12,
                "head_h": head_h,
                "duty_lines": lines,
                "title_right": hand_x - 12 if key == "classify" else x + width,
            }
        )
    regions["geo"] = {
        "book_x": book_x,
        "book_right": book_x + book_w,
        "class_x": class_x,
        "class_right": class_x + class_w,
        "consult_x": consult_x,
        "consult_right": consult_x + consult_w,
    }
    return pos, regions


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
    width = text_width(text, 12) + 14
    height = 18
    return (
        f'<rect x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" height="{height}" rx="4" '
        f'fill="#ffffff" stroke="#d5dbe3"/>'
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(text)}</text>'
    )


def path_of(points, dotted=False, arrow=True):
    cleaned = []
    for point in points:
        if not cleaned or abs(cleaned[-1][0] - point[0]) > 0.4 or abs(cleaned[-1][1] - point[1]) > 0.4:
            cleaned.append(point)
    if len(cleaned) < 2:
        return ""
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in cleaned)
    dash = ' stroke-dasharray="7 5"' if dotted else ""
    marker = ' marker-end="url(#arrow)"' if arrow else ""
    return f'<path d="{d}" fill="none" stroke="{ARROW}" stroke-width="1.7" stroke-linejoin="round"{dash}{marker}/>'


class Route:
    def __init__(self, points, label="", dotted=False, arrow=True, label_at=None, tag=""):
        self.points = points
        self.label = label
        self.dotted = dotted
        self.arrow = arrow
        self.label_at = label_at
        self.tag = tag


def anchor(node, box, side):
    skew = 16 if node.kind in {"io", "out"} else 0
    if side == "left":
        return (box.left + skew / 2, box.cy) if skew else (box.left, box.cy)
    if side == "right":
        return (box.right - skew / 2, box.cy) if skew else (box.right, box.cy)
    if side == "top":
        if skew:
            return ((box.left + skew + box.right) / 2, box.top)
        return (box.cx, box.top)
    if skew:
        return ((box.left + box.right - skew) / 2, box.bottom)
    return (box.cx, box.bottom)


def elbow(a, b):
    if abs(a[0] - b[0]) < 6 or abs(a[1] - b[1]) < 6:
        return [a, b]
    return [a, (b[0], a[1]), b]


def label_near(a, b, text):
    if abs(a[0] - b[0]) >= abs(a[1] - b[1]):
        return ((a[0] + b[0]) / 2, a[1] - 14)
    y = a[1] + 16 if b[1] > a[1] else a[1] - 16
    if abs(b[1] - a[1]) < 70:
        y = (a[1] + b[1]) / 2
    return (a[0] + 18, y)


def diamond_lower_left(box):
    # 左顶点往下沿边，避开正左和正下两个口
    t = 0.46
    x = box.left + t * (box.cx - box.left)
    y = box.cy + t * (box.bottom - box.cy)
    return x, y


def build_routes(nodes, edges, pos, regions):
    lanes = regions["lanes"]
    routes = []
    used = set()

    def add(points, label="", dotted=False, arrow=True, label_at=None, tag=""):
        routes.append(Route(points, label, dotted, arrow, label_at, tag))

    # 交给预约：从判断左侧进入列间空隙，向上接到预约第一问的右侧
    slot = pos["is_slot"]
    cancel = pos["book_cancel"]
    hand_label = next(edge.label for edge in edges if edge.src == "is_slot" and edge.dst == "book_cancel")
    add(
        [
            anchor(nodes["is_slot"], slot, "left"),
            (lanes["drop"], slot.cy),
            (lanes["drop"], cancel.cy),
            anchor(nodes["book_cancel"], cancel, "right"),
        ],
        hand_label,
        label_at=(lanes["drop"] + 36, (slot.cy + cancel.cy) / 2),
        tag="handoff-book",
    )
    used.add(("is_slot", "book_cancel"))

    # 交给咨询：右空隙里拐进咨询入口的左侧
    question = pos["is_question"]
    consult_in = pos["consult_in"]
    consult_label = next(edge.label for edge in edges if edge.src == "is_question" and edge.dst == "consult_in")
    add(
        [
            anchor(nodes["is_question"], question, "right"),
            (lanes["gap_r"], question.cy),
            (lanes["gap_r"], consult_in.cy),
            anchor(nodes["consult_in"], consult_in, "left"),
        ],
        consult_label,
        label_at=(lanes["gap_r"] + 28, (question.cy + consult_in.cy) / 2),
        tag="handoff-consult",
    )
    used.add(("is_question", "consult_in"))

    # 还有片段：从菱形左下侧先落到框外，再沿归类列左边降到两栏之间的空白，贴预约列左缘升回空带
    more = pos["more"]
    q_ctx = pos["q_ctx"]
    x_lane = lanes["class_loop"]
    x_rise = regions["geo"]["class_x"] - 18
    x_out = regions["geo"]["book_x"] + 14
    y_under = regions["commit"]["y"] - 28
    y_back = cancel.top - 40
    t = 0.86
    leave = (
        more.left + t * (more.cx - more.left),
        more.cy + t * (more.bottom - more.cy),
    )
    x_drop = leave[0] - 32
    y_clear = more.bottom + 52
    more_label = next(edge.label for edge in edges if edge.src == "more" and edge.dst == "q_ctx")
    add(
        [
            leave,
            (x_drop, leave[1]),
            (x_drop, y_clear),
            (x_rise, y_clear),
            (x_rise, y_under),
            (x_out, y_under),
            (x_out, y_back),
            (x_lane, y_back),
            (x_lane, q_ctx.cy),
            anchor(nodes["q_ctx"], q_ctx, "left"),
        ],
        more_label,
        dotted=True,
        label_at=((regions["geo"]["book_x"] + regions["geo"]["book_right"]) / 2, y_back),
        tag="loop-more",
    )
    used.add(("more", "q_ctx"))

    # 回到补全：澄清追问右侧上去，进入上下文补全的右侧
    q_ask = pos["q_ask"]
    back_label = next(edge.label for edge in edges if edge.src == "q_ask" and edge.dst == "q_ctx")
    back_mid_y = (q_ask.cy + q_ctx.cy) / 2
    add(
        [
            anchor(nodes["q_ask"], q_ask, "right"),
            (lanes["back"], q_ask.cy),
            (lanes["back"], q_ctx.cy),
            anchor(nodes["q_ctx"], q_ctx, "right"),
        ],
        back_label,
        dotted=True,
        label_at=((anchor(nodes["q_ctx"], q_ctx, "right")[0] + lanes["back"]) / 2, q_ctx.cy - 14),
        tag="loop-ask",
    )
    used.add(("q_ask", "q_ctx"))
    del back_mid_y

    # 下一句：从页边升到输入的高度，横穿预约列顶部的空区，进入输入左侧
    nxt = pos["next_sentence"]
    entered = pos["input"]
    entry = anchor(nodes["input"], entered, "left")
    add(
        [
            anchor(nodes["next_sentence"], nxt, "bottom"),
            (nxt.cx, regions["loop_y"]),
            (lanes["outer"], regions["loop_y"]),
            (lanes["outer"], entry[1]),
            entry,
        ],
        "下一句",
        dotted=True,
        label_at=(regions["geo"]["book_x"] + 160, entry[1] - 18),
        tag="loop-next",
    )
    used.add(("next_sentence", "input"))

    # 改草稿的结果，沿左轨汇到「还有片段吗」的左下边
    attach = diamond_lower_left(more)
    book_sources = [edge for edge in edges if edge.kind == "join" and nodes[edge.src].band == "book"]
    rail_x = lanes["book_rail"]
    top_y = None
    for edge in book_sources:
        box = pos[edge.src]
        start = anchor(nodes[edge.src], box, "left")
        add([start, (rail_x, start[1])], arrow=False, tag=f"join-{edge.src}")
        top_y = start[1] if top_y is None else min(top_y, start[1])
        used.add((edge.src, edge.dst))
    if book_sources and top_y is not None:
        add(
            [
                (rail_x, top_y),
                (rail_x, regions["bus_y"]),
                (lanes["join"], regions["bus_y"]),
                (lanes["join"], attach[1]),
                attach,
            ],
            "汇合",
            label_at=((lanes["join"] + attach[0]) / 2, attach[1] - 14),
            tag="join-book",
        )

    # 咨询的结果，沿右轨在「还有片段吗」的高度汇入右侧
    consult_sources = [edge for edge in edges if edge.kind == "join" and nodes[edge.src].band == "consult"]
    consult_rail = lanes["consult_rail"]
    consult_top = None
    for edge in consult_sources:
        box = pos[edge.src]
        start = anchor(nodes[edge.src], box, "right")
        add([start, (consult_rail, start[1])], arrow=False, tag=f"join-{edge.src}")
        consult_top = start[1] if consult_top is None else min(consult_top, start[1])
        used.add((edge.src, edge.dst))
    if consult_sources and consult_top is not None:
        more_right = anchor(nodes["more"], more, "right")
        add(
            [
                (consult_rail, consult_top),
                (consult_rail, more_right[1]),
                more_right,
            ],
            "汇合",
            label_at=((consult_rail + more_right[0]) / 2, more_right[1] - 14),
            tag="join-consult",
        )

    # 落单结果汇到「本句结束」的右侧
    end = pos["sentence_end"]
    end_right = anchor(nodes["sentence_end"], end, "right")
    commit_sources = [edge for edge in edges if edge.kind == "join" and nodes[edge.src].band == "commit"]
    commit_rail = regions["commit_rail"]
    rows = {}
    for edge in commit_sources:
        box = pos[edge.src]
        rows.setdefault(round(box.cy / 8), []).append(edge)
        used.add((edge.src, edge.dst))
    rail_ys = []
    for group in rows.values():
        if len(group) == 1:
            edge = group[0]
            start = anchor(nodes[edge.src], pos[edge.src], "right")
            add([start, (commit_rail, start[1])], arrow=False, tag=f"join-{edge.src}")
            rail_ys.append(start[1])
            continue
        bus = max(pos[edge.src].bottom for edge in group) + 14
        left_x = min(pos[edge.src].cx for edge in group)
        for edge in group:
            add([(pos[edge.src].cx, pos[edge.src].bottom), (pos[edge.src].cx, bus)], arrow=False, tag=f"join-{edge.src}")
        add([(left_x, bus), (commit_rail, bus)], arrow=False, tag="join-bus")
        rail_ys.append(bus)
    if rail_ys:
        add(
            [(commit_rail, min(rail_ys)), (commit_rail, end_right[1]), end_right],
            "汇合",
            label_at=((commit_rail + end_right[0]) / 2, end_right[1] - 14),
            tag="join-commit",
        )

    for edge in edges:
        key = (edge.src, edge.dst)
        if key in used or edge.kind in {"join", "loop"}:
            continue
        src_n = nodes[edge.src]
        dst_n = nodes[edge.dst]
        src = pos[edge.src]
        dst = pos[edge.dst]
        if edge.kind == "down":
            a = anchor(src_n, src, "bottom")
            b = anchor(dst_n, dst, "top")
            points = [a, b] if abs(a[0] - b[0]) < 8 else [a, (a[0], (a[1] + b[1]) / 2), (b[0], (a[1] + b[1]) / 2), b]
            add(points, edge.label, label_at=label_near(a, b, edge.label), tag=f"down-{edge.src}")
        elif edge.kind == "right":
            if dst.cx < src.cx:
                a = anchor(src_n, src, "left")
                b = anchor(dst_n, dst, "right")
            else:
                a = anchor(src_n, src, "right")
                b = anchor(dst_n, dst, "left")
            points = [a, b] if abs(a[1] - b[1]) < 8 else [a, ((a[0] + b[0]) / 2, a[1]), ((a[0] + b[0]) / 2, b[1]), b]
            add(points, edge.label, label_at=label_near(a, b, edge.label), tag=f"right-{edge.src}")
        elif edge.kind in {"yes", "no"}:
            continue
        used.add(key)

    for edge in edges:
        if edge.kind != "yes":
            continue
        pair = [item for item in edges if item.src == edge.src and item.kind == "no"]
        if not pair:
            continue
        src = pos[edge.src]
        yes = pos[edge.dst]
        no = pos[pair[0].dst]
        stem = src.bottom + 14
        add([(src.cx, src.bottom), (src.cx, stem)], arrow=False, tag=f"fork-{edge.src}")
        add([(yes.cx, stem), (no.cx, stem)], arrow=False, tag=f"fork-bus-{edge.src}")
        add([(yes.cx, stem), (yes.cx, anchor(nodes[edge.dst], yes, "top")[1])], edge.label, label_at=(yes.cx, (stem + yes.top) / 2), tag=f"yes-{edge.dst}")
        add([(no.cx, stem), (no.cx, anchor(nodes[pair[0].dst], no, "top")[1])], pair[0].label, label_at=(no.cx, (stem + no.top) / 2), tag=f"no-{pair[0].dst}")

    return routes


def overlaps(a, b, pad=8):
    return not (
        a.right + pad <= b.left
        or b.right + pad <= a.left
        or a.bottom + pad <= b.top
        or b.bottom + pad <= a.top
    )


def render(bands, nodes, edges, branch, pos, regions, routes):
    del bands, edges, branch
    width = regions["canvas_w"]
    height = int(regions["canvas_h"])
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>']
    chips = [
        ("book", "预约 · 改草稿", "取消、同意、拒绝、改槽，只改草稿"),
        ("classify", "归类", "明确后向左交给预约，向右交给咨询"),
        ("consult", "咨询", "只回答已经明确的问题"),
    ]
    chip_w = 430
    for index, (key, title, duty) in enumerate(chips):
        x = 20 + index * (chip_w + 14)
        color = COLORS[key]
        parts.append(
            f'<rect x="{x}" y="14" width="{chip_w}" height="62" rx="8" fill="{color["bg"]}" stroke="{color["stroke"]}"/>'
        )
        parts.append(f'<rect x="{x}" y="14" width="8" height="62" fill="{color["head"]}"/>')
        parts.append(
            f'<text x="{x + 20}" y="36" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="15" font-weight="700" fill="{color["head"]}">{esc(title)}</text>'
        )
        parts.append(
            f'<text x="{x + 20}" y="58" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="12" fill="{INK}">{esc(duty)}</text>'
        )
    parts.append(
        '<text x="22" y="96" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="#5c6773">'
        "上端从左到右：预约改草稿、归类、咨询。下端：预约落单。向下继续，向旁是结果。虚线是回路。"
        "</text>"
    )

    for column in regions["columns"]:
        band = column["band"]
        color = COLORS[band["group"]]
        x, y, w, h = column["x"], column["y"], column["w"], column["h"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" '
            f'fill="{color["bg"]}" stroke="{color["stroke"]}" stroke-width="1.6"/>'
        )
        title_w = min(w, column["title_right"] - x)
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{title_w:.1f}" height="28" fill="{color["head"]}"/>'
        )
        parts.append(
            f'<text x="{x + 14:.1f}" y="{y + 19:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
            f'font-size="15" font-weight="700" fill="#ffffff">{esc(band["title"])}</text>'
        )
        for index, line in enumerate(column["duty_lines"]):
            parts.append(
                f'<text x="{x + 14:.1f}" y="{y + 48 + index * 16:.1f}" '
                f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(line)}</text>'
            )

    commit = regions["commit"]
    color = COLORS["book"]
    notch = commit["notch"]
    parts.append(
        f'<rect x="{commit["x"]:.1f}" y="{commit["y"]:.1f}" width="{commit["w"]:.1f}" height="{commit["h"]:.1f}" rx="12" '
        f'fill="{color["bg"]}" stroke="{color["stroke"]}" stroke-width="1.6"/>'
    )
    left_w = notch - 16 - commit["x"]
    if left_w > 20:
        parts.append(
            f'<rect x="{commit["x"]:.1f}" y="{commit["y"]:.1f}" width="{left_w:.1f}" height="28" fill="{color["head"]}"/>'
        )
    right_x = notch + 16
    right_w = commit["x"] + commit["w"] - right_x
    parts.append(
        f'<rect x="{right_x:.1f}" y="{commit["y"]:.1f}" width="{right_w:.1f}" height="28" fill="{color["head"]}"/>'
    )
    parts.append(
        f'<text x="{right_x + 12:.1f}" y="{commit["y"] + 19:.1f}" font-family="Microsoft YaHei, PingFang SC, sans-serif" '
        f'font-size="15" font-weight="700" fill="#ffffff">{esc(commit["title"])}</text>'
    )
    for index, line in enumerate(commit["duty_lines"]):
        parts.append(
            f'<text x="{right_x + 12:.1f}" y="{commit["y"] + 48 + index * 16:.1f}" '
            f'font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="12" fill="{INK}">{esc(line)}</text>'
        )

    for route in routes:
        parts.append(path_of(route.points, dotted=route.dotted, arrow=route.arrow))
    for route in routes:
        if not route.label:
            continue
        if route.label_at:
            lx, ly = route.label_at
        else:
            lx, ly = label_near(route.points[0], route.points[-1], route.label)
        parts.append(draw_label(lx, ly, route.label))

    band_group = {}
    for column in regions["columns"]:
        band_group[column["band"]["id"]] = column["band"]["group"]
    band_group["commit"] = "book"
    for nid, node in nodes.items():
        if nid not in pos:
            continue
        color = COLORS[band_group.get(node.band, "classify")]
        parts.append(draw_shape(node, pos[nid], color))

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M 0 1.2 L 9 5 L 0 8.8 z" fill="{ARROW}"/></marker></defs>\n'
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


def _between(value, left, right):
    return min(left, right) + 0.6 < value < max(left, right) - 0.6


def segments_cross(a, b, c, d):
    horizontal_ab = abs(a[1] - b[1]) < 0.6
    horizontal_cd = abs(c[1] - d[1]) < 0.6
    vertical_ab = abs(a[0] - b[0]) < 0.6
    vertical_cd = abs(c[0] - d[0]) < 0.6
    if horizontal_ab and horizontal_cd:
        if abs(a[1] - c[1]) > 0.8:
            return False
        return min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])) > 0.8
    if vertical_ab and vertical_cd:
        if abs(a[0] - c[0]) > 0.8:
            return False
        return min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])) > 0.8
    if horizontal_ab and vertical_cd:
        return _between(c[0], a[0], b[0]) and _between(a[1], c[1], d[1])
    if vertical_ab and horizontal_cd:
        return _between(a[0], c[0], d[0]) and _between(c[1], a[1], b[1])
    return False


def segment_hits_box(a, b, box):
    inset = 6
    left, top, right, bottom = box.left + inset, box.top + inset, box.right - inset, box.bottom - inset
    if right <= left or bottom <= top:
        return False
    if abs(a[1] - b[1]) < 0.6:
        y = a[1]
        if not (top < y < bottom):
            return False
        return min(max(a[0], b[0]), right) - max(min(a[0], b[0]), left) > 1
    if abs(a[0] - b[0]) < 0.6:
        x = a[0]
        if not (left < x < right):
            return False
        return min(max(a[1], b[1]), bottom) - max(min(a[1], b[1]), top) > 1
    return False


def trim_segment(a, b, start=7, end=16):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= start + end + 2:
        return None
    ux, uy = dx / length, dy / length
    return (a[0] + ux * start, a[1] + uy * start), (b[0] - ux * end, b[1] - uy * end)


def on_shape(node, box, x, y):
    if node.kind == "ask":
        nx = abs(x - box.cx) / (box.w / 2)
        ny = abs(y - box.cy) / (box.h / 2)
        return abs(nx + ny - 1) <= 0.08
    skew = 16 if node.kind in {"io", "out"} else 0
    on_top = abs(y - box.top) <= 3 and box.left + skew - 4 <= x <= box.right + 4
    on_bottom = abs(y - box.bottom) <= 3 and box.left - 4 <= x <= box.right - skew + 4
    on_left = abs(x - (box.left + skew / 2 if skew else box.left)) <= 4 and box.top - 3 <= y <= box.bottom + 3
    on_right = abs(x - (box.right - skew / 2 if skew else box.right)) <= 4 and box.top - 3 <= y <= box.bottom + 3
    return on_top or on_bottom or on_left or on_right


def report_routes(routes, nodes, pos):
    crosses = []
    pierces = []
    misses = []
    segments = []
    for route in routes:
        for index in range(len(route.points) - 1):
            segments.append((route.tag, route.points[index], route.points[index + 1], index == len(route.points) - 2 and route.arrow))
    for i, (tag_a, a1, a2, _) in enumerate(segments):
        for tag_b, b1, b2, _ in segments[i + 1 :]:
            if segments_cross(a1, a2, b1, b2):
                crosses.append(f"{tag_a} x {tag_b} | {a1[0]:.0f},{a1[1]:.0f}-{a2[0]:.0f},{a2[1]:.0f} | {b1[0]:.0f},{b1[1]:.0f}-{b2[0]:.0f},{b2[1]:.0f}")
        trimmed = trim_segment(a1, a2)
        if not trimmed:
            continue
        for nid, box in pos.items():
            node = nodes[nid]
            if on_shape(node, box, a1[0], a1[1]) or on_shape(node, box, a2[0], a2[1]):
                continue
            if segment_hits_box(trimmed[0], trimmed[1], box):
                pierces.append(f"{tag_a} through {nid}")
    for route in routes:
        if not route.arrow:
            continue
        end = route.points[-1]
        # 落在任一节点边界上即可。汇合线的终点就是目标。
        if not any(on_shape(nodes[nid], box, end[0], end[1]) for nid, box in pos.items()):
            misses.append(f"{route.tag} -> ({end[0]:.0f},{end[1]:.0f})")
    for item in crosses:
        print("cross", item)
    for item in pierces:
        print("pierce", item)
    for item in misses:
        print("miss", item)
    return crosses, pierces, misses


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
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        port += 1
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
                f"--window-size={width},{min(height, 8000)}",
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
    routes = build_routes(nodes, edges, pos, regions)
    crosses, pierces, misses = report_routes(routes, nodes, pos)
    svg = render(bands, nodes, edges, branch, pos, regions, routes)
    SVG.write_text(svg, encoding="utf-8")
    print(
        f"svg {regions['canvas_w']}x{int(regions['canvas_h'])} nodes {len(pos)} "
        f"overlaps {len(hits)} crosses {len(crosses)} pierces {len(pierces)} misses {len(misses)}"
    )
    if os.environ.get("SKIP_PNG") != "1" and not crosses and not pierces and not misses and not hits:
        export_png(regions["canvas_w"], int(regions["canvas_h"]))


if __name__ == "__main__":
    main()
