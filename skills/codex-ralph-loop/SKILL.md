---
name: codex-ralph-loop
version: 0.1.0
description: Codex+Ralph loop coding workflow (one task one commit, contract-driven)
---

# codex-ralph-loop — SKILL

## What this skill is
A repeatable, low-risk workflow for **shipping code via local `codex` CLI** using a **Ralph loop** task breakdown:
- small tasks
- one task → one commit
- contract-driven constraints (single source of truth)
- minimal context prompts (avoid token bloat)

This skill is optimized for Pixel Studio-style backend work, but the loop is reusable.

---

## When to use
Use this skill when the user asks for any of:
- “用 codex 写代码/不允许你自己写”
- “按拉尔夫循环拆任务”
- “每个任务一个 commit”
- “上下文太大，需要稳定可复用流程”

---

## Hard constraints (must follow)
1. **All code changes must be produced by `codex`**, not manually authored by the assistant.
   - The assistant may: plan, decompose, review diffs, run git/misc commands, commit.
   - The assistant must not: directly write/patch source files outside codex runs.
2. **One task = one commit** (unless user explicitly allows squashing).
3. **Single source of truth** for rules:
   - Create/maintain a short `docs/**/CONTRACT.md` in the repo.
   - Every codex prompt must reference the contract; do not paste long docs repeatedly.
4. **No external integrations unless explicitly requested**.
   - For “define ACL only”: create interfaces + models + call sites; keep implementations stubbed.

---

## Ralph loop (task anatomy)
Each task must be closed-loop and auditable.

### R0 — Prepare
- ensure clean git state (stash if needed)
- create a feature branch
- verify `codex` CLI is available

### R1 — Skeleton
- module structure / pom / basic markers
- compile boundary if toolchain available

### R2 — Common layer
- enums/constants
- DTOs/requests/responses
- QueryBOs

### R3 — Entity/DAO
- entities aligned to DDL/contract
- DAO signatures aligned to existing project style

### R4 — Service
- BizService skeleton + minimal rules
- ACL interfaces only (no SDK details)

### R5 — Action/API
- thin Action layer, validation, delegation
- forbid endpoints that violate the contract

### R6 — Read-only features first
- implement “query/read” endpoints before “write/mutate” when feasible

### R7 — Verification
- best-effort compile/test
- if toolchain missing: stop at syntax-level confidence + file list

---

## Context minimization rules
- **Never paste full design docs into prompts**.
- Prompts should include only:
  - contract path(s)
  - the exact scope (modules/files)
  - precise acceptance criteria for this task
- Prefer “codex, please open file X and adjust Y” over pasting big snippets.

---

## Codex execution template
Use `codex exec --full-auto` and a heredoc prompt.

### Prompt template (copy/paste)

**System / role**
- You are Codex CLI coding agent.

**Contract**
- Strictly follow: `docs/<project>/CONTRACT.md`.

**Scope**
- Only modify: <module(s)>
- Do not modify: <forbidden paths>

**Task**
- Implement: <single feature>

**Acceptance criteria**
- <bullet list>

**Output**
- Summary + modified file list
- Do NOT git commit

---

## Commit discipline
After codex finishes:
1. `git status --porcelain`
2. `git diff` (spot-check)
3. `git add <scoped paths>`
4. `git commit -m "<prefix>: <task>"`

Commit message conventions:
- `workorder: ...` for feature work
- `docs(...): ...` for docs-only
- Keep <= 72 chars if possible

---

## Pixel Studio-specific defaults (optional)
If working in Pixel Studio repo unless told otherwise:
- Action thin, BizService thick
- DAO via QueryBO + SqlPath style
- Admin pages prefer flattened columns for ops
- For external systems: define **ACL interfaces** only; implementations may be stubs

---

## Safety / guardrails
- Avoid destructive operations.
- If a change might affect prod behavior broadly, isolate behind feature flag / stub and keep minimal.
- If build tools are unavailable, clearly report verification limits.

---

## Checklist for the assistant
- [ ] Branch created
- [ ] Contract exists & referenced
- [ ] Task is small & closed-loop
- [ ] Codex run produced the code
- [ ] One task → one commit
- [ ] Updated file list recorded in response
- [ ] Best-effort verification executed (or limitation reported)
