# External Repository Data Notes

Checked on 2026-03-25 (Asia/Seoul).

## 1. FinanceDatabase

Repository:
- https://github.com/JerBouma/FinanceDatabase

License:
- MIT

What it is good for:
- Large reference database of financial instruments and identifiers.
- Good for building or enriching a universe, symbol master, and metadata layer.

What data it appears to provide:
- 300,000+ symbols across:
  - Equities
  - ETFs
  - Funds
  - Indices
  - Currencies
  - Cryptocurrencies
  - Money Markets
- Example equity metadata fields shown in README:
  - symbol
  - name
  - currency
  - sector
  - industry_group
  - industry
  - exchange
  - market
  - country
  - state
  - city
  - zipcode
  - website
  - market_cap
  - isin
  - cusip
  - figi
  - composite_figi
  - shareclass_figi

What it is not good for:
- Not intended to provide up-to-date fundamentals.
- Not intended to provide historical price data / OHLCV.

Likely useful for our project:
- Symbol normalization
- Exchange / country / sector / industry filters
- Building candidate universes by asset class
- ETF/fund/index lookup tables
- Mapping between ticker and identifiers

Suggested integration role:
- Reference metadata only
- Do not treat it as a backtest price source

## 2. Qlib

Repository:
- https://github.com/microsoft/qlib

License:
- MIT

What it is good for:
- Quant research data pipeline and dataset format
- Historical market data preparation
- Derived factor / feature generation
- Instrument calendars and stock pools

Important current note:
- The README says the official dataset is temporarily disabled due to stricter data security policy.
- The README points to a community-contributed data source and still documents how to build datasets locally.

What data / dataset structure it appears to support:
- Basic qlib dataset contents:
  - Features / price-volume:
    - $close
    - $open
    - $low
    - $high
    - $volume
    - $change
    - $factor
  - Calendar files:
    - day.txt
    - 1min.txt
  - Instrument files:
    - all.txt
    - csi300.txt
    - csi500.txt
    - sp500.txt

Ready-made / collector-supported data patterns shown in docs:
- Daily data
- 1-minute data
- Regions:
  - cn
  - us
  - in
- Yahoo collector can download raw files such as:
  - high
  - low
  - open
  - close
  - adjclose
- The data collector area in the repo also includes directories for:
  - yahoo
  - fund
  - cn_index
  - us_index
  - br_index
  - crypto
  - pit
  - baostock_5min
  - crowd_source
  - contrib

Specific collector examples mentioned in the repo:
- yahoo:
  - US/CN stock data from Yahoo Finance
- fund:
  - fund data from Eastmoney
- cn_index:
  - CN indices such as CSI300 / CSI100
- us_index:
  - US indices such as SP500 / NASDAQ100 / DJIA / SP400

Dataset / feature layer capabilities relevant to research:
- Formulaic alpha building on top of qlib fields
- Example docs show MACD-style expressions built from qlib operators like:
  - EMA
  - Ref
  - arithmetic / rolling operations
- Dataset zoo in README mentions:
  - Alpha158
  - Alpha360
  - both for US and China markets

Important caveats:
- Yahoo Finance quality is explicitly warned to be imperfect.
- The ready-made qlib Yahoo data is not regularly updated.
- Incremental updates should be done from raw Yahoo collection, not from the offline reduced dataset.

Likely useful for our project:
- Historical OHLCV-style source candidate
- Alternate research data pipeline for equity markets
- Daily / 1-minute market datasets
- Calendar and instrument membership files
- Feature engineering ideas for indicator/factor expansion

Suggested integration role:
- Data ingestion and feature-research reference
- Not a drop-in replacement for our current backtest harness without an adapter
- Promising for future expansion if we want:
  - richer market universe files
  - standardized calendar/instrument datasets
  - factor-style features beyond simple indicators

## 3. Recommended use in this repository

FinanceDatabase:
- Use as a metadata knowledge source.
- Good first use cases:
  - sector / industry annotations
  - exchange / country filters
  - symbol master enrichment

Qlib:
- Use as a historical data and factor-engine reference.
- Good first use cases:
  - compare qlib field layout against our market pack format
  - evaluate whether qlib calendars / instruments can enrich our universe definition
  - mine feature ideas from Alpha158 / Alpha360 and formulaic alpha docs

## 4. Immediate conclusion

If the goal is "more instruments and better metadata":
- FinanceDatabase is the stronger reference.

If the goal is "more historical market data structure and factor ideas":
- Qlib is the stronger reference.

If the goal is "plug directly into current autoresearch":
- FinanceDatabase fits as reference metadata.
- Qlib fits as a future adapter / data pipeline project, not as an instant drop-in.

## Sources

- FinanceDatabase README and repository page:
  - https://github.com/JerBouma/FinanceDatabase
- Qlib README and repository page:
  - https://github.com/microsoft/qlib
- Qlib data collector README:
  - https://github.com/microsoft/qlib/tree/main/scripts/data_collector
- Qlib Yahoo collector page:
  - https://github.com/microsoft/qlib/tree/main/scripts/data_collector/yahoo
- Qlib formulaic alpha docs:
  - https://qlib.readthedocs.io/en/latest/advanced/alpha.html
