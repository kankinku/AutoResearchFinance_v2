# 151 trading strategies asset-class scope map

- Source:
  - local PDF: `C:\Users\hanji\Desktop\Finance\ssrn-3247865.pdf`
  - SSRN abstract: https://ssrn.com/abstract=3247865
- Review date: 2026-03-26

## Asset classes covered by the source

- options
- stocks
- ETFs
- fixed income
- indexes
- volatility
- FX
- commodities
- futures
- structured assets
- convertibles
- tax arbitrage
- miscellaneous assets
- distressed assets
- real estate
- cash
- cryptocurrencies
- global macro
- infrastructure

## What is directly relevant to this repo now

- stocks
  - momentum
  - low-volatility
  - channel
  - simple mean reversion
- ETFs and indexes
  - sector rotation as a future universe feature
  - trend following
  - volatility targeting ideas
- cryptocurrencies
  - trend and regime ideas
  - sentiment and ANN only as future-data references

## What is only partially relevant

- FX
  - moving-average style signals can fit
  - carry needs rate data
  - triangular arbitrage does not fit
- commodities and futures
  - trend following can fit conceptually
  - roll yield and basis need term-structure data
- volatility
  - risk-premium and VIX basis are useful conceptually
  - actual trade construction needs derivative data

## What is out of scope for the current engine

- option spreads and volatility option structures
- fixed-income curve trades
- structured-credit carry
- convertible arbitrage
- tax arbitrage
- repo and cash-market lending structures
- distressed debt workflows
- real-estate allocation structures
- macro-announcement trading without event data

## Why this distinction matters

- the current engine is:
  - single-file
  - OHLCV-first
  - small-indicator
  - fixed market-pack oriented
- this book is much broader than the current engine
- using it well means:
  - importing the taxonomy
  - not importing unsupported execution assumptions

## Safe adaptation rules

- current planner-readable takeaways from this source should emphasize:
  - which asset classes map to OHLCV-only ideas
  - which ones require new data
  - which ones require a different execution engine
- prefer using this source to improve:
  - idea coverage
  - future factor catalog vocabulary
  - scope and non-goal clarity

## Immediate value for this project

- better naming for research briefs
- better boundaries for future market-pack expansion
- fewer false expectations when a strategy family looks attractive on paper but needs data the repo does not have
