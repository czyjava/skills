---
name: requirements-analyst
description: Analyze requirement documents before design/development. Use when the user wants you to read a PRD, requirement link, meeting notes, or product comments; produce requirement understanding, user stories, and questions for product clarification; and iteratively refine the document based on product feedback until approved.
---

# Requirements Analyst

Use this skill when the user wants a **BA-style requirement analysis loop**, especially for tasks like:
- reading a PRD / requirement document / online requirement link
- understanding business goals and scope
- producing **需求理解** and **用户故事**
- identifying ambiguities and forming **待确认问题**
- revising the analysis based on **产品评论 / 批注 / 反馈**
- iterating multiple rounds until the product owner accepts the wording

Do **not** use this skill for:
- direct coding or implementation work
- detailed front-end/back-end task decomposition as the primary output
- writing technical design docs first
- skipping unclear business rules and jumping straight into development plans

## Core principle

This skill is for the **pre-implementation alignment phase**.

The default goal is:
1. understand what the product requirement is really trying to do
2. expose unclear parts
3. turn that understanding into a stable written draft
4. refine the draft repeatedly based on product comments
5. stop when the product side认可/确认 through explicit feedback

## Working mode

### Phase 1: Read and extract
Read the requirement material and extract:
- business background
- target users / roles
- problem to solve
- business goals
- scope and boundary
- key business changes
- explicit facts vs inferred assumptions

Accepted input forms:
- markdown / text / pdf / docx
- requirement web links
- meeting notes
- chat excerpts
- screenshots / pasted text
- product comments on a previous draft

If the document is behind authentication, try available reading methods first. If access is blocked, clearly state what is blocking access and ask for the minimum missing material.

### Phase 2: First draft output
Produce a first draft with these sections:

## 1. 需求理解
Focus on:
- 需求背景
- 要解决的问题
- 目标用户
- 本期目标
- 核心业务变化
- 范围边界
- 关键假设

## 2. 用户故事
Use this format by default:
- 作为 `<用户角色>`
- 我希望 `<完成某个动作>`
- 以便 `<获得某种价值>`

Only add acceptance criteria when it helps clarify business intent. Do not over-expand into engineering details unless explicitly asked.

## 3. 待确认问题
List unresolved items that need product clarification before downstream work.

Prefer grouping questions into:
- 业务规则待确认
- 页面/链路承接待确认
- 状态定义待确认
- 范围边界待确认
- 数据口径/统一表述待确认

### Phase 3: Product comment iteration
When the user provides product comments, treat them as the next revision input.

For each revision round:
1. read all comments carefully
2. classify each comment into one of:
   - 事实修正
   - 范围调整
   - 表述优化
   - 新增约束
   - 新增问题
3. update the draft accordingly
4. keep the structure stable unless the user asks for a new format
5. explicitly summarize what changed in this round

Default revision output structure:

## 本轮评论吸收
- 评论 1 → 如何处理
- 评论 2 → 如何处理
- 评论 3 → 如何处理

## 更新后的需求理解
## 更新后的用户故事
## 更新后的待确认问题
## 仍需产品确认的点（如果有）

## Practical rules

### Rule 1: Do not jump to implementation too early
Unless the user explicitly asks for engineering decomposition, stay in the BA lane:
- understand
- clarify
- align
- refine

### Rule 2: Separate fact from inference
When you infer something from the material, label it as:
- 我的理解
- 初步判断
- 假设前提

Do not present inferred content as confirmed fact.

### Rule 3: Prefer useful questions over vague questions
Bad:
- 这里是不是还要再确认一下？

Good:
- 被邀请人的“体验产品”最终落到哪个页面？是下载页、注册页还是 App 内某个体验页？

### Rule 4: Optimize for product review
Write drafts that are easy for product managers to comment on:
- concise sections
- explicit assumptions
- specific unresolved questions
- stable wording across rounds

### Rule 5: Preserve business intent
When revising, do not mechanically rewrite. Preserve:
- original business goal
- role definitions
- scope boundaries
- changed rules confirmed by product comments

## Recommended default output style

Keep the tone professional and concise. Prefer:
- short section headers
- bullet points for key conclusions
- user stories grouped by module or role
- questions phrased so product can answer directly

## Suggested section template

# 需求分析初稿 / 修订稿

## 一、需求理解
### 1. 背景
### 2. 要解决的问题
### 3. 目标用户
### 4. 本期目标
### 5. 核心业务变化
### 6. 范围边界
### 7. 假设与风险

## 二、用户故事
### 模块 A
- 作为...
- 我希望...
- 以便...

## 三、待确认问题
### P0（不确认会影响理解）
### P1（建议确认，避免后续返工）

## 四、如果是修订稿：本轮变更说明
- 根据产品评论修订了什么
- 哪些问题已经闭环
- 哪些问题仍待确认

## Exit condition

A round is considered complete when one of these is true:
- the user says this version is accepted by product
- the user asks to pause iteration
- the remaining unresolved items are explicitly parked as future decisions

## Deliverable expectation

The main deliverables of this skill are always:
1. 需求理解
2. 用户故事
3. 待确认问题

Optional add-ons only when requested:
- 功能点清单
- 验收标准
- 评审纪要
- 研发拆分
- Jira 任务草案

## Notes for repeated collaboration

If the same requirement goes through multiple rounds:
- keep terms consistent across rounds
- avoid changing section structure without reason
- track what changed each round
- prefer editing the existing understanding rather than rewriting from zero every time
