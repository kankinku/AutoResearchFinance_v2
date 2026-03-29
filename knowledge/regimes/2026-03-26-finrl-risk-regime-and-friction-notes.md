# FinRL risk regime and friction notes

- Source repository: [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL)
- Review date: 2026-03-26

## What the repository is actually useful for

- FinRL is useful here as a reference for:
  - risk-state construction
  - market-friction handling
  - turbulence-style regime gates
- The reusable value is in the state and execution logic.
- The reusable value is not the RL training loop.

## Risk and regime ideas worth keeping

- Turbulence is treated as a portfolio-level risk signal.
- A simple but useful pattern appears repeatedly:
  - when risk exceeds threshold
  - block new buys
  - optionally force liquidation or defensive behavior
- VIX appears as an optional fast-moving risk feature.
- Rolling covariance is used as a research feature, especially for portfolio context.

## Execution and friction ideas worth keeping

- Apply explicit buy and sell costs.
- Bound buys by available cash.
- Bound sells by current holdings.
- Keep integer-share or inventory-style constraints in the execution model.
- Consider cash-pressure or minimum-cash rules as a survivability constraint.

## What fits this project now

- Treat turbulence as a regime or kill-switch reference.
- Treat covariance as a future diagnostic feature for:
  - diversification pressure
  - cluster exposure checks
  - portfolio stress awareness
- Treat explicit fee, cash, and inventory constraints as backtest realism inputs.
- These ideas fit the current project best in:
  - evaluator
  - falsifier
  - future risk clauses

## What does not fit this project yet

- Do not import RL environments or Gym abstractions.
- Do not copy tutorial assumptions blindly.
  - Some older tutorial paths are less realistic than newer environment code.
- Do not use FinRL portfolio environments as drop-in allocators without auditing which costs and thresholds are actually enforced.

## Project adaptation rules

- Keep the current backtest-first architecture.
- Reuse only the deterministic pieces:
  - turbulence threshold logic
  - fee and friction handling
  - cash and holdings constraints
  - covariance-derived risk context
- Keep regime logic explicit and inspectable in notes, reports, and future compiler metadata.

## Source-backed caveats

- Repository code and tutorial material are not perfectly aligned.
- Some environment variants are much more realistic than others.
- Covariance construction is shown in tutorial flow but is not a universal preprocessing primitive across the repo.

## Sources

- Repository:
  - https://github.com/AI4Finance-Foundation/FinRL
- Feature engineering:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/preprocessor/preprocessors.py
- Stock trading environment:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/env_stock_trading/env_stocktrading.py
- Numpy stock trading environment:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/env_stock_trading/env_stocktrading_np.py
- Cash penalty environment:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/env_stock_trading/env_stocktrading_cashpenalty.py
- Portfolio allocation tutorial:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/docs/source/tutorial/Introduction/PortfolioAllocation.rst
- Portfolio optimization environment:
  - https://github.com/AI4Finance-Foundation/FinRL/blob/master/finrl/meta/env_portfolio_optimization/env_portfolio_optimization.py
