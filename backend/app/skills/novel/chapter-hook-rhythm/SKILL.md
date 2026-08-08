---
name: chapter-hook-rhythm
title: Chapter Hook and Rhythm
description: A project-local method for planning chapter openings, escalation and ending hooks before prose generation.
skill_type: workflow
version: 1.0.0
category: novel
tags: [novel, chapter, hook, rhythm, method]
triggers:
  keywords: [chapter hook, opening hook, rhythm, pacing, paywall point]
  context_keys: [creative_project_context, chapter_contract]
  tools: [generate_chapter_outline, generate_novel_body]
requires_tools: [generate_chapter_outline]
risk: read
creative:
  compatible_project_types: [novel]
  compatible_genres: ["*"]
  stages: [chapter_outline, novel_body, prose_draft, prose_rewrite, directed_rewrite]
  context_contribution: "Treat the chapter contract as an executable method: open with a concrete disturbance, escalate through visible choices, pay off one promise, and end with a specific forward-pulling hook. Keep the method subordinate to locked project facts and the user's chosen genre."
  input_schema: {chapter_contract: object, previous_context: string, project_rules: array}
  output_schema: {opening_hook: string, escalation_beats: array, payoff: string, ending_hook: string}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# Chapter Hook and Rhythm

Use this as a method reference, not as a replacement for the chapter outline.

1. Identify the chapter's concrete disturbance within the opening scene.
2. Turn the chapter goal into visible choices, resistance and consequences.
3. Make at least one promised element pay off in the chapter instead of adding only explanation.
4. End on a specific unresolved action, discovery or decision that naturally demands the next chapter.
5. Check continuity against the project context and never invent a fact that conflicts with locked canon.

The method produces a candidate plan. It does not promote prose, accept facts, activate foreshadowing or publish content.
