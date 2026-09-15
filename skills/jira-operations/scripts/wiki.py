# -*- coding: utf-8 -*-
"""Markdown → Jira wiki markup 转换（对齐设计 §9）。

最小转换集：标题 #~### → h1.~h3.、无序列表 - → *、有序列表 1. → #、
代码块 ``` → {code}、行内代码 ` → {{}}、粗体 **x** → *x*、
表格 → ||表头|| / |单元格|。

正文中的 wiki 元字符 { [ * _ ? - + ^ ~ 必须转义，否则 Jira 渲染错乱。
"""

import re

_META_CHARS = set("{[*_?-+^~")
_INLINE_TOKEN = re.compile(r"(`[^`\n]+`)|(\*\*[^*\n]+\*\*)")
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_ULIST = re.compile(r"^(\s*)-\s+(.*)$")
_OLIST = re.compile(r"^(\s*)\d+\.\s+(.*)$")


def escape_wiki(text):
    """转义 wiki 元字符。"""
    out = []
    for ch in text:
        if ch in _META_CHARS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _inline(text):
    """处理行内代码与粗体，其余正文转义元字符。"""
    out = []
    pos = 0
    for m in _INLINE_TOKEN.finditer(text):
        out.append(escape_wiki(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append("{{" + m.group(1)[1:-1] + "}}")
        else:
            out.append("*" + escape_wiki(m.group(2)[2:-2]) + "*")
        pos = m.end()
    out.append(escape_wiki(text[pos:]))
    return "".join(out)


def _is_table_line(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and len(s) > 1


def _is_table_separator(line):
    s = line.strip()
    return bool(s) and set(s) <= set("|-: ") and "-" in s


def _convert_table(lines):
    """把 markdown 表格行列表转成 wiki 表格。首行表头用 ||，其余用 |。"""
    out = []
    first = True
    for line in lines:
        if _is_table_separator(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        sep = "||" if first else "|"
        out.append(sep + sep.join(_inline(c) for c in cells) + sep)
        first = False
    return out


def md_to_wiki(text):
    lines = text.split("\n")
    out = []
    in_code = False
    table_buf = []

    def flush_table():
        if table_buf:
            out.extend(_convert_table(table_buf))
            del table_buf[:]

    for line in lines:
        if line.strip().startswith("```"):
            flush_table()
            out.append("{code}")
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        if _is_table_line(line):
            table_buf.append(line)
            continue
        flush_table()
        m = _HEADING.match(line)
        if m:
            out.append("h%d. %s" % (len(m.group(1)), _inline(m.group(2))))
            continue
        m = _ULIST.match(line)
        if m:
            out.append("%s* %s" % (m.group(1), _inline(m.group(2))))
            continue
        m = _OLIST.match(line)
        if m:
            out.append("%s# %s" % (m.group(1), _inline(m.group(2))))
            continue
        out.append(_inline(line))
    flush_table()
    if in_code:
        out.append("{code}")  # 未闭合的代码块兜底闭合
    return "\n".join(out)
