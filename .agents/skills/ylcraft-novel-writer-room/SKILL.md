---
name: ylcraft-novel-writer-room
description: Run and inspect YLCraft creative-project novel writer-room workflows. Use when Codex needs to improve chapter prose, run scene beats, character rehearsal, prose draft, humanization, review, targeted rewrite, inspect writer-room logs, export novel text, or promote approved writer-room output into `novel_body` inside the YLCraft repo.
---

# YLCraft Novel Writer Room

Use the local YLCraft API or repo workflow CLI. Prefer API-backed operations over direct database writes so project content versions and generation logs stay visible in the frontend.

Default API base:

```text
http://127.0.0.1:8000/api/v1
```

Default long-prose model when the user says “用 deepseekv4 那个写”:

```text
provider=deepseek
model=deepseek-v4-pro
```

## Workflow

1. Inspect the project before writing.
2. Run writer-room steps for the target chapter.
3. Inspect generated contents and logs.
4. Do targeted rewrite when review issues are concrete.
5. Promote only after the user approves or explicitly asks to promote.
6. Export ordered novel text when the user asks for a readable manuscript.

Recommended step order:

```text
scene_beats -> character_rehearsal -> prose_draft -> prose_humanized -> prose_review -> prose_rewrite
```

Run the recommended review flow before final prose:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter <n> --provider deepseek --model deepseek-v4-pro --steps scene_beats character_rehearsal prose_draft prose_humanized prose_review --continue-on-error
```

Run targeted rewrite from review:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter <n> --step prose_rewrite --instruction "按主编意见重写，保留剧情事实，压低解释感，增加动作、物件互动和潜台词" --provider deepseek --model deepseek-v4-pro
```

Promote only after approval:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-promote --project-id <id> --content-id <writer-room-content-id>
```

## Guardrails

- Do not overwrite approved `novel_body` through writer-room steps. Writer-room steps create candidate content.
- Treat promote as a manual approval checkpoint.
- Keep provider/model explicit when the user specified one.
- Inspect generation logs after failures before retrying.
- Do not start image generation until prose, script, storyboard, and reference matching are stable.

## References

Read `references/workflow.md` for command examples, endpoint names, and content types.
