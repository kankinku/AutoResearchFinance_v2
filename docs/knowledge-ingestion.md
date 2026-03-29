# Knowledge ingestion rules

## What the planner reads now

- The planner reads text files under:
  - `knowledge/indicators`
  - `knowledge/factors`
  - `knowledge/regimes`
  - `knowledge/failures`
  - `knowledge/markets`
- It currently accepts:
  - `.md`
  - `.txt`
  - `.json`
  - `.yaml`
  - `.yml`
- It does not read raw `.pdf` files directly.

## What to do with PDFs

- Put raw source PDFs in:
  - `knowledge/external/raw/`
- Treat that location as a provenance archive, not as planner-readable knowledge.
- For the planner to actually use the content, extract and distill the PDF into Markdown notes under the planner-visible folders:
  - `knowledge/factors` for factor or strategy-family ideas
  - `knowledge/regimes` for risk-state or regime-gating ideas
  - `knowledge/markets` for asset-class, universe, and implementation-scope notes
  - `knowledge/indicators` only when the source contains indicator-level signal ideas that fit the current engine

## Rule for this project

- Do not drop large raw PDFs into `knowledge/factors`, `knowledge/regimes`, `knowledge/markets`, or `knowledge/indicators`.
- First keep the raw source in `knowledge/external/raw/`.
- Then create small Markdown notes that:
  - summarize only what fits the current strategy engine
  - call out what requires future data or multi-asset support
  - avoid turning a broad source into an immediate implementation commitment

## Current engine constraints to respect

- single mutable strategy file
- OHLCV-first data
- small indicator sets
- no direct options, fixed-income, structured-credit, or tax-arbitrage execution path
- no news, sentiment, or macro-calendar dependencies in the default path

## Recommended workflow

1. archive the raw PDF in `knowledge/external/raw/`
2. extract text outside the planner path
3. write 1-3 distilled Markdown notes in planner-visible knowledge folders
4. tag the notes with the exact ideas that should affect retrieval
5. keep non-implementable ideas as future references, not immediate mutation instructions
