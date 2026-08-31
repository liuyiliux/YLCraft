# Novel Source to World Project

## Why

YLCraft currently imports selected novel chapters mainly as a seed for a creative project. This is enough for a short adaptation, but it does not turn a complete novel into a durable, inspectable world project. Users need to extract and reuse characters, worldview, rules, economy, power systems, geography, factions, timeline and relationships, then decide whether to adapt the source, continue it, or write a fan work from it.

The system must support both local TXT files and novels collected through search and bookshelf workflows. It must also support completed books and ongoing serials without confusing unfinished source material with confirmed canon.

## What Changes

- Introduce a source-to-world-project workflow for TXT imports and bookshelf novels.
- Normalize a novel into ordered chapters, text chunks, source snapshots and provenance anchors.
- Build optional chapter/chunk vector indexes, while retaining lexical and structural retrieval for names, aliases and exact evidence.
- Extract reviewable world knowledge: characters, aliases, relationships, locations, geography, factions, worldview rules, economy/finance, power systems, items, timeline, glossary and unresolved questions.
- Use adaptive setting profiles so a city short drama can stay lightweight while science-fiction, fantasy, historical and animation/game projects can opt into species, ecology, history, religion, language, technology, magic, maps and geopolitical modules.
- Store extracted results as candidates first; only user-confirmed results become project facts, character cards, world assets or map documents.
- Add completed-source modes: adaptation, continuation/sequel and fan work.
- Add serial-source modes: incremental import, new-chapter delta extraction, affected-fact recheck and source checkpointing.
- Keep original source canon read-only and place continuation/fan-work content in a separate derivative branch.
- Give human users and Agents the same preview, confirmation, provenance and API contracts.

## Non-goals

- Do not claim legal permission to create or publish fan works; source rights and publication decisions remain the user's responsibility.
- Do not automatically accept model-extracted facts as canon.
- Do not use vector similarity as the only extraction method; exact names, aliases, chapter order and evidence anchors must remain available.
- Do not rewrite or mutate imported source chapters when creating adaptations, continuations or fan works.
- Do not require a map image generator for the first release; structured map data and reviewable visual drafts are separate stages.
- Do not replace the existing Creative Project, Character Library, Narrative Runtime or Asset Hub; this change coordinates them.

## User-visible outcome

```text
TXT upload / novel search / bookshelf
  -> source snapshot and chapterized text
  -> optional vector index
  -> extraction preview
  -> user/Agent review
  -> confirmed world project
  -> adaptation | continuation | fan work
  -> outline, chapters, maps, scripts and visual production
```

The result is a project that can answer “what is true in the source?”, “where is the evidence?”, “what is still uncertain?” and “which facts belong only to my derivative work?”.
