## ADDED Requirements

### Requirement: Durable Agent Runs

The system SHALL store each agent execution as a durable run with ordered steps, status, selected profile, selected model, context, tool calls, observations, final answer, timestamps, and errors.

#### Scenario: Create run for agent request

- **WHEN** the user sends an agent request
- **THEN** the system creates an agent run
- **AND** the run stores the objective, selected profile, selected model, session id, and initial context

#### Scenario: Record tool execution

- **WHEN** an agent request triggers a tool call
- **THEN** the system records tool name, arguments, summarized result, raw result, linked objects, success state, and duration as run steps

#### Scenario: Resume run

- **WHEN** a run is paused, cancelled, or failed
- **THEN** the user can inspect existing steps
- **AND** continue or retry from a safe step without losing previous observations

### Requirement: Agent Runtime State Machine

The system SHALL process agent runs through a bounded state machine instead of a single opaque chat call.

#### Scenario: Execute state machine

- **WHEN** a run starts
- **THEN** the system processes states for intake, context packing, planning, tool selection, execution, observation, decision, and final response
- **AND** every state transition is recorded

#### Scenario: Stop at max steps

- **WHEN** an agent reaches its configured maximum step count
- **THEN** the system stops further automatic execution
- **AND** returns a summary explaining what was completed and what remains

### Requirement: Compatible Tool Loop

The system SHALL support text-JSON tool call fallback without requiring native OpenAI function calling support from every LLM backend.

#### Scenario: Model returns JSON tool call

- **WHEN** the model returns `{"tool_calls":[...]}`
- **THEN** the backend executes authorized tools
- **AND** feeds the result back as normal observation context unless the backend produced native assistant `tool_calls`

#### Scenario: Backend does not support native tool messages

- **WHEN** the backend only supports plain chat messages
- **THEN** the system SHALL NOT send bare `role=tool` messages
- **AND** tool results SHALL be converted to readable observation messages

### Requirement: Native Tool Calling

The system SHALL support OpenAI-compatible native tool calling for LLM backends that expose assistant `tool_calls`.

#### Scenario: Backend supports native tool calling

- **WHEN** a backend returns assistant `tool_calls`
- **THEN** the system appends the assistant tool call message and matching tool result messages according to the OpenAI protocol
- **AND** preserves tool call ids for each result

### Requirement: Tool Authorization And Risk Control

The system SHALL enforce per-profile tool authorization and risk-aware confirmation.

#### Scenario: Unauthorized tool requested

- **WHEN** a model asks to call a tool outside the selected profile's allowlist
- **THEN** the system blocks the call
- **AND** records a failed step with a clear unauthorized message

#### Scenario: High-risk tool requested

- **WHEN** a tool is classified as write, delete, external, or costly
- **THEN** the system creates a pending confirmation step before execution

### Requirement: Visible Memory And Context

The agent workbench SHALL show which memory, project context, default context, model, and authorized tools are active for the current run.

#### Scenario: User inspects context

- **WHEN** the user opens an agent run
- **THEN** the page shows selected profile, model, max steps, authorized tool count, project context, injected memories, and default context

#### Scenario: Save useful memory

- **WHEN** an agent identifies reusable user preferences or project rules
- **THEN** the system proposes memory entries
- **AND** stores them only after user confirmation or explicit user instruction

### Requirement: Creative Project Context Pack

The system SHALL provide a compact project context pack for creative-project-related runs.

#### Scenario: Creative project selected

- **WHEN** a run is associated with a creative project
- **THEN** the context pack includes project bible, chapter status, character summaries, reference assets, recent tasks, and known gaps

### Requirement: Multi-Agent Delegation

The system SHALL allow an orchestrator profile to delegate subtasks to specialized agent profiles while preserving a traceable delegation chain.

#### Scenario: Creative project run delegates work

- **WHEN** the orchestrator receives a request to continue a creative project
- **THEN** it can delegate writing, character design, storyboard, asset lookup, and review tasks to specialized profiles
- **AND** each subtask result is recorded in the parent run

#### Scenario: Show delegation chain

- **WHEN** a run contains delegated subtasks
- **THEN** the workbench shows parent run, child runs, responsible profiles, statuses, and outputs

### Requirement: Agent Workbench UI

The `/agent` page SHALL function as an operational workbench, not just a chat window.

#### Scenario: Inspect run timeline

- **WHEN** a run has steps
- **THEN** the page displays a timeline with plan, tool calls, observations, final answer, failed steps, and retry actions

#### Scenario: Inspect tool result

