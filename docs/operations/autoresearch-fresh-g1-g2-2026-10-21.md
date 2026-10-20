# Quant AutoResearch — New independent G1–G2 verified local research (2026-10-21 KST)

**Scope/status:** User explicitly authorized starting from scratch. New **separate** session, not G351, not a recovered G350 and not a successor of the former official record. Planned fresh target **G500**, completed **2/500**. **G1–G2 session COMPLETED 2/2**, with two actual GPT-authored typed plans, two actual observation-bound GPT diagnoses and two canonical costed S7 controlled experiments. This was directly called from Moon Python, **not through working authenticated Quant MCP**, whose existing URL/OAuth registration was not touched. `model_autonomy_verified=false`; no unattended 100-gen worker.

## Pinned inputs and isolation

- Git branch/worktree: `feat/quant-fresh-research-20261021`, worktree `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`; code baseline from original feature branch `cc6630ff130521da91d849fbc51d3d96b7a11c95`.
- Independent new session ID: `3eb928535edd4a3c90eea0e937e67973`.
- Local persisted state: `state/moon-http/fresh-20261021/research/academic-gpt-checkpoints/`, not in Git. Operator-readable session identifier `state/moon-http/fresh-20261021/session-id.txt`. **Do not reset or overwrite this directory.**
- Market source: `https://yennj12.js.org/finance_data/data/qqq/qqq.csv` (website says Yahoo Finance-derived raw QQQ OHLCV; **not independent PIT/vendor certification**), original source SHA256 `ff800ea26038e58f0cf6b1465261f13628b66cb410a0438f179fed90ce3b01e8`, retrieved in current session.
- Frozen data `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`: **1,508** daily OHLCV bars, QQQ, 2020-01-02–2025-12-31; Parquet bytes SHA256 `94e1f5f118e6dc14d25dc95b654fcfd485f07bce251fb1c8a16d1843df638037`; immutable engine dataset hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. Read-back matching hash PASS. Original CSV, Parquet and manifest are ignored by Git.
- DEVELOPMENT, fixed next-open long/flat, 100% allocation, canonical costs. Same-data QQQ single buy-and-hold +187.7724% price-only (no dividends), **not independent benchmark verification**. Sealed OOS not used; brokers/orders disabled.

## Real research observations (each generation costed independently on the same full DEVELOPMENT sample)

| Stage | Total return | Full-period MDD | Closed trades | Exposure | Observation and action |
| --- | ---: | ---: | ---: | ---: | --- |
| Fresh counted G1 | +55.6281% | 24.8197% | 118 | 57.9576% | GPT drafted two-regime weighted vote algorithm. Largest losing trade entered with dual-SMA=0 despite positive EMA/breakout; proposed a single hard dual-SMA entry rule as **hypothesis**, not assumed fact. |
| G1 S7 counterfactual child (not extra generation) | +57.1824% | 18.2003% | 81 | 54.6419% | Entry gate reduced MDD by **6.6194 pp**, return rose **1.5543 pp**; replayed child hash `e589c8386fea1bb1c9d0d4eb2dbeb48b4a6ab4796abecb64921a1b6e4510cf23`. Selected as new G2 development parent. |
| Fresh counted G2 (inherited G1 S7 child) | **+68.2234%** | **20.1421%** | **71** | **55.6366%** | GPT replaced exit from `plan_entry<=0.5` with `plan_vote_score<=0.25` to test whipsaw/over-early exit. True change in fill sequence, measured return +11.0410 pp vs selected parent; MDD worse by 1.9418 pp. |
| G2 S7 counterfactual child (not extra generation) | +51.9739% | 27.5119% | Not independently totaled in summary | Not independently totaled | GPT hypothesized earlier `ema_direction_20<=0.5` exit would reduce reversal MDD; actual measured MDD **increased 7.3698 pp** and return decreased **16.2495 pp** from G2. Hypothesis **refuted on the reused development sample**. Do not promote it. |

Quantitative comparison is the **cross-sectional value of each complete single-period strategy**; numbers are not compounded generation-to-generation and do not prove real profitability. The original older G350 used a different vendor dataset; equivalence is unverified.

## Integrity and checkpoint evidence

- G1 strategy SHA `013bf42643add3b261134db4aa15c67b9d00c6583852ed299cf2559ade575451`; G1 immutable Evidence SHA `20aab6faf056178622e908c588d4feea0fe9d3e512e57062555d1d5f87a58db3`.
- G2 strategy SHA `17a13db4253f18f5b19478542272db544ed403d4748e388a29d1b9a85dd082a6`; G2 Evidence SHA `e58a76c157da26f48ed3b4bf1f02a74a82365a516b172935b2a14ed63f6f4d6f`.
- Verified `G2.previous_evidence_hash == G1.evidence_hash`; verified `COMPLETED 2/2`, two distinct strategies and verified S7 reports (1 hypothesis per generation), immutable Evidence-linked S7 summaries `all_proposed_hypotheses_measured=true`; final report `total_observed_fills=378`, `model_autonomy_verified=false`, `independent_profitability_verified=false`.
- Engine's selected parent decision `COUNTED_S7_CHILD` on G1 source. At G2 `require_execution_change=true` passed `VERIFIED_DIFFERENT_COSTED_FILLS`, 162 original parent fills vs 142 candidate fills before G2 commit.
- `orders_enabled=false`, `independent_oos_approved=false`, `real_model_connection_verified=false`; no KIS order/client use, no OAuth URL/DB/key modifications.
- Host ignored audit summary `state/moon-http/fresh-20261021/read-only-audit-summary.json`; research SQLite is authoritative. Checkpoint now **COMPLETED 2/2**. Continuing G3 requires explicit verified session extension or a new separately identified research cycle. Do not accidentally start G3 in an unrelated batch.

## Limitations / blockers / required next sequence

1. The authenticated Quant MCP remains HTTP 404 / plugin `The tool failed internally`; Moon **local** direct invocation of existing canonical service is working, but this does not verify `ChatGPT↔MCP` connectivity, self-scheduling or automatic LLM planning without user turns.
2. Data is latest Yahoo-derived price history without independent PIT, split/dividend vintage or sealed OOS. Existing cost model is a development model, not independently calibrated live market execution.
3. The S7 experiments reused exactly the same period; observed benefits/harms can reflect sample-specific fitting rather than causality. Actual GPT-written plans were submitted in this conversation, but server field `real_model_connection_verified=false` correctly remains false.
4. To reach fresh G500, verify the authenticated transport/operational service in **the new isolated runtime** without changing old URL credentials; checkpoint extension and sequential GPT-authored new plan → diagnosis → S7; plan and report every bounded cohort, random controls and diverse markets later under original V05→T4→V01–V04→V06→V07 order. Do **not** label the current 2/2 session a completed 100/500 autonomous campaign.
