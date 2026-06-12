# Rule Assistant Plugin Design

## Goal

Rule Assistant is a reusable plugin layer for repairing extractor rules with an existing YLCraft LLM backend. The first plugin targets book sources, but the service is intentionally domain-neutral so crawler, download, or social-source rules can register their own plugins later.

## Layers

1. API: accepts a compact rule-debug context and optional `provider/model`.
2. Service: selects a plugin, calls the existing `AIService.chat`, parses strict JSON, and validates patches against the supplied HTML.
3. Plugin: understands one rule domain, builds the prompt, prepares local diagnostics, and validates domain-specific patch targets.

## Context Contract

The API sends:

- `domain`: plugin key, for example `book_source`.
- `rule_type`: `search`, `toc`, or `content` for the first book-source plugin.
- `rule_format`: `legado` or `ylcraft`.
- `current_rules`: the unsaved editor state, not only database state.
- `test_result`: the last debug response, including diagnostics, rule trace, parsed result, request preview, and truncated HTML.

Sensitive request data must be filtered before entering this context. Cookies should stay hidden or omitted.

## Patch Contract

The model returns JSON only:

```json
{
  "summary": "short explanation",
  "patches": [
      {
        "target": "rule_content",
        "format": "legado",
        "mode": "merge",
        "value": { "content": "main" },
        "reason": "why this patch should work",
        "confidence": 0.82,
      "risks": ["what may still fail"]
    }
  ],
  "test_plan": ["Run the same content test again"]
}
```

The frontend applies a patch to the current editor only. Saving remains an explicit user action after retesting.

`mode` defaults to `merge`. Object targets such as `rule_search`, `rule_toc`, and `rule_content` preserve existing fields and only overwrite keys present in `value`. `replace` is reserved for intentional full-object replacement.

YLCraft patches are deep-merged. A patch such as `search.items.fields.author` updates only that field and must not replace the whole `search` section.

## YLCraft Rule Direction

Legado compatibility remains the short-term import and fallback layer because many public book sources already use Legado syntax. YLCraft is the preferred editable format for new rules because it is structured JSON: selectors, field extraction, request metadata, and post-processing can be patched independently and validated before saving.

YLCraft supports field/content `transforms` for common cleanup that would otherwise require Legado `##` filters or `<js>` snippets:

```json
{
  "search": {
    "items": {
      "selector": ".book-item",
      "fields": {
        "author": {
          "selector": ".author",
          "type": "text",
          "transforms": [
            { "type": "replace", "old": "作者：", "new": "" },
            { "type": "trim" }
          ]
        },
        "url": {
          "selector": "a",
          "type": "attr",
          "attr": "href",
          "transforms": [
            { "type": "urljoin", "base": "https://www.example.com" }
          ]
        }
      }
    }
  },
  "content": {
    "selector": "#content",
    "transforms": [
      { "type": "regex_replace", "pattern": "本章完", "repl": "" },
      { "type": "trim" }
    ]
  }
}
```

Supported transform types:

- `trim`
- `replace` / `text_replace`
- `regex_replace` / `replace_regex`
- `regex_extract` / `extract_regex`
- `prefix`
- `suffix`
- `urljoin` / `absolute_url`
- `max_length` / `truncate`
- `slice`
- `js`

The converter preserves Legado `##pattern` as `regex_replace` and Legado `<js>...</js>` / `@js:` as `js` transforms on supported field and content paths. Exporting YLCraft back to Legado writes those supported transforms back as `##pattern` and `<js>...</js>`. Other YLCraft-native transforms remain YLCraft-native because Legado has no direct structured equivalent.

## Book Source Plugin v1

The book-source plugin prepares evidence before calling the model:

- Page meta: title, keywords, description.
- Rule trace: current selector hit counts and samples.
- Diagnostics: anti-bot, no-match, meta-description fallback, and HTTP warnings.
- Selector inventory: local BeautifulSoup probes for common content/list containers.
- Clean HTML excerpt: scripts/styles removed and capped.

This keeps the LLM task narrow: judge existing evidence and produce a small patch, instead of guessing from a full page dump.

## Extension Path

Future plugins only need to implement:

- `supports(context)`
- `analyze(context)`
- `build_messages(context, analysis)`
- `parse_response(response)`
- `validate_patches(context, result)`

The same API can then serve crawler rules, platform connector extraction rules, or download parser rules without a new model stack.