- **WHEN** a tool returns structured data
- **THEN** the page shows a human-readable summary by default
- **AND** offers collapsible raw JSON

### Requirement: Creative Workflow Entry Points

Creative project pages SHALL be able to start agent runs for common project-closing workflows.

#### Scenario: Start one-click project continuation

- **WHEN** the user selects a creative project and chooses a continuation goal
- **THEN** the system creates an orchestrator run with project context
- **AND** the run can coordinate writing, storyboard, reference matching, prompt generation, and review steps

### Requirement: Prompt Template Tool Coverage

The Agent Center SHALL expose platform and creative-project prompt templates as auditable tools.

#### Scenario: Inspect and preview prompt templates

- **WHEN** an agent needs to understand how a creative stage is prompted
- **THEN** it can list templates, read a selected template, and preview rendering with sample variables without calling an LLM
- **AND** the preview reports detected, used, and missing variables

#### Scenario: Update prompt template with confirmation

- **WHEN** an agent proposes a prompt template update
- **THEN** the update tool is classified as `write`
- **AND** the run requires user confirmation before persisting changes

### Requirement: AI Connector Tool Coverage

The Agent Center SHALL expose non-sensitive AI connector configuration as read-only tools.

#### Scenario: Select configured model

- **WHEN** an agent needs to choose a text, image, video, speech, or embedding model
- **THEN** it can list active connectors and inspect connector details without exposing API keys
- **AND** the details include provider type, default model, available models, API format, endpoint, supported sizes, reference-image support, and parsing/default parameters

#### Scenario: Avoid paid test calls

- **WHEN** an agent inspects AI connector configuration
- **THEN** the tool does not run connector tests or call model generation endpoints

### Requirement: Task Center Tool Coverage

The Agent Center SHALL expose the unified task center as agent-callable tools.

#### Scenario: Inspect asynchronous work

- **WHEN** an agent needs to check progress or diagnose a failed operation
- **THEN** it can list tasks by status/type/keyword and read a single task detail
- **AND** task detail includes payload, result, diagnostics, events, and error fields when available

#### Scenario: Control task records with risk confirmation

- **WHEN** an agent proposes cancelling a task
- **THEN** the cancel tool is classified as `write`
- **AND** the run requires user confirmation before executing it
- **WHEN** an agent proposes deleting a task record
- **THEN** the delete tool is classified as `delete`
- **AND** deletion removes only the task center record, not generated assets or files

### Requirement: Novel Source Tool Coverage

The Agent Center SHALL expose novel source and bookshelf workflows as agent-callable tools.

#### Scenario: Inspect local novel material

- **WHEN** an agent needs upstream story material
- **THEN** it can list local novel source configuration and local Asset Hub bookshelf/download records without external network access
- **AND** bookshelf results include asset id, title, author, source, chapter counts, downloaded chapter indices, and content path when available

#### Scenario: Search and preview external novel sources

- **WHEN** an agent needs to search book sources, read a catalog, or preview chapter text
- **THEN** those tools are classified as `external`
- **AND** the run requires user confirmation before visiting external book-source sites
- **AND** chapter preview returns truncated content with the full content length, not an unbounded full chapter by default

### Requirement: Download Source Tool Coverage

The Agent Center SHALL expose download parsing and download task creation as agent-callable tools.

#### Scenario: Parse external media link before downloading

- **WHEN** an agent needs to inspect a media/article URL
- **THEN** it can call a `download` category parse tool that returns metadata, quality summaries, platform, and parsed asset id when available
- **AND** the parse tool is classified as `external` and requires confirmation before visiting the external URL
- **AND** the tool does not return long signed media URLs by default

#### Scenario: Create and monitor a download task

- **WHEN** the user confirms a download
- **THEN** the agent can create a background download task with URL, quality, title, page URL, audio-only flag, and parsed asset id
- **AND** the task creation tool is classified as `external` because it visits external sites and writes local files/assets
- **AND** the agent can poll the task status or use task-center tools to inspect progress and errors

### Requirement: WeChat MP Tool Coverage

The Agent Center SHALL expose WeChat MP connection and article acquisition workflows as agent-callable tools.

#### Scenario: Inspect configured WeChat MP connections

- **WHEN** an agent needs to use WeChat MP acquisition
- **THEN** it can list configured WeChat MP connections without exposing cookies, tokens, or raw credentials
- **AND** the connection listing tool is classified as `read`

#### Scenario: Search accounts and download an article

