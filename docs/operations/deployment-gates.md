# Deployment gates

| Gate | Local implementation | External requirement |
|---|---|---|
| Research | PASS when tests and evaluator contracts pass | none |
| Paper | Exact Champion hash, validation flag, and unexpired approval | paper account/configuration |
| Live | `DENY` by default; research permissions reject credentials/orders | separate process, secret store, real KIS account, current paper evidence, explicit human approval, expiry, risk limits |
| Data | Versioned Parquet or provider contract with zone enforcement | real vendor, symbol universe, calendar, date ranges |
| Feature Registry | Optional registered features, as-of alignment, calculator and verification gates | production data mappings and source quality approval |
| Benchmark | QQQ total return and Nasdaq Composite comparison when supplied | benchmark series, dividend/distribution policy, aligned date range |
| Risk evaluation | Strategy risk appetite and daily-loss behavior recorded separately | user-defined strategy policy; immutable emergency cutoff remains outside strategy |
| Worker | Docker isolation command and image contract | built and pinned image digest, Docker Engine |
| LLM | Offline provider, local Codex Desktop MCP, or local `codex exec` adapter with schema validation | Codex Desktop/CLI login; no KIS credential is passed to the research bridge |

The external requirements are intentionally not marked PASS by local unit tests. No live
order method is exposed by the research KIS adapter, and this repository does not submit
orders.
