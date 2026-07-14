# skills

跨 Agent 通用技能仓库(唯一真源 / SSOT）。同一份 `SKILL.md` 同时供 **Claude Code** 与 **Codex (ChatGPT)** 加载,避免多处副本漂移。

## 结构

```
skills/                 # 所有技能,每个一个目录,内含 SKILL.md(+ 可选附件/子目录)
scripts/sync.sh         # 幂等脚本:把 skills/ 软链到 Claude 与 Codex 的技能目录
.claude-plugin/         # 可选:作为 Claude 插件被 /plugin 安装时的清单
```

技能格式为通用 Agent Skills 形式:目录 + `SKILL.md`(YAML frontmatter `name`/`description` + Markdown 正文)。Claude 与 Codex 均可直接识别。

## 使用

```bash
git clone git@github.com:czyjava/skills.git ~/work/codes/skills
cd ~/work/codes/skills
./scripts/sync.sh            # 建立软链,两端立即加载
./scripts/sync.sh --status   # 只查看当前链接状态,不改动
```

- **新增/修改技能**:直接编辑 `skills/<name>/`,`git commit` 即可,两端软链自动指向最新内容。
- **换机器**:`git clone` + `./scripts/sync.sh` 全部恢复。

## 加载方式

- **Claude Code**:`sync.sh` 将每个技能软链进 `~/.claude/skills/`(默认)。也可改用插件式:`/plugin marketplace add ~/work/codes/skills` 后安装。
- **Codex (ChatGPT)**:`sync.sh` 将每个技能软链进 `~/.codex/skills/`。