- **WHEN** an agent needs to collect WeChat MP article material
- **THEN** it can search accounts, list articles by fake_id, and download a selected article after user confirmation
- **AND** account search, article listing, and article download tools are classified as `external`
- **AND** downloaded files can be used as upstream material for Asset Hub and creative projects

### Requirement: TTS Tool Coverage

The Agent Center SHALL expose text-to-speech workflows as agent-callable tools.

#### Scenario: Preview and generate narration audio

- **WHEN** an agent needs to turn narration, dialogue, or script text into audio
- **THEN** it can preview the normalized TTS request without writing a file
- **AND** confirmed audio generation is classified as `costly`
- **AND** generation returns a local file path and audio URL when successful

### Requirement: Ebook Tool Coverage

The Agent Center SHALL expose EPUB generation workflows as agent-callable tools.

#### Scenario: Generate EPUB from local article/chapter folder

- **WHEN** an agent has a local folder of Markdown or HTML files
- **THEN** it can create an EPUB generation task with title, author, cover path, and output directory
- **AND** EPUB generation is classified as `write`
- **AND** the agent can list and inspect EPUB task status and output paths

### Requirement: Semantic Asset Search Tool Coverage

The Agent Center SHALL expose semantic Asset Hub search as agent-callable tools.

#### Scenario: Search assets by meaning and similarity

- **WHEN** an agent needs references that are semantically or visually similar to a creative need
- **THEN** it can run hybrid semantic search with query text, ranking weights, tag filters, type filters, and similarity threshold
- **AND** query embedding search is classified as `costly`
- **AND** it can find similar assets from an existing asset id when stored embeddings are available
- **AND** embedding inspection omits raw vector values from tool output

### Requirement: Asset Lineage Tool Coverage

The Agent Center SHALL expose Asset Hub lineage inspection and relation creation as agent-callable tools.

#### Scenario: Inspect asset provenance and derivatives

- **WHEN** an agent needs to explain where an asset came from or what it produced
- **THEN** it can read full lineage graph, upstream lineage, downstream lineage, lineage stats, and common ancestor information
- **AND** all inspection tools are classified as `read`

#### Scenario: Create lineage relation with confirmation

- **WHEN** an agent proposes linking source and target assets
- **THEN** it can create a relation with relation type and optional context
- **AND** relation creation is classified as `write`
- **AND** the run requires user confirmation before persisting the relation

### Requirement: Local Reader Tool Coverage

The Agent Center SHALL expose local readable document workflows as agent-callable tools.

#### Scenario: Browse and preview local downloaded documents

- **WHEN** an agent needs to inspect downloaded articles, chapters, or local document collections
- **THEN** it can browse readable files under the reader root and preview one or many documents
- **AND** document previews return chapter metadata, content lengths, and truncated content previews rather than unbounded full content

#### Scenario: Delete local reader document with confirmation

- **WHEN** an agent proposes deleting a local document or folder
- **THEN** the delete tool is classified as `delete`
- **AND** the run requires user confirmation before deletion

### Requirement: Export And Quality Tool Coverage

The Agent Center SHALL expose dataset export, quality scoring, duplicate detection, and duplicate merge workflows as agent-callable tools.

#### Scenario: Inspect and export dataset

- **WHEN** an agent needs to prepare material for backup, training, or handoff
- **THEN** it can read dataset statistics and create a ZIP dataset export with optional metadata and lineage
- **AND** dataset export is classified as `write`

#### Scenario: Quality and duplicate curation

- **WHEN** an agent needs to curate a material library
- **THEN** it can calculate single or batch asset quality scores and find duplicate assets
- **AND** these compute-heavy tools are classified as `costly`
- **AND** duplicate merge is classified as `write` and requires confirmation before persisting changes

### Requirement: Platform Source Tool Coverage

The Agent Center SHALL expose external platform source acquisition workflows as agent-callable tools.

#### Scenario: Inspect supported platforms and configured connections

- **WHEN** an agent needs to collect material from external platforms
- **THEN** it can list supported platforms, search modes, and configured platform connections
- **AND** connection listings do not expose cookies, tokens, or raw credentials
- **AND** these inspection tools are classified as `read`

#### Scenario: Search external platforms and fetch details

- **WHEN** an agent needs to find external source material
- **THEN** it can search platform sources, run enhanced search, fetch note/content details, and fetch no-watermark resources
- **AND** these tools are classified as `external`
- **AND** the run requires user confirmation before visiting external platform endpoints

#### Scenario: Import collected platform results

- **WHEN** the user confirms collected results should become local material
- **THEN** the agent can import crawler result objects into Asset Hub
- **AND** import is classified as `write`
