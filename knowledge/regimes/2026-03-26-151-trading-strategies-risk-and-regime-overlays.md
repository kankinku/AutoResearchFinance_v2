# 151 trading strategies risk and regime overlays

- Source:
  - local PDF: `C:\Users\hanji\Desktop\Finance\ssrn-3247865.pdf`
  - SSRN abstract: https://ssrn.com/abstract=3247865
- Review date: 2026-03-26

## Risk and regime ideas worth keeping

- low-volatility is not only a stock-selection anomaly
  - it also acts as a regime filter
- volatility targeting is a first-class overlay
  - reduce risk in unstable conditions
  - avoid treating every signal equally across regimes
- channel and breakout logic are regime-sensitive
  - they behave differently in trend and chop
- sector rotation and dual momentum imply market-state dependence
  - leadership changes matter
- carry, basis, and roll-yield families are often hidden regime bets
  - they break when macro stress changes the state

## What fits this project now

- treat these ideas as:
  - regime vocabulary
  - risk overlay vocabulary
  - falsification prompts
- useful near-term adaptations:
  - volatility gating
  - trend versus chop split
  - exposure throttling
  - weaker confidence when a signal works only in one narrow slice

## Good planner words from this source

- low_volatility
- volatility_targeting
- trend_regime
- chop_regime
- breakout
- sector_leadership
- risk_on
- risk_off
- carry_regime
- basis_stress
- roll_yield

## What should remain future-only

- options-based volatility overlays
- yield-curve trades
- FX carry implementations
- commodity roll-yield implementations
- macro announcement filters

## Project adaptation rules

- use the source to improve regime language before adding new runtime dependencies
- prefer simple overlays first:
  - volatility filter
  - exposure cap
  - slower confirmation in unstable periods
- use this source in falsification language:
  - is the edge only a hidden regime bet
  - does the candidate collapse when turnover rises
  - does the candidate lose exposure in a stress regime

## Why this source matters

- it broadens the planner beyond pure indicator tweaking
- it reminds the system that many strategies are really:
  - state trades
  - carry trades
  - correlation trades
  - liquidity trades
- for the current repo, the right use is to make regime thinking sharper without pretending the engine already supports every asset class
