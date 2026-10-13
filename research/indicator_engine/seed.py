"""Manually curated DOI starting set; citation numbers deliberately unknown.

No PDF scraping, network calls, arbitrary package execution, or automatic
academic-to-runtime promotion. Each mapping is a research hypothesis.
"""

from __future__ import annotations

from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.models import CANONICAL_FORMULAS, IndicatorCandidate, Paper


def _paper(
    doi: str, title: str, authors: tuple[str, ...], year: int, journal: str, market: str, note: str
) -> Paper:
    return Paper(
        doi=doi,
        title=title,
        authors=authors,
        published_year=year,
        source_url="https://doi.org/" + doi,
        venue=journal,
        source_scope=market,
        replication_note=note,
    )


ACADEMIC_PAPERS: tuple[Paper, ...] = (
    _paper(
        "10.1111/j.1540-6261.1992.tb04681.x",
        "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns",
        ("William Brock", "Josef Lakonishok", "Blake LeBaron"),
        1992,
        "The Journal of Finance",
        "Dow Jones index, 1897-1986",
        "Original moving-average and trading-range experiments; no QQQ replication.",
    ),
    _paper(
        "10.1111/j.1540-6261.1993.tb04702.x",
        "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
        ("Narasimhan Jegadeesh", "Sheridan Titman"),
        1993,
        "The Journal of Finance",
        "cross-sectional US stocks",
        "Requires point-in-time survivor-free multi-asset universe; QQQ alone is ineligible.",
    ),
    _paper(
        "10.1016/j.jfineco.2011.11.003",
        "Time Series Momentum",
        ("Tobias J. Moskowitz", "Yao Hua Ooi", "Lasse Heje Pedersen"),
        2012,
        "Journal of Financial Economics",
        "futures across asset classes",
        "Single-asset QQQ signal is a transport hypothesis, not paper replication.",
    ),
    _paper(
        "10.1086/296072",
        "On the Estimation of Security Price Volatilities from Historical Data",
        ("Mark B. Garman", "Michael J. Klass"),
        1980,
        "The Journal of Business",
        "OHLC volatility estimator",
        "Range estimator of variance, not a standalone profitable trading rule.",
    ),
    _paper(
        "10.1086/296071",
        "The Extreme Value Method for Estimating the Variance of the Rate of Return",
        ("Michael Parkinson",),
        1980,
        "The Journal of Business",
        "High-low range variance estimator",
        "Conditional estimator assumptions; QQQ use requires independent research validation.",
    ),
    _paper(
        "10.1111/jofi.12513",
        "Volatility-Managed Portfolios",
        ("Alan Moreira", "Tyler Muir"),
        2017,
        "The Journal of Finance",
        "US risk factors and variance-scaled portfolios",
        "Unleveraged daily risk sizing is an adaptation, not paper replication.",
    ),
)


def _signal(
    signal_id: str,
    doi: str,
    calculator: str,
    family: str,
    role: str,
    fields: tuple[str, ...],
    lookback: int,
    scope: str = "single_asset",
    *,
    target_daily_variance: float | None = None,
    max_exposure: float | None = None,
) -> IndicatorCandidate:
    return IndicatorCandidate.model_validate(
        {
            "signal_id": signal_id,
            "paper_doi": doi,
            "calculator": calculator,
            "family": family,
            "role": role,
            "required_fields": fields,
            "lookback": lookback,
            "formula": CANONICAL_FORMULAS[calculator],
            "scope": scope,
            "status": "PROPOSED",
            "target_daily_variance": target_daily_variance,
            "max_exposure": max_exposure,
        }
    )


ACADEMIC_SIGNALS: tuple[IndicatorCandidate, ...] = (
    _signal(
        "sma_direction",
        ACADEMIC_PAPERS[0].doi,
        "sma_direction",
        "trend",
        "regime",
        ("close",),
        20,
    ),
    _signal(
        "previous_range_breakout",
        ACADEMIC_PAPERS[0].doi,
        "previous_range_breakout",
        "breakout",
        "entry",
        ("high", "close"),
        20,
    ),
    _signal(
        "cross_sectional_momentum",
        ACADEMIC_PAPERS[1].doi,
        "cross_sectional_momentum",
        "momentum",
        "entry",
        ("close",),
        252,
        "cross_section",
    ),
    _signal(
        "time_series_momentum",
        ACADEMIC_PAPERS[2].doi,
        "time_series_momentum",
        "momentum",
        "entry",
        ("close",),
        252,
    ),
    _signal(
        "garman_klass_variance",
        ACADEMIC_PAPERS[3].doi,
        "garman_klass_variance",
        "volatility",
        "risk",
        ("open", "high", "low", "close"),
        20,
    ),
    _signal(
        "parkinson_variance",
        ACADEMIC_PAPERS[4].doi,
        "parkinson_variance",
        "volatility",
        "risk",
        ("high", "low"),
        20,
    ),
    _signal(
        "volatility_managed_exposure",
        ACADEMIC_PAPERS[5].doi,
        "volatility_managed_exposure",
        "volatility",
        "risk",
        ("close",),
        20,
        target_daily_variance=0.0001,
        max_exposure=1.0,
    ),
)


def seed_approved_references(catalog: ResearchCatalog) -> None:
    """Idempotent initial reviewed citations; all associated signals PROPOSED."""
    for paper in ACADEMIC_PAPERS:
        try:
            existing = catalog.get_paper(paper.doi)
        except ValueError:
            catalog.add_paper(paper)
        else:
            if existing != paper:
                raise ValueError("paper metadata conflict; never overwrite provenance")
    for indicator in ACADEMIC_SIGNALS:
        try:
            existing_signal = catalog.get_indicator(indicator.signal_id)
        except ValueError:
            catalog.add_indicator(indicator)
        else:
            if existing_signal.status == "PROPOSED" and existing_signal != indicator:
                raise ValueError("indicator seed conflict; explicit version required")
