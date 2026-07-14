---
name: production-image-audit
description: Use when the user asks to inspect recent production image generation tasks, compare uploaded input images with generated outputs, audit prompt adherence, summarize quality issues, or propose prompt/skill improvements from live server data.
---

# Production Image Audit

## Scope

Use this for production QA of image-generation workflows: pull recent tasks from the server database, compare input/output images, read the user prompt and structured fields, then summarize quality issues and prompt/skill improvement points.

For `decoration-assistant` on `47.251.185.234`, use the `wanmeixiangsu-server-ssh` skill for connection facts and safety checks.

## Workflow

1. Confirm the audit window, role, and target service. Default: last 2 hours, `interior_renovation_rendering`, `/data/decoration-assistant-data`.
2. Run the bundled sheet generator instead of hand-writing SQL/PIL/scp each time:

```bash
/Users/chenzhiyuan/.agents/skills/production-image-audit/scripts/collect_image_audit.py \
  --hours 2 \
  --role interior_renovation_rendering
```

It creates a local audit folder with `manifest.tsv`, `sheet_*.jpg`, and `audit_notes.md`.

3. Inspect every sheet image visually. When detail matters, fetch or open the original input/output image for that row.
4. Compare against the prompt, not only against taste. Judge whether the output satisfies the selected role, room/type/style fields, user supplement, and reference-image constraints.
5. Report findings before recommendations. Separate isolated sample issues from reusable skill/prompt improvements.

## Review Rubric

- Prompt adherence: requested role/type/style/color tone and user supplement are visible.
- Reference fidelity: camera, shell, main walls, windows/doors, fixed openings, and fixed large elements remain believable.
- Functional validity: furniture, fixtures, circulation, privacy, plumbing, lighting, safety, and maintenance access work for the requested room or scene.
- Finish quality: unfinished surfaces, construction debris, raw brick/concrete, exposed pipes/wires, and temporary objects are resolved when a finished rendering is requested.
- Style strength: style is dominant without overriding structure or function.
- Regression risk: note when a proposed prompt change may damage previously good behavior; prefer compressing and clarifying rules over adding long rule stacks.

## Output Shape

Keep the summary concise:

- Audit window, count, statuses, and any missing files.
- Links or rendered images for the comparison sheets.
- Overall judgment.
- Per-sample findings with severity only where useful.
- Reusable optimization points for prompt/skill/SCL, grouped by priority.
- Explicitly say when the sample set lacks coverage for an important case.

## Common Mistakes

- Counting log lines that only installed a skill as real role tasks. Query the DB by session role.
- Downloading full originals first. Generate thumbnail sheets on the server, then fetch originals only for suspicious samples.
- Letting one bad sample cause broad prompt bloat. Prefer a smaller priority rule or a sharper failure condition.
