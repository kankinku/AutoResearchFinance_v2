# Verification evidence

The release gate is reproducible from the repository root:

```powershell
python -m pytest -q
ruff check .
python -m mypy .
```

Focused contracts cover source normalization, IR signal execution, Docker isolation,
data-zone and Parquet integrity, funnel decisions, CSCV/CPCV split generation, abstract
knowledge extraction, paper approval, live denial, state atomicity, and CLI behavior.

The verification result must report external configuration separately: no KIS credentials,
live data vendor, LLM credential, or pinned production image is fabricated by tests.
