# -*- coding: utf-8 -*-
"""真实 Jira 集成测试包。

作用是让 `python3 -m unittest discover tests` 能递归发现本目录下的用例 ——
发现得到、但因为类上的 `@unittest.skipUnless(JIRA_IT == "1")` 闸门全部 skip，
所以默认离线跑法看到的是「skipped」而不是「error」，回归基线不会被连真 Jira 的用例打红。
单独跑集成测试用：

    JIRA_IT=1 JIRA_IT_KEYS=XMKFB-123 python3 -m unittest discover tests/integration
"""
