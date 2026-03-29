# Factor catalog draft

- Review date: 2026-03-26
- Purpose:
  - keep a small factor vocabulary that the planner can retrieve without widening the system into a full factor engine

## Core factor families

- volatility and stress
  - atr
  - rolling_std
  - turbulence
  - vix
- trend and persistence
  - ema
  - sma
  - xaverage
  - macd
  - trend_slope
  - trend_fit
  - trend_residual
- correlation and cross-asset structure
  - rolling_corr
  - covariance
- return transforms
  - simple_return
  - log_return
- ranking and cross-sectional views
  - rolling_rank
  - rolling_quantile
  - quantile
  - autocorrelation

## Metadata-aware evaluation vocabulary

- metadata
- sector
- industry
- exchange
- country
- market_cap
- universe

## Practical guidance for this project

- use factor vocabulary as:
  - planner retrieval hints
  - review and lesson language
  - future factor catalog seed
- do not treat this file as a commitment to implement every factor now
- keep the current strategy engine focused on:
  - small indicator sets
  - readable mutations
  - falsifiable changes
- turbulence and covariance are first-class research words even before they become first-class strategy primitives
