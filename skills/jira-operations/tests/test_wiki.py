# -*- coding: utf-8 -*-
"""wiki.py 测试：Markdown → wiki markup 最小转换集 + 元字符转义。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import wiki


class TestMdToWiki(unittest.TestCase):
    def test_标题(self):
        self.assertEqual(wiki.md_to_wiki("# 一"), "h1. 一")
        self.assertEqual(wiki.md_to_wiki("## 二"), "h2. 二")
        self.assertEqual(wiki.md_to_wiki("### 三"), "h3. 三")

    def test_无序列表(self):
        self.assertEqual(wiki.md_to_wiki("- 甲\n- 乙"), "* 甲\n* 乙")

    def test_有序列表(self):
        self.assertEqual(wiki.md_to_wiki("1. 甲\n2. 乙"), "# 甲\n# 乙")

    def test_代码块(self):
        self.assertEqual(wiki.md_to_wiki("```\nprint(1)\n```"),
                         "{code}\nprint(1)\n{code}")

    def test_未闭合代码块兜底(self):
        self.assertEqual(wiki.md_to_wiki("```\ncode"), "{code}\ncode\n{code}")

    def test_行内代码(self):
        self.assertEqual(wiki.md_to_wiki("执行 `ls -l` 查看"),
                         "执行 {{ls -l}} 查看")

    def test_粗体(self):
        self.assertEqual(wiki.md_to_wiki("这是**重点**内容"), "这是*重点*内容")

    def test_表格(self):
        md = "| 名称 | 数量 |\n| --- | --- |\n| 苹果 | 3 |"
        self.assertEqual(wiki.md_to_wiki(md), "||名称||数量||\n|苹果|3|")

    def test_元字符转义(self):
        self.assertEqual(wiki.md_to_wiki("a*b"), "a\\*b")
        self.assertEqual(wiki.md_to_wiki("1+1=2"), "1\\+1=2")
        self.assertEqual(wiki.md_to_wiki("x_y"), "x\\_y")
        self.assertEqual(wiki.md_to_wiki("好吗?"), "好吗\\?")
        self.assertEqual(wiki.md_to_wiki("[备注]"), "\\[备注]")
        self.assertEqual(wiki.md_to_wiki("~删除~"), "\\~删除\\~")
        self.assertEqual(wiki.md_to_wiki("^上标"), "\\^上标")
        self.assertEqual(wiki.md_to_wiki("a-b"), "a\\-b")

    def test_生成的标记不被转义(self):
        out = wiki.md_to_wiki("## 标题\n- **重点** `cmd`")
        self.assertEqual(out, "h2. 标题\n* *重点* {{cmd}}",
                         "转换生成的 markup 不应被二次转义")

    def test_代码块内不转义(self):
        out = wiki.md_to_wiki("```\na*b {x}\n```")
        self.assertEqual(out, "{code}\na*b {x}\n{code}",
                         "代码块内容应原样保留")


if __name__ == "__main__":
    unittest.main()
