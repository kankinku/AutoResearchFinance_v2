from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
            "KIS_PAPER_APP_KEY": values.get("KIS_PAPER_APP_KEY", ""),
            "KIS_PAPER_APP_SECRET": values.get("KIS_PAPER_APP_SECRET", ""),
            "KIS_PAPER_BASE_URL": values.get("KIS_PAPER_BASE_URL", ""),
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
            app_key=required["KIS_PAPER_APP_KEY"],
            app_secret=required["KIS_PAPER_APP_SECRET"],
            base_url=required["KIS_PAPER_BASE_URL"].rstrip("/"),
            account_number=values.get("KIS_ACCOUNT_NO", "").strip(),
            product_code=values.get("KIS_PRODUCT_CODE", "01").strip() or "01",
            symbols=symbols,
        )


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
