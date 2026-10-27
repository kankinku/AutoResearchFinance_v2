"""Compose one authenticated, same-document Quant research and chart workspace.

Legacy URLs and the evidence APIs remain unchanged. No iframe, no arbitrary
web content, and no request to a source provider from this composition layer.
"""

from __future__ import annotations

from scripts.quant_chart_oos_bridge import page as oos_page


def compose_unified_workspace(chart_html: str) -> str:
    if chart_html.count("<main>") != 1 or chart_html.count("</main>") != 1:
        raise ValueError("unrecognized development chart markup")
    separate = oos_page().decode("utf-8")
    if separate.count("<main>") != 1 or separate.count("</main>") != 1:
        raise ValueError("unrecognized retrospective chart markup")
    forward_inner = separate.split("<main>", 1)[1].split("</main>", 1)[0]
    required = [
        'id="oos-panel"',
        'id="oos-price"',
        'id="oos-equity"',
        'id="oos-start"',
        'id="oos-orders"',
        "사후 OOS · 비봉인",
    ]
    if any(item not in forward_inner for item in required):
        raise ValueError("missing frozen OOS evidence sections")
    old_nav_start = chart_html.index('<nav class="page-nav"')
    old_nav_end = chart_html.index("</nav>", old_nav_start) + len("</nav>")
    shell = """<div class="quant-workspace-switch" aria-label="Quant 통합 작업공간">
      <div class="quant-mode-tabs" role="tablist" aria-label="조회할 데이터 구간">
        <button type="button" role="tab" id="quant-tab-development"
          aria-controls="quant-panel-development" aria-selected="true"
          data-quant-tab="development">개발기간 <small>2020~2025</small></button>
        <button type="button" role="tab" id="quant-tab-oos"
          aria-controls="quant-panel-oos" aria-selected="false"
          data-quant-tab="oos">2026 검증 <small>G124 · 사후 OOS</small></button>
        <button type="button" role="tab" id="quant-tab-operations"
          aria-controls="quant-panel-operations" aria-selected="false"
          data-quant-tab="operations">연구 운영 <small>현재 상태</small></button>
      </div>
      <div class="quant-workspace-actions">
        <a href="research" class="quant-link-secondary">연구 상세보기</a>
        <a href="backtest" class="quant-link-secondary">기존 연구 결과</a>
      </div>
    </div>"""
    chart_html = chart_html[:old_nav_start] + shell + chart_html[old_nav_end:]
    # A single constant strip, backed by the live verified development/OOS APIs.
    summary = """<section class="quant-period-overview" aria-labelledby="quant-period-title">
      <div class="quant-period-intro">
        <div><p class="eyebrow">전략 일반화 점검 · 같은 G124, 서로 다른 평가기간</p>
        <h2 id="quant-period-title">개발 성과와 2026 검증을 한눈에</h2>
        <p>개발기간과 2026년은 <strong>서로 다른 평가구간</strong>입니다.
        두 수익률을 단순히 이어 붙이거나 합산하지 않습니다.</p></div>
        <span class="quant-caution">2026 사후 OOS · 전향적 봉인 아님</span>
      </div>
      <div class="quant-period-metrics" aria-live="polite">
        <button type="button" data-quant-jump="g124" class="quant-period-metric">
          <span>G124 · 개발기간 2020~2025</span>
          <strong id="quant-metric-dev">확인 중</strong>
          <small>원본 감사 일치 재현 · 클릭하면 G124 선택</small>
        </button>
        <button type="button" data-quant-jump="oos" class="quant-period-metric">
          <span>G124 · 2026년 미학습 구간</span>
          <strong id="quant-metric-oos">확인 중</strong>
          <small>과거 가격으로 별도 사후 검증 · 클릭하면 차트 전환</small>
        </button>
        <div class="quant-period-metric quant-period-benchmark">
          <span>2026년 QQQ 단순 보유</span>
          <strong id="quant-metric-qqq">확인 중</strong>
          <small>배당 제외 · 동일 기간 참고 기준</small>
        </div>
      </div>
      <p class="muted" id="quant-period-message" role="status">
        개발 구간은 48개 감사 검증 전략, 2026년 평가는 G124 한 개만 존재합니다.
      </p>
    </section>"""
    # An inline status element keeps the selected mode legible to screen readers.
    old_main_open = "<main>"
    chart_html = chart_html.replace(
        old_main_open,
        old_main_open
        + "\n"
        + summary
        + '<p id="quant-view-status" class="quant-view-status" '
        + 'role="status" aria-live="polite"></p>'
        + '\n<section id="quant-panel-development" role="tabpanel" '
        'aria-labelledby="quant-tab-development">\n',
        1,
    )
    operations = """<section class="quant-operations-panel" aria-labelledby="quant-ops-title">
      <div class="quant-ops-heading">
        <div><p class="eyebrow">읽기 전용 · 원본 Quant 연구 연결</p>
          <h2 id="quant-ops-title">연구 운영 현황</h2>
          <p class="muted">실시간 연구 원장을 조회합니다. 여기서는 연구를 시작하거나
          주문을 실행하지 않습니다.</p></div>
        <button type="button" id="quant-ops-refresh" class="button button-small">
          운영 상태 다시 확인</button>
      </div>
      <div class="quant-ops-grid">
        <div><span>원본 기록 세대</span><strong id="quant-ops-generation">—</strong>
          <small>현재 원장에 기록된 세대 수</small></div>
        <div><span>연구 성과 선두</span><strong id="quant-ops-best">—</strong>
          <small>연구 개발기간 기준 · OOS 아님</small></div>
        <div><span>연구 서버 상태</span><strong id="quant-ops-health">—</strong>
          <small>마지막 조회 정보 기준</small></div>
        <div><span>주문 기능</span><strong>비활성화</strong>
          <small>연구 전용 · Paper-only</small></div>
      </div>
      <p id="quant-ops-status" class="muted" role="status">원본 연구 연결 대기 중</p>
      <a class="button button-small" href="research">전체 연구 운영·세대 원장 보기</a>
    </section>"""
    chart_html = chart_html.replace(
        "</main>",
        "</section>\n"
        '<section id="quant-panel-oos" role="tabpanel" '
        'aria-labelledby="quant-tab-oos" hidden>\n' + forward_inner + "\n</section>\n"
        '<section id="quant-panel-operations" role="tabpanel" '
        'aria-labelledby="quant-tab-operations" hidden>\n' + operations + "\n</section></main>",
        1,
    )
    period = (
        '<div class="quant-quick-range"><span>빠른 확대</span>'
        + "".join(
            f'<button type="button" data-quant-period="{n}">{name}</button>'
            for n, name in (
                (30, "최근 1개월"),
                (90, "최근 3개월"),
                (180, "최근 6개월"),
                (0, "전체"),
            )
        )
        + "</div>"
    )
    source_date = '<div class="trace-date-range" role="group"'
    target_date = '<div class="trace-date-range" aria-label="2026 차트 확대 기간"'
    if chart_html.count(source_date) != 1 or chart_html.count(target_date) != 1:
        raise ValueError("chart date controls not recognized")
    chart_html = chart_html.replace(source_date, period + source_date, 1)
    chart_html = chart_html.replace(target_date, period + target_date, 1)
    chart_html = chart_html.replace(
        "</head>",
        '<link rel="stylesheet" href="chart-assets/quant-oos-2026.css?v=d8">\n'
        '<link rel="stylesheet" href="chart-assets/quant-unified.css?v=u1">\n'
        "</head>",
        1,
    )
    chart_html = chart_html.replace(
        "</body>",
        '<script defer src="chart-assets/quant-oos-2026.js?v=u1"></script>\n'
        '<script defer src="chart-assets/quant-unified.js?v=u1"></script>\n'
        "</body>",
        1,
    )
    chart_html = chart_html.replace(
        "Quant 연구 운영 · 매매 차트</h1>",
        "Quant 연구 운영 · 매매 차트</h1>",
        1,
    )
    # Existing source IDs and standalone HTML remain intact for regressions.
    assert chart_html.count('id="quant-panel-oos"') == 1
    assert chart_html.count('id="trade-visualization"') == 1
    assert chart_html.count('id="oos-price"') == 1
    assert chart_html.count('id="quant-panel-operations"') == 1
    assert "iframe" not in chart_html.lower()
    return chart_html
