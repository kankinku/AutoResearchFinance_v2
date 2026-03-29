from __future__ import annotations

from finance_autoresearch.research.models import KnowledgeSnippet


INDICATOR_VOCABULARY = (
    "ema",
    "sma",
    "rsi",
    "atr",
    "rolling_std",
    "xaverage",
    "macd",
    "rolling_corr",
    "simple_return",
    "log_return",
)

FACTOR_VOCABULARY = (
    "rolling_rank",
    "rolling_quantile",
    "trend_slope",
    "trend_fit",
    "trend_residual",
    "quantile",
    "turnover",
    "autocorrelation",
)

CONTEXT_SIGNAL_VOCABULARY = (
    "turbulence",
    "covariance",
    "vix",
    "metadata",
    "sector",
    "industry",
    "industry_group",
    "exchange",
    "country",
    "market_cap",
    "universe",
)

KNOWLEDGE_TAG_VOCABULARY = (
    *INDICATOR_VOCABULARY,
    *FACTOR_VOCABULARY,
    *CONTEXT_SIGNAL_VOCABULARY,
    "regime",
    "bull",
    "bear",
)


def allowed_indicator_pool(snippets: list[KnowledgeSnippet]) -> tuple[str, ...]:
    indicators: list[str] = []
    for snippet in snippets:
        for tag in snippet.tags:
            normalized = str(tag).strip().lower()
            if normalized in INDICATOR_VOCABULARY and normalized not in indicators:
                indicators.append(normalized)
    return tuple(indicators)


def knowledge_context_signals(snippets: list[KnowledgeSnippet]) -> tuple[str, ...]:
    signals: list[str] = []
    for snippet in snippets:
        for tag in snippet.tags:
            normalized = str(tag).strip().lower()
            if (
                normalized in CONTEXT_SIGNAL_VOCABULARY
                and normalized not in signals
            ):
                signals.append(normalized)
    return tuple(signals)


def knowledge_evidence(snippets: list[KnowledgeSnippet]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "source_id": snippet.source_id,
            "title": snippet.title,
            "relevance_reason": snippet.relevance_reason,
        }
        for snippet in snippets
    )
