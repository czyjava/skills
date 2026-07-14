---
name: pixel-studio-local-dev
description: Use when the user asks to switch Pixel Studio into or out of local development/startup mode, says “切回本地开发”, “本地启动”, “恢复仓库态”, “切换开发分支”, or needs the Pixel Studio local-only patch applied/removed via git ps-local-on/off.
---

# Pixel Studio 本地开发切换

## 适用范围

只用于 Pixel Studio 仓库：

```text
/Users/chenzhiyuan/work/codes/wmxs/pixel-studio
```

本技能管理一组“不提交、不推送、仅本地启动需要”的改动：

- `git ps-local-on`：应用 `.git/info/pixel-studio-local-start.patch`，切到本地启动态。
- `git ps-local-off`：反向撤销该 patch，恢复仓库态。
- patch 文件实际应从 `git rev-parse --git-common-dir` 定位，保证 Git worktree 中也能复用同一份本地启动态 patch。

当前本地启动态 patch 主要包含：

- `MqConfig`：关闭 Redis Stream 主题消费，避免本地启动消费测试环境消息。
- `EventBridgeConfig`：关闭 EventBridge listener，避免本地排障时消费测试环境订阅事件。
- `application-dev.properties`：切到本地 Redis、关闭 EventBridge listener、关闭本地非必要的 FFmpeg 依赖预检和证件照 FaceParsing 启动预加载；装修助手 Codex HTTP token 不写入本地 patch，需要通过外部配置或启动参数提供。
- `logback.xml`：日志写入工程内相对目录，并屏蔽本地慢 SQL 轮询噪音。
- `OrderCenterConfig`：关闭本地不需要的订单中心配置。
- `FFmpegDependencyChecker`：支持按配置关闭启动时依赖预检。
- `FaceParsingDetector`：支持按配置跳过启动时模型预加载。

## 默认流程

1. 进入 Pixel Studio 仓库并先执行 `git status --short --branch`。
2. 如果用户要“切回本地开发 / 本地启动 / 切到本地启动态”，执行 `git ps-local-on`。
3. 如果用户要“切分支 / 提交 / 恢复仓库态”，先执行 `git ps-local-off`。
4. 执行后再次检查 `git status --short --branch`，明确告诉用户当前是本地启动态还是仓库态。

## 切换开发分支

当用户要求切换 Pixel Studio 开发分支时：

1. 先执行 `git ps-local-off`，把本地启动态收回去。
2. 检查工作区。若仍有其他改动，先说明剩余改动并暂停，不要擅自覆盖、丢弃或混入切分支。
3. 工作区干净后再执行 `git switch <branch>` 或按用户指定方式切分支。
4. 如果用户同时要求“切回本地开发 / 本地启动”，切分支成功后执行 `git ps-local-on`。

## 缺失或冲突处理

- 如果 `git ps-local-on/off` 不存在，但 `.git/info/pixel-studio-local-start.patch` 存在，可以补齐仓库本地 alias。
- 如果 patch 不存在，停止并说明需要重新从本地启动态 diff 生成 patch。
- 如果 `git ps-local-on/off` 报冲突，停止并说明冲突文件，不要自动改代码。
- 提交业务代码前必须确保 `git ps-local-off` 已执行，且本地启动态文件没有进入暂存区。

## 常用验证命令

```bash
git status --short --branch
git apply --check .git/info/pixel-studio-local-start.patch
git apply -R --check .git/info/pixel-studio-local-start.patch
git config --get-regexp '^alias\.ps-local-'
```
