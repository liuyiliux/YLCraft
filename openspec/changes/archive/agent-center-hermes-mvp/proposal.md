# Agent Center Hermes MVP

## Why

YLCraft already has many functional modules, but the Agent page is still mostly a chat shell. The next useful step is a standalone Agent Center that can call YLCraft project tools, remember user/project preferences, and run configurable specialized agents.

## What Changes

- Add configurable agent profiles with system prompt, tool permissions, model preference and execution limits.
- Fix the existing Agent API/session/tool registry path so the Agent Center can actually list tools and chat reliably.
- Add creative-project tools to the Agent tool registry.
- Update the Agent page to expose profile configuration and project-aware tools.

## Non-Goals

- Do not introduce a heavy external multi-agent framework in this MVP.
- Do not allow agents to overwrite approved creative content without explicit tool/action confirmation.
- Do not add cloud-hosted agent execution.
