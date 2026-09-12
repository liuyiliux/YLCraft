# Creative Project Workflow Specification

创作项目工作流负责把原创创意、小说章节和素材转成可持续推进的小说、短剧、漫画项目。

## ADDED Requirements

### Requirement: Creative project as primary workflow unit

The system SHALL provide a creative project entity that stores project type, source type, current stage, status, settings and structured generation outputs.

#### Scenario: Create project from original idea
- **WHEN** the user enters an idea and creates a project
- **THEN** the system creates a creative project with source_type `original_idea`
- **AND** the project starts at stage `outline`

#### Scenario: Create project from downloaded novel
- **WHEN** the user selects a downloaded novel and one or more chapters
- **THEN** the system creates a creative project with source_type `novel`
- **AND** stores the novel id and selected chapter ids in source metadata

### Requirement: Story outline JSON contract

The system SHALL generate and store story outlines using a strict JSON contract containing title, genre, logline, target reader, tone, worldview, main conflict, themes, characters, relationship map, story arc and visual style.

#### Scenario: Generate outline from idea
- **WHEN** the user requests outline generation for a project with an idea
- **THEN** the system sends a JSON-only prompt to the configured LLM
- **AND** validates the response against the story outline schema
- **AND** stores the normalized JSON as project outline

#### Scenario: Reject invalid outline
- **WHEN** the model returns invalid JSON after repair
- **THEN** the system keeps the previous outline unchanged
- **AND** records the raw response and validation error in generation logs

### Requirement: Chapter plan JSON contract

The system SHALL generate and store chapter or episode plans using a strict JSON contract with chapter_count and chapters.

#### Scenario: Generate chapter plan from outline
- **WHEN** a project has a valid outline
- **THEN** the user can generate a chapter plan for a requested count
- **AND** each chapter includes number, title, goal, conflict, key events, character focus, ending hook and status

#### Scenario: Regenerate without overwriting locked content
- **WHEN** a chapter plan or chapter entry is locked
- **THEN** regeneration must preserve locked entries
- **AND** only update unlocked entries

### Requirement: Stage-based generation

The system SHALL generate downstream content using saved upstream stages as context.

#### Scenario: Generate chapter detail
- **WHEN** the user generates detail for chapter 3
- **THEN** the system uses the saved outline and chapter 3 plan
- **AND** stores the output as a versioned project content item

#### Scenario: Generate single-chapter outline
- **WHEN** the user generates a detailed outline for a selected chapter
- **THEN** the system uses the saved story outline, full chapter plan, selected chapter plan and previous chapter context
- **AND** stores scenes, key dialogues, foreshadowing, ending hook and continuity notes as `chapter_outline`
- **AND** each scene MAY include an image prompt for downstream visual planning

#### Scenario: Generate chapter prose
- **WHEN** the user generates prose for a selected chapter
- **THEN** the system uses the latest `chapter_outline` for that chapter and previous context
- **AND** stores the complete prose body as `novel_body`
- **AND** preserves structured metadata such as title, chapter number, word count and continuity notes

#### Scenario: Convert storyboard into comic pages
- **WHEN** the user generates comic pages for a selected chapter
- **THEN** the system uses the latest `storyboard`, visual style and image style prompt
- **AND** stores versioned `comic_pages` where each page contains panel-marked script text and an image prompt
- **AND** the comic pages reference the storyboard content as their source content

#### Scenario: Generate short drama script
- **WHEN** the user generates a short drama script from a chapter detail
- **THEN** the system outputs structured scenes with action, dialogue, camera hints, emotion and image prompts

#### Scenario: Generate storyboard draft
- **WHEN** the user generates a storyboard from a script
- **THEN** each storyboard panel references source scene information
- **AND** includes a prompt suitable for AI image generation

### Requirement: Novel adaptation

The system SHALL adapt downloaded novel chapters into project material.

#### Scenario: Extract project seed from novel chapters
- **WHEN** the user creates a project from selected novel chapters
- **THEN** the system summarizes plot, characters, conflict, world rules and visual style suggestions
- **AND** uses that summary to generate or prefill the story outline

#### Scenario: Convert novel chapter to short drama episode
- **WHEN** the user selects a novel chapter and requests script conversion
- **THEN** the system generates a short drama script draft based on the chapter content
- **AND** links the script to the source novel chapter

### Requirement: Generation logs

The system SHALL record generation requests and responses for each project stage.

#### Scenario: Inspect generation log
- **WHEN** a stage is generated
- **THEN** the system records provider, model, prompt, request JSON, raw response, normalized output, token usage if available and validation errors

#### Scenario: View project generation logs
- **WHEN** the user opens a creative project workspace
- **THEN** the system provides a project log view listing recent generation attempts
- **AND** each log can reveal the prompt, request JSON, selected prompt template, raw response, normalized JSON and validation error

### Requirement: Stage prompt templates

The system SHALL allow creative project generation prompts to be managed as typed templates instead of only hardcoded backend strings.

#### Scenario: Select prompt template for stage generation
- **WHEN** the user generates outline, chapter plan, chapter outline, chapter prose, comic pages, script or storyboard content
- **THEN** the request MAY include a creative-project prompt template id
- **AND** the backend validates that the template scope is `creative_project` and the template stage matches the requested stage
- **AND** the backend renders the template with the stage context before calling the LLM
- **AND** the backend uses the template system prompt when configured, otherwise it uses the built-in default system prompt

#### Scenario: Fallback when no template is configured
- **WHEN** no active prompt template exists for the requested stage
- **THEN** the system uses the built-in default user prompt and system prompt
- **AND** generation remains available

#### Scenario: Record prompt template usage
- **WHEN** a generation uses a prompt template
- **THEN** the generation log request JSON includes the template id, name, scope, stage and actual system/user messages

### Requirement: Project export

The system SHALL export project outputs without triggering regeneration.

#### Scenario: Export Markdown package
- **WHEN** the user exports a project as Markdown
- **THEN** the system uses saved outline, chapter plan, scripts and storyboard text
- **AND** does not call any AI provider

#### Scenario: Export project archive
- **WHEN** the user exports a project ZIP
- **THEN** the archive includes structured JSON, Markdown, linked asset manifest and local file references where available
