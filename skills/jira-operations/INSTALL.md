# zq-jira-query 快速安装

1. 解压本压缩包，进入解压后的工程根目录。
2. 执行一键安装：

   ```bash
   python3 install.py
   ```

   安装脚本会自动完成：释放 AI 技能到各工具目录、替换内部绝对路径、同步技能入口完整实体文件（全平台无软链）、生成 `jira_config.json` 配置模板、跑单元测试。

3. 编辑 `jira_config.json`，填入各 Jira 源的 `base_url` / `username` / `password`（字段含义见 `project-docs/deploy/第三方部署手册.md` 第四节）。
4. 再跑一次 `python3 install.py --check-only`，验证凭据与网络连通性。

完成。日常用自然语言让 AI 助手（Claude Code / Kimi CLI，在工程根新开会话）调用，或直接命令行调 `scripts/jira_cli.py`，示例见部署手册第七节。

可选：`python3 install.py --user` 会额外把技能装到用户级目录（`~/.claude/skills/` 与 `~/.agents/skills/`），在任意目录下都能被 AI 助手加载。

环境要求：Python 3（只用标准库，无需 pip 安装任何依赖），macOS / Linux / Windows 均可。
