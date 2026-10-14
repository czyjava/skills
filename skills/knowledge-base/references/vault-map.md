# Obsidian 知识库映射

更新时间：2026-10-14。

## 当前的库

用户用四个知识库，Obsidian 里也只登记这四个。都放在 `~/work/doc/` 下，显示名就是目录名。

| 库 | 路径 | 放什么 | 规则文件 | 同步方式 |
|---|---|---|---|---|
| `wmxs` | `~/work/doc/wmxs` | 完美像素业务线（`~/work/codes/wmxs` 下的项目）的项目知识、需求交付文档和跨项目规范 | `README.md` | Git，有私有远端，obsidian-git 自动同步 |
| `sfs` | `~/work/doc/sfs` | 共享基础服务领域的知识图谱 | `CONVENTIONS.md` | 留在公司工作目录和授权存储 |
| `feed` | `~/work/doc/feed` | 信息流广告投放：投放系统 `feed-pilot` 和广告素材生产 `ad-creative` 的项目知识 | `README.md` | 本地 Git，无远端，obsidian-git 只在本地自动提交 |
| `learn` | `~/work/doc/learn` | 个人学习笔记：概念笔记、主题地图、来源摘要 | `README.md` | Git，有私有远端，obsidian-git 自动同步 |

前三个是工作库，`learn` 是个人库，2026-10-14 建立。

旧的个人库 `~/Documents/Obsidian Vault` 2026-10-13 停用，2026-10-14 删除。`learn` 不是它的延续，只放学习笔记。

## 项目和库的对应

业务域、仓库和项目知识库的对应关系见 `~/work/doc/wmxs/projects/INDEX.md`，由 `_scripts/wmxs.py index` 按 `~/work/codes/wmxs/<业务域>/` 的现状生成。信息流投放的两个项目见 `~/work/doc/feed/projects/INDEX.md`。

## 关联规则

- 当前项目在 `~/work/codes/wmxs`、公司代码或公司工作目录内：只检索相应的工作库。
- 用户说“记到学习库”“我想学 X”：写入 `learn`，在哪个项目目录下都一样。
- 当前项目在 homelab、家庭设备、NAS 或装修范围内：没有对应的知识库。服务器和机器的变更记在 homelab 仓库；其余需要沉淀时先问用户放哪里。
- 不跨库复制原文。
- 只需要原始文件时用文件目录；需要结论、索引或长期复用时才写入知识库。
