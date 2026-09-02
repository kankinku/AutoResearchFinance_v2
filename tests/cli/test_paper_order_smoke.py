from __future__ import annotations

import json
from pathlib import Path

import cli
from integrations.kis.paper_orders import PaperOrderReceipt, PaperRoundTripResult


def test_paper_order_smoke_requires_explicit_confirmation() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["paper-order-smoke", "--env-file", ".env"])

    assert args.symbol == "QQQ"
    assert args.quantity == 1
    assert args.confirm_paper_order is False


def test_paper_order_smoke_is_paper_only_and_does_not_change_mode(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "KIS_PAPER_APP_KEY=placeholder",
                "KIS_PAPER_APP_SECRET=placeholder",
                "KIS_PAPER_BASE_URL=https://paper.example",
                "KIS_ACCOUNT_NO=12345678-01",
                "KIS_PRODUCT_CODE=01",
                "QUANT_TRADING_MODE=paper",
            )
        ),
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    mode_path = state_dir / "mode.json"
    mode_path.write_text(
        '{"selected_mode":"paper","orders_enabled":false}', encoding="utf-8"
    )
    receipt = PaperOrderReceipt("QQQ", "buy", "NASD", 1, "100")

    class FakeOrderClient:
        def __init__(self, config) -> None:
            assert config.mode == "paper"

        def run_buy_then_sell(
            self, symbol, *, quantity, exchange, timeout_seconds, poll_seconds
        ):
            assert (symbol, quantity, exchange) == ("QQQ", 1, "NASD")
            assert (timeout_seconds, poll_seconds) == (30.0, 1.0)
            return PaperRoundTripResult("FLAT", receipt, 1, receipt, 1, 0.0)

    monkeypatch.setattr(cli, "KISPaperOrderClient", FakeOrderClient)

    assert (
        cli.main(
            [
                "paper-order-smoke",
                "--state-dir",
                str(state_dir),
                "--env-file",
                str(env_path),
                "--confirm-paper-order",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FLAT"
    assert payload["mode"] == "paper"
    assert json.loads(mode_path.read_text(encoding="utf-8"))["orders_enabled"] is False
