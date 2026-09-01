# Deployment gates

| Gate | Local implementation | External requirement |
|---|---|---|
| Research | PASS when tests and evaluator contracts pass | none |
| Paper | Exact Champion hash, validation flag, and unexpired approval | paper account/configuration |
| Live | `DENY` by default; research permissions reject credentials/orders | separate process, secret store, real KIS account, current paper evidence, explicit human approval, expiry, risk limits |
| Data | Versioned Parquet or provider contract with zone enforcement | real vendor, symbol universe, calendar, date ranges |
| Worker | Docker isolation command and image contract | built and pinned image digest, Docker Engine |
| LLM | Offline provider or configured HTTP JSON provider | endpoint and credential supplied through runtime environment |

The external requirements are intentionally not marked PASS by local unit tests. No live
order method is exposed by the research KIS adapter, and this repository does not submit
orders.
