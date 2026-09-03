from pathlib import Path

STATIC = Path(__file__).parents[2] / "dashboard" / "static"


def test_active_dashboard_pages_load_one_shared_label_contract_first() -> None:
    for page in ("index.html", "backtest.html"):
        content = (STATIC / page).read_text(encoding="utf-8")
        assert content.index('/static/labels.js') < content.index('.js"></script>')


def test_active_dashboard_scripts_do_not_redeclare_status_vocabulary() -> None:
    for script in ("app.js", "backtest.js"):
        content = (STATIC / script).read_text(encoding="utf-8")
        assert "const STATUS_LABELS" not in content
        assert "const statusLabel" not in content


def test_backtest_command_shows_all_canonical_evaluation_gates() -> None:
    content = (STATIC / "backtest.js").read_text(encoding="utf-8")
    assert "--min-trades 10" in content
    assert "--min-annual-trades 30" in content
    assert "--min-qqq-cagr 0.10" in content
