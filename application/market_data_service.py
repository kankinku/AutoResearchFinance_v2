"""Read-only, interchangeable daily-market-data ingestion for GPT research.

Providers never get MCP arguments for URLs, credentials or arbitrary file paths.
Downloaded data is immutable development-only Parquet with declared provenance.
Neither this module nor the MCP tools can place trades.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx

from core.data.contracts import (
    Bar,
    DataContractError,
    DataZone,
    MarketDataSet,
    MarketSourceProvenance,
)
from core.data.parquet import ParquetDataProvider
from core.data.quality import market_data_quality
from integrations.kis.client import KISPaperClient
from integrations.kis.config import PaperKISConfig, _read_dotenv
from memory.evidence_store import EvidenceIntegrityError
from orchestration.evidence import require_research_zone

_SYMBOL_RE = re.compile(r"[A-Z][A-Z0-9.-]{0,14}\Z")
_MARKET_FILENAME = re.compile(
    r"(?P<symbol>[A-Z][A-Z0-9.-]{0,14})_"
    r"(?P<start>\d{4}-\d{2}-\d{2})_"
    r"(?P<end>\d{4}-\d{2}-\d{2})_"
    r"(?P<policy>raw|total_return_adjusted)\.parquet\Z"
)
_SUPPORTED = ("tiingo", "kis")
_ALLOWED_POLICIES = {"raw", "total_return_adjusted"}


class MarketDataError(ValueError):
    """Safe codes/messages, with no credential or vendor response body leakage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DailyPriceProvider(Protocol):
    def daily_bars(
        self, symbol: str, start: date, end: date, *, adjusted: bool
    ) -> tuple[Bar, ...]: ...


