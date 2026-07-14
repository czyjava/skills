#!/usr/bin/env bash
#
# sync.sh — 把本仓库 skills/ 下的技能软链到 Claude 与 Codex 的技能目录。
# 幂等:重复运行只会修正链接;绝不覆盖已存在的“真目录/真文件”。
# 默认还会 prune:清理“指向本仓库但源已删除”的悬空软链(删技能后同步用)。
#
# 用法:
#   ./scripts/sync.sh            建/修软链 + 清理本仓库的悬空软链
#   ./scripts/sync.sh --status   只查看状态,不改动
#   ./scripts/sync.sh --prune    只清理悬空软链,不新建
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/skills"

# 目标端:Claude 与 Codex 的用户级技能目录
TARGETS=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
)

MODE="sync"
case "${1:-}" in
  --status) MODE="status" ;;
  --prune)  MODE="prune" ;;
  "")       MODE="sync" ;;
  *) echo "未知参数: $1(可用: --status | --prune)"; exit 2 ;;
esac

link_one() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    local cur; cur="$(readlink "$dest")"
    if [[ "$cur" == "$src" ]]; then
      echo "  ok      $dest"
    elif [[ "$MODE" == "status" ]]; then
      echo "  relink? $dest -> $cur (期望 $src)"
    else
      ln -sfn "$src" "$dest"; echo "  relinked $dest"
    fi
  elif [[ -e "$dest" ]]; then
    echo "  SKIP(真实文件/目录,未动) $dest"
  elif [[ "$MODE" == "status" ]]; then
    echo "  missing $dest"
  else
    ln -s "$src" "$dest"; echo "  linked  $dest"
  fi
}

# 清理:仅删除“指向本仓库 SRC_DIR 且源已不存在”的悬空软链。
prune_base() {
  local base="$1"
  [[ -d "$base" ]] || return 0
  local dest cur
  for dest in "$base"/*; do
    [[ -L "$dest" ]] || continue
    cur="$(readlink "$dest")"
    # 只处理指向本仓库的软链
    [[ "$cur" == "$SRC_DIR/"* ]] || continue
    # 源仍存在则保留
    [[ -e "$cur" ]] && continue
    if [[ "$MODE" == "status" ]]; then
      echo "  prune?  $dest (源已删除: $cur)"
    else
      rm "$dest"; echo "  pruned  $dest"
    fi
  done
}

for base in "${TARGETS[@]}"; do
  echo "== $base =="
  [[ "$MODE" == "status" ]] || mkdir -p "$base"
  if [[ "$MODE" != "prune" ]]; then
    for dir in "$SRC_DIR"/*/; do
      link_one "${dir%/}" "$base/$(basename "$dir")"
    done
  fi
  # sync 与 prune 模式都做清理;status 模式只报告
  [[ "$MODE" == "sync" || "$MODE" == "prune" || "$MODE" == "status" ]] && prune_base "$base"
done

echo "完成。源共 $(find "$SRC_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') 个技能。"
