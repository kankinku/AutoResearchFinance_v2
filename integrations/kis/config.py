from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


class KISConfigError(ValueError):
    """Raised when the paper-only KIS runtime is not configured safely."""


@dataclass(frozen=True)
class PaperKISConfig:
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    base_url: str
    account_number: str = ""
    product_code: str = "01"
    mode: str = "paper"
    symbols: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, path: Path) -> PaperKISConfig:
        values = _read_dotenv(path)
        mode = values.get("QUANT_TRADING_MODE", "paper").strip().lower()
        if mode not in {"", "paper", "demo"}:
            raise KISConfigError("paper-only runtime rejects non-paper trading mode")
        required = {
            "PAPER_KIS_APP_KEY": _setting(
                values, "PAPER_KIS_APP_KEY", "KIS_PAPER_APP_KEY"
            ),
            "PAPER_KIS_APP_SECRET": _setting(
                values, "PAPER_KIS_APP_SECRET", "KIS_PAPER_APP_SECRET"
            ),
            "PAPER_KIS_BASE_URL": _setting(
                values, "PAPER_KIS_BASE_URL", "KIS_PAPER_BASE_URL"
            ),
        }
        for name, value in required.items():
            if not value.strip():
                raise KISConfigError(f"missing required paper setting: {name}")
        symbols = tuple(
            symbol.strip().upper()
            for symbol in values.get("KIS_SYMBOLS", "").split(",")
            if symbol.strip()
        )
        return cls(
            app_key=required["PAPER_KIS_APP_KEY"],
            app_secret=required["PAPER_KIS_APP_SECRET"],
            base_url=required["PAPER_KIS_BASE_URL"].rstrip("/"),
            account_number=values.get("KIS_ACCOUNT_NO", "").strip(),
            product_code=values.get("KIS_PRODUCT_CODE", "01").strip() or "01",
            symbols=symbols,
        )


def _setting(values: dict[str, str], preferred: str, legacy: str) -> str:
    return values.get(preferred, "").strip() or values.get(legacy, "").strip()


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise KISConfigError(f"environment file does not exist: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            values[name] = value.strip().strip('"').strip("'")
    return values



def validate_paper_endpoint(
    config: PaperKISConfig, *, transport_is_injected: bool,
) -> None:
    """Fail closed before a paper-only client can send KIS credentials."""
    if config.mode not in {"", "paper", "demo"}:
        raise KISConfigError("paper-only client rejects non-paper trading mode")
    url = urlsplit(config.base_url)
    try:
        host, port = (url.hostname or "").lower(), url.port
    except ValueError as exc:
        raise KISConfigError("invalid paper endpoint port") from exc
    if (
        url.scheme != "https" or not host or url.username is not None
        or url.password is not None or url.path not in {"", "/"}
        or url.query or url.fragment
    ):
        raise KISConfigError("paper endpoint requires HTTPS without URL credentials or paths")
    if host != "openapivts.koreainvestment.com":
        # Test hosts are allowed only with an explicitly injected transport.
        # Production network clients must never send KIS tokens elsewhere.
        if not transport_is_injected or not host.endswith((".example", ".test", ".invalid")):
            raise KISConfigError("paper client requires the virtual KIS endpoint")
        if port is not None:
            raise KISConfigError("test paper endpoint must not specify a port")
    elif port not in {None, 29443}:
        raise KISConfigError("unexpected virtual paper endpoint port")
