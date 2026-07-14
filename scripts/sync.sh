#!/usr/bin/env bash
#
# sync.sh — 把本仓库 skills/ 下的技能软链到 Claude 与 Codex 的技能目录。
# 幂等:重复运行只会修正链接;绝不覆盖已存在的“真目录/真文件”。
#
# 用法:
#   ./scripts/sync.sh            建立/修正软链
#   ./scripts/sync.sh --status   只查看状态,不改动
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/skills"

# 目标端:Claude 与 Codex 的用户级技能目录
TARGETS=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
)

STATUS_ONLY=0
[[ "${1:-}" == "--status" ]] && STATUS_ONLY=1

link_one() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    local cur; cur="$(readlink "$dest")"
    if [[ "$cur" == "$src" ]]; then
      echo "  ok      $dest"
    elif [[ "$STATUS_ONLY" == 1 ]]; then
      echo "  relink? $dest -> $cur (期望 $src)"
    else
      ln -sfn "$src" "$dest"; echo "  relinked $dest"
    fi
  elif [[ -e "$dest" ]]; then
    echo "  SKIP(真实文件/目录,未动) $dest"
  elif [[ "$STATUS_ONLY" == 1 ]]; then
    echo "  missing $dest"
  else
    ln -s "$src" "$dest"; echo "  linked  $dest"
  fi
}

for base in "${TARGETS[@]}"; do
  echo "== $base =="
  if [[ "$STATUS_ONLY" == 0 ]]; then mkdir -p "$base"; fi
  for dir in "$SRC_DIR"/*/; do
    name="$(basename "$dir")"
    link_one "${dir%/}" "$base/$name"
  done
done

echo "完成。共 $(find "$SRC_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') 个技能。"
