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


def test_backtest_page_is_performance_first_and_hides_ids_in_diagnostics() -> None:
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    javascript = (STATIC / "backtest.js").read_text(encoding="utf-8")
    for marker in (
        "현재 세대",
        "전략 연복리",
        "QQQ 연복리",
        "QQQ 대비",
        "성능 향상 추이",
        "인디케이터와 입력 자료",
        "연도별 안정성",
        "상세 진단",
        "전체 실행 원장",
        "data-generation",
    ):
        assert marker in html
    assert "renderResearch" in javascript
    assert "renderGenerations" in javascript
    assert "renderDiagnostics" in javascript
    assert "generation_summary" in javascript
