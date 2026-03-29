# Output Language

This project can localize operator-facing output into English or Korean.

## Settings

Add these environment variables to `.env`:

```powershell
FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE=en
FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE=
FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE=
```

Rules:

- `FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE`
  - global fallback language
  - supported values: `en`, `ko`
- `FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE`
  - optional override for generated Markdown / README-style outputs
  - currently affects generated brain vault notes and maps
- `FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE`
  - optional override for CLI help, command messages, pipeline/autoresearch status text, and Telegram progress/report text

If the override values are blank, the system falls back to `FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE`.

## Recommended examples

English everywhere:

```powershell
FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE=en
```

Korean everywhere:

```powershell
FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE=ko
```

English logs with Korean Markdown notes:

```powershell
FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE=en
FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE=ko
FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE=en
```

## Current scope

Localized now:

- CLI help and runtime error/status messages
- supervisor command responses
- Telegram progress/report text
- analyzer and falsifier summaries/messages
- generated brain vault Markdown notes and maps

Not localized intentionally:

- SQLite schema
- JSON response keys
- state enum values
- dashboard API field names