class TiingoDailyProvider:
    """Fixed-host EOD API; token is supplied only in an Authorization header."""

    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        if not token:
            raise MarketDataError("PROVIDER_NOT_CONFIGURED", "Tiingo API key is not configured.")
        self._token = token
        self._transport = transport

    def daily_bars(self, symbol: str, start: date, end: date, *, adjusted: bool) -> tuple[Bar, ...]:
        endpoint = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
        try:
            with httpx.Client(
                timeout=20, transport=self._transport, follow_redirects=False
            ) as client:
                response = client.get(
                    endpoint,
                    params={
                        "startDate": start.isoformat(),
                        "endDate": end.isoformat(),
                        "format": "json",
                    },
                    headers={"Authorization": f"Token {self._token}", "Accept": "application/json"},
                )
                if response.status_code == 429:
                    raise MarketDataError("PROVIDER_RATE_LIMITED", "Tiingo rate limit reached.")
                if response.status_code in {401, 403}:
                    raise MarketDataError(
                        "PROVIDER_AUTH_FAILED", "Tiingo rejected the configured API key."
                    )
                if response.status_code != 200:
                    raise MarketDataError(
                        "PROVIDER_UNAVAILABLE", "Tiingo price request did not succeed."
                    )
                payload = response.json()
        except MarketDataError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataError(
                "PROVIDER_UNAVAILABLE", "Tiingo transport or JSON response is unavailable."
            ) from exc
        if not isinstance(payload, list):
            raise MarketDataError(
                "INVALID_VENDOR_DATA", "Tiingo returned an unexpected price format."
            )
        bars = []
        for row in payload:
            if not isinstance(row, dict):
                raise MarketDataError("INVALID_VENDOR_DATA", "Tiingo price row has invalid shape.")
            try:
                raw_day = row["date"]
                if not isinstance(raw_day, str):
                    raise ValueError("date must be a string")
                stamp = datetime.fromisoformat(raw_day.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                stamp = stamp.astimezone(timezone.utc)
                if not start <= stamp.date() <= end:
                    continue
                prefix = "adj" if adjusted else ""
                fields = (
                    ("Open", "High", "Low", "Close", "Volume")
                    if adjusted
                    else ("open", "high", "low", "close", "volume")
                )
                values = (
                    [float(row[prefix + field]) for field in fields]
                    if adjusted
                    else [float(row[field]) for field in fields]
                )
                bars.append(Bar(stamp, symbol, *values))
            except (KeyError, TypeError, ValueError, OverflowError, DataContractError) as exc:
                raise MarketDataError(
                    "INVALID_VENDOR_DATA", "Tiingo returned missing or invalid OHLCV fields."
                ) from exc
        return tuple(sorted(bars, key=lambda bar: bar.timestamp))


class KISDailyProvider:
    """Uses the existing paper/read-only quote client; never an order client."""

    def __init__(self, client: KISPaperClient, *, exchange: str = "NAS") -> None:
        self._client = client
        self._exchange = exchange

    def daily_bars(self, symbol: str, start: date, end: date, *, adjusted: bool) -> tuple[Bar, ...]:
        if adjusted:
            raise MarketDataError("POLICY_UNSUPPORTED", "KIS EOD adapter supports only raw prices.")
        try:
            return self._client.daily_bars(
                symbol,
                start=start.strftime("%Y%m%d"),
                end=end.strftime("%Y%m%d"),
                exchange=self._exchange,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise MarketDataError(
                "PROVIDER_UNAVAILABLE", "KIS historical price request failed."
            ) from exc


class MarketDataService:
    """Discover and ingest only project-scoped price history.

    User-requested downloads are explicit. Never auto-fetch during a research batch.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        providers: dict[str, DailyPriceProvider] | None = None,
    ) -> None:
        self.root = project_root.resolve()
        self.directory = self.root / "data" / "market"
        self._providers = providers

    def provider_status(self) -> dict[str, object]:
        if self._providers is not None:
            configured = {name: name in self._providers for name in _SUPPORTED}
        else:
            kis_file = self.root / ".env"
            try:
                PaperKISConfig.from_env(kis_file)
                kis_configured = True
            except ValueError:
                kis_configured = False
            configured = {
                "tiingo": bool(self._tiingo_token()),
                "kis": kis_configured,
            }
        return {
            "providers": [
                {
                    "name": name,
                    "configured": configured[name],
                    "price_policies": (sorted(_ALLOWED_POLICIES) if name == "tiingo" else ["raw"]),
                }
                for name in _SUPPORTED
            ],
            "orders_enabled": False,
            "credentials_exposed": False,
        }

    def _tiingo_token(self) -> str:
        value = os.environ.get("TIINGO_API_KEY", "").strip()
        if value:
            return value
        # Existing ignored project .env; do not make token a tool argument.
        config = self.root / ".env"
        if config.is_file():
            return _read_dotenv(config).get("TIINGO_API_KEY", "").strip()
        return ""

    def _provider(self, name: str) -> DailyPriceProvider:
        if self._providers is not None:
            if name not in self._providers:
                raise MarketDataError(
                    "PROVIDER_NOT_CONFIGURED", f"{name} is not configured for market data."
                )
            return self._providers[name]
        if name == "tiingo":
            return TiingoDailyProvider(self._tiingo_token())
        if name == "kis":
            try:
                config = PaperKISConfig.from_env(self.root / ".env")
            except (OSError, ValueError) as exc:
                raise MarketDataError(
                    "PROVIDER_NOT_CONFIGURED", "KIS read-only paper configuration is unavailable."
                ) from exc
            return KISDailyProvider(KISPaperClient(config))
        raise MarketDataError("UNKNOWN_PROVIDER", "Unknown market data provider.")

    def list_datasets(self) -> dict[str, object]:
        records = []
        for path in sorted(self.directory.glob("*/*.parquet"))[:300]:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                records.append(self.validate_dataset(path.relative_to(self.root).as_posix()))
            except (MarketDataError, OSError, ValueError):
                continue
        return {"count": len(records), "datasets": records, "orders_enabled": False}

    def _managed_directory(self) -> Path:
        managed = self.directory.resolve()
        if self.root not in managed.parents or managed != self.directory:
            raise MarketDataError("DATA_PATH_UNSAFE", "Market data directory must be local.")
        return managed

    def _dataset_path(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise MarketDataError("INVALID_PATH", "A research data_path is required.")
        candidate = (self.root / path).resolve()
        # Never allow arbitrary server files, even when an MCP caller guesses paths.
        if self._managed_directory() not in candidate.parents or candidate.suffix != ".parquet":
            raise MarketDataError(
                "INVALID_PATH", "data_path must be a managed market Parquet file."
            )
        if not candidate.is_file():
            raise MarketDataError("DATA_FILE_NOT_FOUND", "Market data_path does not exist.")
        return candidate

    def validate_dataset(self, path: str) -> dict[str, object]:
        source = self._dataset_path(path)
        # Deny protected market zones before loading any Parquet price rows.
        try:
            require_research_zone(source)
        except EvidenceIntegrityError as exc:
            raise MarketDataError(
                "DATA_ZONE_DENIED", "Only development market data may be inspected."
            ) from exc
        except (OSError, ValueError) as exc:
            raise MarketDataError("INVALID_DATASET", "Market data file is invalid.") from exc
        try:
            dataset = ParquetDataProvider.read(source)
            self._check_dataset_identity(source, dataset)
            quality = market_data_quality(dataset)
        except MarketDataError:
            raise
        except (OSError, ValueError, KeyError, TypeError, DataContractError) as exc:
            raise MarketDataError("INVALID_DATASET", "Market data file is invalid.") from exc
        return {
            "data_path": source.relative_to(self.root).as_posix(),
            "bars": len(dataset.bars),
            "symbols": sorted({bar.symbol for bar in dataset.bars}),
            "start": dataset.bars[0].timestamp.date().isoformat() if dataset.bars else None,
            "end": dataset.bars[-1].timestamp.date().isoformat() if dataset.bars else None,
            "zone": DataZone(dataset.zone).value,
            "price_policy": dataset.provenance.corporate_action_policy
            if dataset.provenance
            else None,
            "source_id": dataset.provenance.source_id if dataset.provenance else None,
            "quality": quality.record(),
            "dataset_hash": dataset.dataset_hash,
            "point_in_time_independently_verified": False,
            "orders_enabled": False,
        }

    def _check_dataset_identity(self, source: Path, dataset: MarketDataSet) -> None:
        """Require filename, declared vendor and stored OHLCV to agree."""
        match = _MARKET_FILENAME.fullmatch(source.name)
        provider = source.parent.name
        if not match or provider not in _SUPPORTED:
            raise MarketDataError(
                "DATA_IDENTITY_MISMATCH", "Managed dataset filename or provider is invalid."
            )
        details = match.groupdict()
        try:
            start = date.fromisoformat(details["start"])
            end = date.fromisoformat(details["end"])
        except ValueError as exc:
            raise MarketDataError(
                "DATA_IDENTITY_MISMATCH", "Managed dataset date range is invalid."
            ) from exc
        provenance = dataset.provenance
        if (
            not dataset.bars
            or dataset.zone is not DataZone.DEVELOPMENT
            or dataset.timeframe != "1d"
            or dataset.calendar != "us_equities"
            or provenance is None
            or provenance.source_id != provider
            or provenance.corporate_action_policy != details["policy"]
            or {bar.symbol for bar in dataset.bars} != {details["symbol"]}
            or any(not start <= bar.timestamp.date() <= end for bar in dataset.bars)
            or (dataset.bars[0].timestamp.date() - start).days > 8
            or (end - dataset.bars[-1].timestamp.date()).days > 8
        ):
            raise MarketDataError(
                "DATA_IDENTITY_MISMATCH", "Stored market data does not match its filename."
            )

    def download(
        self,
        *,
        provider: str,
        symbol: str,
        start: str,
        end: str,
        price_policy: str = "raw",
    ) -> dict[str, object]:
        if provider not in _SUPPORTED:
            raise MarketDataError("UNKNOWN_PROVIDER", "Choose tiingo or kis.")
        if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
            raise MarketDataError(
                "INVALID_SYMBOL", "Symbol must be an uppercase US equity/ETF ticker."
            )
        if price_policy not in _ALLOWED_POLICIES:
            raise MarketDataError("INVALID_POLICY", "Choose raw or total_return_adjusted.")
        if provider == "kis" and price_policy != "raw":
            raise MarketDataError(
                "POLICY_UNSUPPORTED", "KIS adapter currently supports raw prices."
            )
        try:
            first = date.fromisoformat(start)
            last = date.fromisoformat(end)
        except (TypeError, ValueError) as exc:
            raise MarketDataError("INVALID_DATE", "Use ISO YYYY-MM-DD dates.") from exc
        if (
            first > last
            or last > datetime.now(timezone.utc).date()
            or (last - first).days > 365 * 35
        ):
            raise MarketDataError("INVALID_RANGE", "Choose a past interval of at most 35 years.")
        relative = (
            Path("data")
            / "market"
            / provider
            / f"{symbol}_{first.isoformat()}_{last.isoformat()}_{price_policy}.parquet"
        )
        target = self.root / relative
        self._managed_directory()
        if target.parent.resolve() != target.parent:
            raise MarketDataError("DATA_PATH_UNSAFE", "Market data provider directory is unsafe.")
        if target.is_symlink():
            raise MarketDataError("DATA_PATH_UNSAFE", "The dataset path is a symlink.")
        if target.exists():
            return {"status": "ALREADY_EXISTS", **self.validate_dataset(relative.as_posix())}
        vendor = self._provider(provider)
        bars = vendor.daily_bars(
            symbol, first, last, adjusted=(price_policy == "total_return_adjusted")
        )
        if not bars:
            raise MarketDataError("NO_MARKET_DATA", "Provider returned no price history.")
        if len(bars) > 15000:
            raise MarketDataError("DATA_LIMIT_EXCEEDED", "Too many daily price bars.")
        if any(
            bar.symbol != symbol or bar.timestamp.date() < first or bar.timestamp.date() > last
            for bar in bars
        ):
            raise MarketDataError(
                "INVALID_VENDOR_DATA", "Unexpected symbol or date in price history."
            )
        # Detect capped APIs or gaps at either edge. US holiday/weekend slack is allowed.
        ordered = sorted(bars, key=lambda item: item.timestamp)
        if (ordered[0].timestamp.date() - first).days > 8 or (
            last - ordered[-1].timestamp.date()
        ).days > 8:
            raise MarketDataError(
                "INCOMPLETE_RANGE", "Provider did not return the full requested date range."
            )
        policy_reference = (
            "https://www.tiingo.com/documentation/end-of-day"
            if provider == "tiingo" and price_policy == "total_return_adjusted"
            else None
        )
        try:
            dataset = MarketDataSet(
                "vendor-eod-v1",
                DataZone.DEVELOPMENT,
                tuple(ordered),
                provenance=MarketSourceProvenance(
                    source_id=provider,
                    retrieved_at=datetime.now(timezone.utc),
                    revision_policy="latest",
                    universe_policy="single_symbol",
                    corporate_action_policy=price_policy,
                    corporate_action_reference=policy_reference,
                    includes_delisted=False,
                ),
            )
        except (DataContractError, ValueError, TypeError) as exc:
            raise MarketDataError(
                "INVALID_VENDOR_DATA", "Provider returned inconsistent market price rows."
            ) from exc
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.is_symlink():
            raise MarketDataError("DATA_PATH_UNSAFE", "The data directory is unsafe.")
        # Use exclusive create semantics: never silently overwrite previous research input.
        import os as _os
        import tempfile

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".ingest-", suffix=".parquet", dir=target.parent, delete=False
            ) as tmp:
                tmp_path = Path(tmp.name)
            ParquetDataProvider.write(tmp_path, dataset)
            # Hard link exclusively; an existing research file is immutable.
            _os.link(tmp_path, target)
        except FileExistsError:
            return {"status": "ALREADY_EXISTS", **self.validate_dataset(relative.as_posix())}
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        return {"status": "DOWNLOADED", **self.validate_dataset(relative.as_posix())}
