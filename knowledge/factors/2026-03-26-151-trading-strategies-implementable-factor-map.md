# 151 trading strategies implementable factor map

- Source:
  - local PDF: `C:\Users\hanji\Desktop\Finance\ssrn-3247865.pdf`
  - SSRN abstract: https://ssrn.com/abstract=3247865
- Review date: 2026-03-26

## Why this source is useful here

- This book is a cross-asset idea catalog, not a drop-in implementation guide for the current engine.
- The useful part for this project is the taxonomy:
  - what kinds of edges exist
  - what data they need
  - which ones can be approximated with OHLCV-only signals

## Factor and signal families worth extracting now

- momentum
  - price momentum
  - residual momentum
  - dual momentum
  - momentum and carry combo as a future extension
- volatility
  - low-volatility anomaly
  - volatility targeting
  - volatility carry as a future derivatives-only family
- mean reversion
  - ETF mean reversion
  - channel-based reversal or breakout logic
  - Internal Bar Strength style short-horizon reversal as a future candidate
- trend persistence
  - channel
  - multi-asset trend following
  - trend-fit and R-squared style persistence checks
- rotation and ranking
  - sector momentum rotation
  - alpha rotation
  - grouped ranking by sector or industry as a future multi-asset path

## What fits the current engine

- ideas that can be approximated from OHLCV or light metadata:
  - price momentum
  - low-volatility filters
  - channel breakout
  - simple mean reversion
  - trend persistence
  - volatility gating
- ideas that fit as planner vocabulary before they fit as strategy primitives:
  - residual momentum
  - trend-fit
  - R-squared
  - alpha combos
  - rotation

## What does not fit the current engine yet

- options structures
- fixed-income butterflies
- variance swaps
- structured-credit carry
- tax arbitrage
- sentiment analysis
- ANN classifiers
- macro-announcement trading
- carry trades that need rate differentials or futures term structure

## Project adaptation rules

- treat this book as a source of:
  - factor family names
  - idea priors
  - scope boundaries
- do not treat each strategy in the book as a candidate for direct mutation
- prefer extracting compact planner-facing concepts such as:
  - momentum
  - low_volatility
  - mean_reversion
  - channel
  - trend_fit
  - volatility_targeting
  - sector_rotation
  - residual_momentum

## Practical planner vocabulary from this source

- momentum
- residual_momentum
- low_volatility
- mean_reversion
- channel
- sector_rotation
- dual_momentum
- trend_following
- trend_fit
- r_squared
- volatility_targeting
- alpha_combo

## Use in this project

- use these words for:
  - retrieval
  - lesson summaries
  - candidate family framing
- do not widen the runtime to support asset-class-specific execution just because the source covers it
