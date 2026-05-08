export function renderDashboardHtml(): string {
  return String.raw`<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AF 투자 연구 대시보드</title>
    <style>
    :root {
      --paper: #f2f4f6;
      --ink: #191f28;
      --muted: #8b95a1;
      --line: #e5e8eb;
      --panel: #ffffff;
      --accent: #191f28;
      --good: #00c773;
      --warn: #ffb020;
      --bad: #f04452;
      --positive: #f04452;
      --negative: #3182f6;
      --soft-good: #e9fbf2;
      --soft-red: #fef0f1;
      --soft-blue: #eef6ff;
      --soft-gray: #f2f4f6;
      --soft-warn: #fff7e6;
      --mono: "Cascadia Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
      --body: "Pretendard", "-apple-system", "BlinkMacSystemFont", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--body);
      -webkit-font-smoothing: antialiased;
      letter-spacing: -0.01em;
    }

    .shell {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .rail { display: none; }

    main {
      width: min(1200px, 100%);
      margin: 0 auto;
      padding: 32px 24px 60px;
      min-width: 0;
    }

    header {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 24px;
    }

    @media (min-width: 768px) {
      header {
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
      }
    }

    h1 {
      margin: 0;
      font-size: clamp(26px, 3.5vw, 36px);
      font-weight: 800;
      line-height: 1.3;
      letter-spacing: -0.02em;
    }

    .subline {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
      overflow-wrap: anywhere;
    }

    .status-strip {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .page-nav {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 0 0 16px;
      padding: 4px;
      background: #e9edf2;
      border-radius: 8px;
    }

    .page-tab {
      appearance: none;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: #4e5968;
      cursor: pointer;
      font-family: var(--body);
      font-size: 14px;
      font-weight: 800;
      min-height: 38px;
      padding: 9px 13px;
    }

    .page-tab.active {
      background: #ffffff;
      color: var(--ink);
      box-shadow: 0 1px 2px rgba(0,0,0,0.06);
    }

    .page {
      display: none;
    }

    .page.active {
      display: block;
    }

    .pill {
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 700;
      background: var(--soft-gray);
      color: #4e5968;
      white-space: nowrap;
    }
    .pill.good { color: var(--good); background: var(--soft-good); }
    .pill.warn { color: #b7791f; background: var(--soft-warn); }
    .pill.bad { color: var(--bad); background: var(--soft-red); }

    .grid, .two-col, .brief-band {
      display: grid;
      gap: 16px;
      margin-top: 16px;
      min-width: 0;
    }
    .grid { grid-template-columns: 1.35fr 0.85fr; }
    .brief-band { grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr); }
    .two-col { grid-template-columns: 1fr 1fr; }
    .stack { display: grid; gap: 16px; min-width: 0; }

    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 16px;
      margin-top: 16px;
    }

    .metric,
    .panel {
      background: var(--panel);
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.02), 0 1px 2px rgba(0,0,0,0.01);
      border: 1px solid rgba(229, 232, 235, 0.5);
    }

    .metric {
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 120px;
    }

    .panel {
      padding: 28px;
      min-width: 0;
    }

    .label, th {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      letter-spacing: -0.01em;
    }

    .value {
      font-size: clamp(24px, 2.5vw, 36px);
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.2;
      margin: 8px 0;
      font-variant-numeric: tabular-nums;
    }

    .value.positive { color: var(--positive); }
    .value.negative { color: var(--negative); }

    .delta {
      color: var(--muted);
      font-size: 13px;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .panel h2 {
      margin: 0 0 20px;
      font-size: 18px;
      font-weight: 800;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: var(--ink);
    }

    .panel h2 > span:last-child {
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
      background: var(--soft-gray);
      padding: 6px 10px;
      border-radius: 8px;
    }

    .brief-title {
      margin: 0 0 12px;
      font-size: 22px;
      font-weight: 800;
      line-height: 1.3;
      letter-spacing: -0.02em;
    }

    .copy {
      margin: 0;
      color: #333d4b;
      line-height: 1.6;
      font-size: 15px;
      overflow-wrap: anywhere;
      font-weight: 500;
    }

    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 20px;
    }

    .evidence {
      background: var(--soft-gray);
      border-radius: 12px;
      padding: 16px;
      min-height: 76px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }

    .evidence.good { background: var(--soft-good); }
    .evidence.watch { background: var(--soft-warn); }
    .evidence.bad { background: var(--soft-red); }
    .evidence.neutral { background: var(--soft-gray); }

    .evidence .label {
      margin-bottom: 6px;
      font-size: 12px;
    }

    .evidence .ev-value {
      font-family: var(--mono);
      font-size: 13px;
      font-weight: 700;
      color: var(--ink);
      overflow-wrap: anywhere;
    }
    
    .evidence.good .ev-value { color: var(--good); }
    .evidence.bad .ev-value { color: var(--bad); }

    .action-list, .warning-list {
      margin: 16px 0 0;
      padding-left: 20px;
      line-height: 1.6;
      font-size: 14px;
      font-weight: 500;
      color: #333d4b;
    }

    .warning-list {
      color: var(--bad);
    }

    .command-list {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }

    .command {
      background: var(--soft-gray);
      border-radius: 12px;
      padding: 16px;
    }

    .command code {
      display: block;
      margin-top: 8px;
      color: var(--ink);
      font-family: var(--mono);
      font-size: 13px;
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .chart {
      width: 100%;
      height: 300px;
      display: block;
      border-radius: 12px;
      background: transparent;
    }

    .feature-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }

    .context-band {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(340px, 0.95fr);
      gap: 16px;
      margin: 0 0 16px;
      min-width: 0;
    }

    .context-title {
      font-family: var(--mono);
      font-size: clamp(22px, 3vw, 34px);
      font-weight: 800;
      line-height: 1.2;
      margin: 4px 0 12px;
      overflow-wrap: anywhere;
    }

    .context-rows {
      margin-top: 16px;
    }

    .chip {
      font-size: 13px;
      font-weight: 600;
      border-radius: 8px;
      padding: 6px 10px;
      background: var(--soft-gray);
      color: #4e5968;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
      table-layout: fixed;
    }

    th, td {
      text-align: left;
      padding: 14px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      overflow-wrap: anywhere;
      color: #333d4b;
      font-weight: 500;
    }

    th {
      border-bottom-width: 2px;
      padding-top: 8px;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    td.mono { font-family: var(--mono); font-size: 13px; }
    .goodText { color: var(--good); font-weight: 700; }
    .warnText { color: var(--warn); font-weight: 700; }
    .badText { color: var(--bad); font-weight: 700; }
    .mutedText { color: var(--muted); font-weight: 700; }

    .hypothesis-grid {
      display: grid;
      gap: 12px;
    }

    .hypothesis-row {
      background: var(--soft-gray);
      border-radius: 8px;
      padding: 16px;
    }

    .record-hero {
      background: #0064ff;
      color: #ffffff;
    }

    .record-hero .label,
    .record-hero .copy,
    .record-hero .delta,
    .record-hero .value {
      color: #ffffff;
    }

    .record-hero .copy,
    .record-hero .delta {
      opacity: 0.86;
    }

    .record-stat-grid,
    .explain-grid {
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }

    .record-stat-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .record-stat,
    .explain-row {
      background: var(--soft-gray);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }

    .leaderboard-table th:nth-child(1),
    .leaderboard-table td:nth-child(1) { width: 58px; }
    .leaderboard-table th:nth-child(2),
    .leaderboard-table td:nth-child(2) { width: 112px; }

    .candidate-detail-list {
      display: grid;
      gap: 14px;
      margin-top: 16px;
    }

    .candidate-detail {
      background: var(--panel);
      border: 1px solid rgba(229, 232, 235, 0.75);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.02), 0 1px 2px rgba(0,0,0,0.01);
    }

    .candidate-detail-head {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 14px;
      align-items: start;
    }

    .rank-badge {
      min-width: 42px;
      height: 42px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--soft-blue);
      color: #0064ff;
      font-family: var(--mono);
      font-weight: 800;
      font-size: 14px;
    }

    .candidate-name {
      margin: 0 0 6px;
      font-family: var(--mono);
      font-size: 16px;
      font-weight: 800;
      color: var(--ink);
      overflow-wrap: anywhere;
    }

    .risk-badge {
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
      background: var(--soft-gray);
      color: #4e5968;
    }
    .risk-badge.good { color: var(--good); background: var(--soft-good); }
    .risk-badge.warn { color: #b7791f; background: var(--soft-warn); }
    .risk-badge.bad { color: var(--bad); background: var(--soft-red); }

    .detail-metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(110px, 1fr));
      gap: 8px;
      margin-top: 16px;
    }

    .detail-metric {
      background: var(--soft-gray);
      border-radius: 8px;
      padding: 12px;
      min-width: 0;
    }

    .detail-metric .metric-value {
      margin-top: 5px;
      font-family: var(--mono);
      font-size: 13px;
      font-weight: 800;
      color: var(--ink);
      overflow-wrap: anywhere;
    }

    .detail-columns {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 14px;
    }

    .detail-section {
      background: var(--soft-gray);
      border-radius: 8px;
      padding: 14px;
    }

    .detail-section ul {
      margin: 8px 0 0;
      padding-left: 18px;
      color: #333d4b;
      line-height: 1.5;
      font-size: 13px;
      font-weight: 500;
    }

    .candidate-detail .source-path {
      margin-top: 12px;
    }

    .record-hero .record-stat {
      background: rgba(255,255,255,0.14);
    }

    .source-path {
      margin-top: 14px;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .footer {
      margin-top: 32px;
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 500;
      padding: 24px 0 0;
    }

    @media (max-width: 1100px) {
      .grid, .two-col, .brief-band, .context-band { grid-template-columns: minmax(0, 1fr); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 560px) {
      main { padding: 20px 16px 40px; }
      .metrics { grid-template-columns: minmax(0, 1fr); }
      .evidence-grid { grid-template-columns: 1fr; }
      .page-nav { position: sticky; top: 0; z-index: 2; }
      .page-tab { flex: 1 1 auto; font-size: 13px; padding: 8px 10px; }
      .record-stat-grid { grid-template-columns: minmax(0, 1fr); }
      .candidate-detail-head,
      .detail-columns,
      .detail-metrics { grid-template-columns: minmax(0, 1fr); }
      .panel { padding: 20px; }
      .metric { padding: 20px; min-height: auto; }
      table { display: block; overflow-x: auto; }
      th, td { white-space: nowrap; }
    }
      /* Hover & Interactive Styles (Toss UI feel) */
    .metric,
    .panel {
      transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.2s cubic-bezier(0.2, 0, 0, 1);
    }
    
    .metric:hover,
    .panel:hover {
      transform: translateY(-4px);
      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.06), 0 4px 8px rgba(0, 0, 0, 0.04);
    }

    .chip, .pill, .evidence, .command {
      transition: background-color 0.2s ease, transform 0.2s ease;
      cursor: default;
    }

    .chip:hover, .evidence:hover, .command:hover {
      transform: scale(1.01);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    }

    .chip:active, .metric:active, .panel:active {
      transform: scale(0.99);
    }

    tbody tr {
      transition: background-color 0.15s ease;
    }
    tbody tr:hover td {
      background-color: #f9fafb;
    }

    /* Toss Blue Toggle Switch Style */
    .toggle-wrapper {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .toss-toggle {
      width: 44px;
      height: 24px;
      background: var(--line);
      border-radius: 12px;
      position: relative;
      transition: background-color 0.3s ease;
    }

    .toss-toggle::after {
      content: '';
      position: absolute;
      top: 2px;
      left: 2px;
      width: 20px;
      height: 20px;
      background: white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.4, 1.2);
    }

    .toss-toggle.active {
      background: var(--good);
    }

    .toss-toggle.active::after {
      transform: translateX(20px);
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="rail"><span>AF 검증 / QQQ 120분</span></aside>
    <main>
      <header>
        <div>
          <h1>AF 자율 투자 연구</h1>
          <div class="subline" id="subline">로컬 상태를 불러오는 중...</div>
        </div>
        <div class="status-strip">
          <span class="pill" id="loopStatus">루프</span>
          <span class="pill" id="improvementStatus">상태</span>
          <span class="pill" id="refreshStatus">갱신</span>
        </div>
      </header>

      <nav class="page-nav" aria-label="대시보드 페이지">
        <button class="page-tab active" type="button" data-page-target="overview">요약</button>
        <button class="page-tab" type="button" data-page-target="strategy">최고 기록</button>
        <button class="page-tab" type="button" data-page-target="explain">쉬운 해설</button>
        <button class="page-tab" type="button" data-page-target="validation">검증</button>
        <button class="page-tab" type="button" data-page-target="history">기록</button>
      </nav>

      <section class="context-band" aria-label="현재 연구 컨텍스트">
        <div class="panel">
          <h2><span>연구 컨텍스트</span><span id="researchModeBadge">-</span></h2>
          <div class="context-title" id="researchTargetLabel">-</div>
          <p class="copy" id="researchObjectiveFocus">-</p>
          <div class="feature-list" id="researchFocusChips"></div>
          <table class="context-rows">
            <tbody id="researchContextRows"></tbody>
          </table>
        </div>
        <div class="panel">
          <h2><span>전략 리뷰 지시</span><span id="strategyReviewConfidence">-</span></h2>
          <div class="context-title" id="strategyReviewDecision">-</div>
          <p class="copy" id="strategyReviewReason">-</p>
          <div class="feature-list" id="strategyReviewFocus"></div>
          <table class="context-rows">
            <tbody id="strategyReviewRows"></tbody>
          </table>
        </div>
      </section>

      <section class="page active" data-page="overview">
        <section class="brief-band">
          <div class="panel">
            <h2><span>운영 브리프</span><span id="operatorMode">-</span></h2>
            <h3 class="brief-title" id="briefHeadline">-</h3>
            <p class="copy" id="briefSummary">-</p>
            <div class="evidence-grid" id="operatorEvidence"></div>
            <ol class="action-list" id="nextActionList"></ol>
            <ul class="warning-list" id="warningList"></ul>
          </div>
          <div class="panel">
            <h2><span>외부 검증</span><span id="externalMode">수동</span></h2>
            <table>
              <tbody id="externalRows"></tbody>
            </table>
            <div class="command-list" id="commandList"></div>
          </div>
        </section>

        <section class="metrics">
          <div class="metric"><div class="label">최신 점수</div><div class="value" id="latestScore">-</div><div class="delta" id="latestDecision">-</div></div>
          <div class="metric"><div class="label">최신 수익률</div><div class="value" id="latestNet">-</div><div class="delta" id="latestTrades">-</div></div>
          <div class="metric"><div class="label">최근 최고 수익률</div><div class="value" id="bestReturn">-</div><div class="delta" id="bestReturnId">-</div></div>
          <div class="metric"><div class="label">최근 평균 수익률</div><div class="value" id="averageReturn">-</div><div class="delta" id="averageReturnDetail">최근 12개 후보</div></div>
          <div class="metric"><div class="label">수익 팩터</div><div class="value" id="latestPf">-</div><div class="delta" id="latestDd">-</div></div>
          <div class="metric"><div class="label">활성 챔피언</div><div class="value" id="championScore">-</div><div class="delta" id="championId">-</div></div>
          <div class="metric"><div class="label">최고 적격 후보</div><div class="value" id="bestScore">-</div><div class="delta" id="bestId">-</div></div>
          <div class="metric"><div class="label">최근 상태</div><div class="value" id="healthValue">-</div><div class="delta" id="healthDetail">-</div></div>
          <div class="metric"><div class="label">Node 메모리</div><div class="value" id="memoryValue">-</div><div class="delta" id="memoryDetail">-</div></div>
          <div class="metric"><div class="label">저장소</div><div class="value" id="storageValue">-</div><div class="delta" id="storageDetail">-</div></div>
        </section>

        <section class="grid">
          <div class="panel">
            <h2><span>최근 로컬 점수 추적</span><span id="chartMeta">-</span></h2>
            <svg class="chart" id="scoreChart" role="img" aria-label="최근 로컬 점수 추세"></svg>
          </div>
          <div class="panel">
            <h2><span>개선 상태</span><span id="generatedAt">-</span></h2>
            <p class="copy" id="improvementSummary">-</p>
            <div class="feature-list" id="nextFocus"></div>
          </div>
        </section>
      </section>

      <section class="page" data-page="strategy">
        <section class="grid">
          <div class="panel record-hero">
            <h2><span>현재 최고 수익률 기록</span><span id="recordCandidateId">-</span></h2>
            <div class="label">최근 로컬 후보 기준</div>
            <div class="value" id="recordReturn">-</div>
            <p class="copy" id="recordSummary">-</p>
            <div class="record-stat-grid">
              <div class="record-stat"><div class="label">점수</div><div class="delta" id="recordScore">-</div></div>
              <div class="record-stat"><div class="label">거래</div><div class="delta" id="recordTrades">-</div></div>
              <div class="record-stat"><div class="label">낙폭</div><div class="delta" id="recordDrawdown">-</div></div>
            </div>
          </div>
          <div class="panel">
            <h2><span>최고 기록 전략</span><span id="recordStrategyId">-</span></h2>
            <p class="copy" id="recordStrategySummary">-</p>
            <div class="feature-list" id="recordStrategyFeatures"></div>
            <table style="margin-top: 12px">
              <tbody id="recordStrategyTable"></tbody>
            </table>
            <div class="source-path" id="recordStrategySource">-</div>
          </div>
        </section>

        <section class="two-col">
          <div class="panel">
            <h2><span>최고 적격 전략</span><span id="strategyId">-</span></h2>
            <p class="copy" id="strategySummary">-</p>
            <div class="feature-list" id="strategyFeatures"></div>
            <table style="margin-top: 12px">
              <tbody id="strategyTable"></tbody>
            </table>
          </div>
          <div class="panel">
            <h2><span>성과 비교</span><span>점수 vs 수익률</span></h2>
            <table>
              <tbody id="recordCompareRows"></tbody>
            </table>
          </div>
        </section>
      </section>

      <section class="page" data-page="explain">
        <section class="grid">
          <div class="panel">
            <h2><span>쉬운 전략 해설</span><span id="explainStrategyId">-</span></h2>
            <p class="copy" id="explanationSummary">-</p>
            <div class="explain-grid" id="explainRows"></div>
          </div>
          <div class="panel">
            <h2><span>운영 체크리스트</span><span>읽기용</span></h2>
            <ol class="action-list" id="explainChecklist"></ol>
          </div>
        </section>

        <section class="two-col">
          <div class="panel">
            <h2><span>현재 가설</span><span id="repairMode">-</span></h2>
            <div class="hypothesis-grid" id="hypothesisGrid"></div>
          </div>
          <div class="panel">
            <h2><span>핵심 파라미터</span><span id="explainParamMeta">-</span></h2>
            <table>
              <tbody id="explainParamRows"></tbody>
            </table>
          </div>
        </section>
      </section>

      <section class="page" data-page="validation">
        <section class="grid">
          <div class="panel">
            <h2><span>TradingView 최종 모델 결과</span><span id="tvResultMeta">-</span></h2>
            <svg class="chart" id="tvResultChart" role="img" aria-label="TradingView 최종 모델 결과"></svg>
          </div>
          <div class="panel">
            <h2><span>TV 결과 요약</span><span id="tvResultSummaryMeta">-</span></h2>
            <table>
              <tbody id="tvResultSummaryRows"></tbody>
            </table>
          </div>
        </section>

        <section class="two-col">
          <div class="panel">
            <h2><span>검증 승격 조건</span><span id="verifiedCandidate">-</span></h2>
            <table>
              <tbody id="verifiedContractRows"></tbody>
            </table>
          </div>
          <div class="panel">
            <h2><span>브랜치 배분</span><span id="branchBudgetMeta">-</span></h2>
            <table>
              <thead><tr><th>브랜치</th><th>목표</th><th>실제</th><th>부족분</th></tr></thead>
              <tbody id="branchBudgetRows"></tbody>
            </table>
          </div>
        </section>

        <section class="two-col">
          <div class="panel">
            <h2><span>수동 TV 큐</span><span id="queueMeta">-</span></h2>
            <table>
              <thead><tr><th>ID</th><th>상태</th><th>사유</th><th>기록</th></tr></thead>
              <tbody id="externalEventRows"></tbody>
            </table>
          </div>
          <div class="panel">
            <h2><span>최신 로컬/TV 차이</span><span id="driftMeta">-</span></h2>
            <table>
              <tbody id="driftRows"></tbody>
            </table>
          </div>
        </section>
      </section>

      <section class="page" data-page="history">
        <section class="grid">
          <div class="panel">
            <h2><span>상위 20개 후보 분석</span><span id="topCandidateMeta">-</span></h2>
            <table class="leaderboard-table">
              <thead><tr><th>순위</th><th>ID</th><th>로컬 수익률</th><th>TV 수익률</th><th>점수</th><th>검증</th></tr></thead>
              <tbody id="topCandidateRows"></tbody>
            </table>
          </div>
          <div class="panel">
            <h2><span>상위 후보 요약</span><span id="topCandidateSummaryMeta">-</span></h2>
            <table>
              <tbody id="topCandidateSummaryRows"></tbody>
            </table>
          </div>
        </section>

        <section class="candidate-detail-list" id="topCandidateDetails"></section>

        <section class="grid">
          <div class="panel">
            <h2><span>최근 후보</span><span>최근 구간</span></h2>
            <table>
              <thead><tr><th>ID</th><th>점수</th><th>수익률</th><th>거래수</th><th>결정</th></tr></thead>
              <tbody id="candidateRows"></tbody>
            </table>
          </div>
          <div class="stack">
            <div class="panel">
              <h2><span>실패 메모리</span><span id="problemCount">-</span></h2>
              <table>
                <thead><tr><th>회차</th><th>종류</th><th>진단</th></tr></thead>
                <tbody id="problemRows"></tbody>
              </table>
            </div>
            <div class="panel">
              <h2><span>수리 기록</span><span id="repairCount">-</span></h2>
              <table>
                <thead><tr><th>회차</th><th>수리</th><th>결과</th></tr></thead>
                <tbody id="repairRows"></tbody>
              </table>
            </div>
          </div>
        </section>
      </section>

      <div class="footer">
        <span id="paths">로컬 파일만 사용</span>
        <span>자동 갱신: 8초</span>
      </div>
    </main>
  </div>

  <script>
    const state = {
      timer: null,
      loading: false,
      failures: 0,
      refreshIntervalMs: 8000,
      requestTimeoutMs: 6000,
      lastDataGeneratedAt: null
    };

    function fmt(value, digits) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return Number(value).toFixed(digits);
    }

    function pct(value) {
      return value === null || value === undefined ? "-" : fmt(value, 2) + "%";
    }

    function text(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function toneValue(id, value) {
      const el = document.getElementById(id);
      if (!el) return;
      const numeric = Number(value);
      el.className = "value" + (
        Number.isFinite(numeric)
          ? numeric > 0
            ? " positive"
            : numeric < 0
              ? " negative"
              : ""
          : ""
      );
    }

    function cls(id, value) {
      const el = document.getElementById(id);
      if (el) el.className = value;
    }

    function shortId(value) {
      return value ? value.replace("cand-", "c-") : "-";
    }

    function modeLabel(mode) {
      return mode === "local_only" ? "로컬 전용" : "외부 자동";
    }

    function goalModeLabel(value) {
      const labels = {
        explore: "탐색",
        improve: "개선",
        repair: "수리",
        calibrate: "보정",
        promote: "승격"
      };
      return labels[value] || value || "-";
    }

    function calibrationPolicyLabel(value) {
      const labels = {
        target_default: "기본",
        queue_only: "큐 보관",
        tv_priority: "TV 우선",
        promotion_readiness: "승격 준비"
      };
      return labels[value] || value || "-";
    }

    function reviewDecisionLabel(value) {
      const labels = {
        exploit_parent: "부모 활용",
        repair_near_miss: "근접 후보 수리",
        redirect_family: "패밀리 전환",
        simplify_family: "단순화",
        quarantine_family: "패밀리 격리",
        calibrate_candidate: "후보 보정",
        no_action: "조치 없음"
      };
      return labels[value] || value || "-";
    }

    function improvementLabel(status) {
      if (status === "improving") return "개선 중";
      if (status === "blocked") return "막힘";
      return "관찰";
    }

    function decisionLabel(value) {
      const labels = {
        local_candidate_eligible: "로컬 적격",
        tv_verified: "TV 검증 완료",
        calibration_queued: "TV 검증 대기",
        quarantined: "격리",
        rejected: "제외",
        failed: "실패",
        skipped: "건너뜀"
      };
      return labels[value] || value || "-";
    }

    function queueStatusLabel(value) {
      const labels = {
        pending: "대기",
        deferred: "보류",
        queued: "큐 등록",
        processed: "처리됨",
        skipped: "건너뜀",
        failed: "실패",
        deactivated: "비활성"
      };
      return labels[value] || value || "-";
    }

    function countKeyLabel(value) {
      const labels = {
        champion: "챔피언",
        calibration_queued: "검증 대기",
        quarantined: "격리",
        matched: "일치",
        major_drift: "큰 차이",
        minor_drift: "작은 차이",
        passed: "통과",
        failed: "실패"
      };
      return labels[value] || value;
    }

    function renderChipList(id, values) {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = "";
      (values || []).forEach(function(value) {
        const span = document.createElement("span");
        span.className = "chip";
        span.textContent = value;
        el.appendChild(span);
      });
    }

    function renderChart(points) {
      const svg = document.getElementById("scoreChart");
      svg.innerHTML = "";
      const width = 820;
      const height = 270;
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      const pad = { left: 46, right: 18, top: 20, bottom: 34 };
      const values = (points || []).map(function(p) { return p.score; }).filter(function(v) { return typeof v === "number"; });
      if (values.length < 2) {
        const empty = document.createElementNS("http://www.w3.org/2000/svg", "text");
        empty.setAttribute("x", "30");
        empty.setAttribute("y", "130");
        empty.setAttribute("font-family", "var(--mono)");
        empty.setAttribute("font-size", "13");
        empty.textContent = "점수 데이터가 부족합니다";
        svg.appendChild(empty);
        return;
      }
      const min = Math.min.apply(null, values);
      const max = Math.max.apply(null, values);
      const span = Math.max(0.001, max - min);
      const usableW = width - pad.left - pad.right;
      const usableH = height - pad.top - pad.bottom;
      const linePoints = points.map(function(p, index) {
        const x = pad.left + (points.length === 1 ? 0 : index * usableW / (points.length - 1));
        const y = pad.top + (max - (p.score || 0)) * usableH / span;
        return { x: x, y: y, p: p };
      });

      for (let i = 0; i <= 4; i += 1) {
        const y = pad.top + i * usableH / 4;
        const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
        grid.setAttribute("x1", String(pad.left));
        grid.setAttribute("x2", String(width - pad.right));
        grid.setAttribute("y1", String(y));
        grid.setAttribute("y2", String(y));
        grid.setAttribute("stroke", "#e5e8eb");
        grid.setAttribute("stroke-width", "1");
        svg.appendChild(grid);
      }

      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "#f04452");
      poly.setAttribute("stroke-width", "3");
      poly.setAttribute("points", linePoints.map(function(pt) { return pt.x + "," + pt.y; }).join(" "));
      svg.appendChild(poly);

      linePoints.forEach(function(pt) {
        const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        dot.setAttribute("cx", String(pt.x));
        dot.setAttribute("cy", String(pt.y));
        dot.setAttribute("r", pt.p.eligible ? "5" : "3");
        dot.setAttribute("fill", pt.p.eligible ? "#f04452" : "#8b95a1");
        svg.appendChild(dot);
      });

      const minLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
      minLabel.setAttribute("x", "8");
      minLabel.setAttribute("y", String(height - pad.bottom));
      minLabel.setAttribute("font-family", "var(--mono)");
      minLabel.setAttribute("font-size", "11");
      minLabel.textContent = fmt(min, 3);
      svg.appendChild(minLabel);

      const maxLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
      maxLabel.setAttribute("x", "8");
      maxLabel.setAttribute("y", String(pad.top + 4));
      maxLabel.setAttribute("font-family", "var(--mono)");
      maxLabel.setAttribute("font-size", "11");
      maxLabel.textContent = fmt(max, 3);
      svg.appendChild(maxLabel);
    }

    function renderTvResultChart(points) {
      const svg = document.getElementById("tvResultChart");
      if (!svg) return;
      svg.innerHTML = "";
      const width = 820;
      const height = 270;
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      const pad = { left: 48, right: 18, top: 20, bottom: 38 };
      const rows = (points || []).filter(function(p) {
        return typeof p.tvReturnPercent === "number" || typeof p.netProfitDelta === "number";
      });
      if (rows.length < 1) {
        const empty = document.createElementNS("http://www.w3.org/2000/svg", "text");
        empty.setAttribute("x", "30");
        empty.setAttribute("y", "130");
        empty.setAttribute("font-family", "var(--mono)");
        empty.setAttribute("font-size", "13");
        empty.textContent = "TradingView 검증 결과가 아직 없습니다";
        svg.appendChild(empty);
        return;
      }
      const deltas = rows
        .map(function(p) { return typeof p.netProfitDelta === "number" ? p.netProfitDelta : 0; });
      const min = Math.min(-1, Math.min.apply(null, deltas));
      const max = Math.max(1, Math.max.apply(null, deltas));
      const span = Math.max(1, max - min);
      const usableW = width - pad.left - pad.right;
      const usableH = height - pad.top - pad.bottom;
      const zeroY = pad.top + (max - 0) * usableH / span;

      for (let i = 0; i <= 4; i += 1) {
        const y = pad.top + i * usableH / 4;
        const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
        grid.setAttribute("x1", String(pad.left));
        grid.setAttribute("x2", String(width - pad.right));
        grid.setAttribute("y1", String(y));
        grid.setAttribute("y2", String(y));
        grid.setAttribute("stroke", "#e5e8eb");
        grid.setAttribute("stroke-width", "1");
        svg.appendChild(grid);
      }

      const zero = document.createElementNS("http://www.w3.org/2000/svg", "line");
      zero.setAttribute("x1", String(pad.left));
      zero.setAttribute("x2", String(width - pad.right));
      zero.setAttribute("y1", String(zeroY));
      zero.setAttribute("y2", String(zeroY));
      zero.setAttribute("stroke", "#8b95a1");
      zero.setAttribute("stroke-width", "1.5");
      svg.appendChild(zero);

      const gap = 5;
      const barW = Math.max(8, (usableW / Math.max(1, rows.length)) - gap);
      rows.forEach(function(p, index) {
        const delta = typeof p.netProfitDelta === "number" ? p.netProfitDelta : 0;
        const x = pad.left + index * usableW / rows.length + gap / 2;
        const y = pad.top + (max - delta) * usableH / span;
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(x));
        rect.setAttribute("y", String(Math.min(y, zeroY)));
        rect.setAttribute("width", String(barW));
        rect.setAttribute("height", String(Math.max(2, Math.abs(zeroY - y))));
        rect.setAttribute("rx", "4");
        rect.setAttribute("fill", delta >= 0 ? "var(--positive)" : "var(--negative)");
        rect.setAttribute("opacity", p.parityStatus === "matched" ? "0.65" : "0.9");
        svg.appendChild(rect);

        const confidence = typeof p.confidenceAfter === "number" ? p.confidenceAfter : null;
        if (confidence !== null) {
          const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          dot.setAttribute("cx", String(x + barW / 2));
          dot.setAttribute("cy", String(pad.top + (1 - confidence) * usableH));
          dot.setAttribute("r", p.parityStatus === "matched" ? "5" : "4");
          dot.setAttribute("fill", p.parityStatus === "matched" ? "var(--good)" : "var(--warn)");
          svg.appendChild(dot);
        }
      });

      const minLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
      minLabel.setAttribute("x", "8");
      minLabel.setAttribute("y", String(height - pad.bottom));
      minLabel.setAttribute("font-family", "var(--mono)");
      minLabel.setAttribute("font-size", "11");
      minLabel.textContent = fmt(min, 1) + "%";
      svg.appendChild(minLabel);

      const maxLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
      maxLabel.setAttribute("x", "8");
      maxLabel.setAttribute("y", String(pad.top + 4));
      maxLabel.setAttribute("font-family", "var(--mono)");
      maxLabel.setAttribute("font-size", "11");
      maxLabel.textContent = fmt(max, 1) + "%";
      svg.appendChild(maxLabel);

      const caption = document.createElementNS("http://www.w3.org/2000/svg", "text");
      caption.setAttribute("x", String(pad.left));
      caption.setAttribute("y", String(height - 10));
      caption.setAttribute("font-family", "var(--mono)");
      caption.setAttribute("font-size", "11");
      caption.setAttribute("fill", "#4e5968");
      caption.textContent = "막대: TV-로컬 수익률 차이, 점: 검증 신뢰도";
      svg.appendChild(caption);
    }

    function row(cells) {
      const tr = document.createElement("tr");
      cells.forEach(function(cell) {
        const td = document.createElement("td");
        if (cell.className) td.className = cell.className;
        td.textContent = cell.value;
        tr.appendChild(td);
      });
      return tr;
    }

    function renderRows(id, rows) {
      const body = document.getElementById(id);
      if (!body) return;
      body.innerHTML = "";
      rows.forEach(function(item) { body.appendChild(item); });
    }

    function metricBox(label, value, className) {
      const box = document.createElement("div");
      box.className = "detail-metric";
      const labelEl = document.createElement("div");
      labelEl.className = "label";
      labelEl.textContent = label;
      const valueEl = document.createElement("div");
      valueEl.className = "metric-value" + (className ? " " + className : "");
      valueEl.textContent = value;
      box.appendChild(labelEl);
      box.appendChild(valueEl);
      return box;
    }

    function detailList(title, values, fallback) {
      const section = document.createElement("div");
      section.className = "detail-section";
      const label = document.createElement("div");
      label.className = "label";
      label.textContent = title;
      const list = document.createElement("ul");
      const items = values && values.length > 0 ? values : [fallback || "-"];
      items.forEach(function(value) {
        const li = document.createElement("li");
        li.textContent = value;
        list.appendChild(li);
      });
      section.appendChild(label);
      section.appendChild(list);
      return section;
    }

    function riskClass(tone) {
      if (tone === "good") return "good";
      if (tone === "bad") return "bad";
      if (tone === "warn") return "warn";
      return "";
    }

    function renderTopCandidateDetails(items) {
      const el = document.getElementById("topCandidateDetails");
      if (!el) return;
      el.innerHTML = "";
      if (!items || items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "candidate-detail";
        empty.textContent = "상위 후보 데이터가 아직 없습니다.";
        el.appendChild(empty);
        return;
      }
      items.forEach(function(item) {
        const card = document.createElement("article");
        card.className = "candidate-detail";

        const head = document.createElement("div");
        head.className = "candidate-detail-head";
        const rank = document.createElement("div");
        rank.className = "rank-badge";
        rank.textContent = "#" + (item.rank || "-");
        const titleWrap = document.createElement("div");
        const title = document.createElement("h3");
        title.className = "candidate-name";
        title.textContent = shortId(item.candidateId);
        const summary = document.createElement("p");
        summary.className = "copy";
        summary.textContent = item.summary || "-";
        titleWrap.appendChild(title);
        titleWrap.appendChild(summary);
        const risk = document.createElement("span");
        risk.className = "risk-badge " + riskClass(item.riskTone);
        risk.textContent = item.riskLabel || "-";
        head.appendChild(rank);
        head.appendChild(titleWrap);
        head.appendChild(risk);
        card.appendChild(head);

        const metrics = document.createElement("div");
        metrics.className = "detail-metrics";
        metrics.appendChild(metricBox("로컬 수익률", pct(item.localReturnPercent), item.localReturnPercent === null || item.localReturnPercent === undefined ? "" : item.localReturnPercent >= 0 ? "goodText" : "badText"));
        metrics.appendChild(metricBox("TV 수익률", pct(item.tvReturnPercent), item.tvReturnPercent === null || item.tvReturnPercent === undefined ? "" : item.tvReturnPercent >= 0 ? "goodText" : "badText"));
        metrics.appendChild(metricBox("점수", item.score === null || item.score === undefined ? "-" : fmt(item.score, 4), "mono"));
        metrics.appendChild(metricBox("PF / 거래", (item.localProfitFactor === null || item.localProfitFactor === undefined ? "-" : fmt(item.localProfitFactor, 2)) + " / " + (item.localTradeCount || "-"), "mono"));
        metrics.appendChild(metricBox("DD / 승률", pct(item.localDrawdownPercent) + " / " + pct(item.localWinRate), item.localDrawdownPercent >= 45 ? "badText" : "mono"));
        metrics.appendChild(metricBox("TV 차이", pct(item.tvNetProfitDelta) + " / " + (item.tvTradeCountDelta === null || item.tvTradeCountDelta === undefined ? "-" : item.tvTradeCountDelta), item.tvParityStatus === "major_drift" ? "badText" : "mono"));
        card.appendChild(metrics);

        const columns = document.createElement("div");
        columns.className = "detail-columns";
        columns.appendChild(detailList("강점", item.strengths, "강점 요약 없음"));
        columns.appendChild(detailList("주의", item.cautions, "주의 항목 없음"));
        card.appendChild(columns);

        const source = document.createElement("div");
        source.className = "source-path";
        source.textContent = [
          "결정 " + decisionLabel(item.decision),
          "TV " + queueStatusLabel(item.tvParityStatus),
          "WF " + queueStatusLabel(item.walkForwardStatus),
          item.sourcePath || "-"
        ].join(" / ");
        card.appendChild(source);
        el.appendChild(card);
      });
    }

    function renderSimpleList(id, values, emptyText) {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = "";
      const items = values && values.length > 0 ? values : (emptyText ? [emptyText] : []);
      items.forEach(function(value) {
        const li = document.createElement("li");
        li.textContent = value;
        el.appendChild(li);
      });
    }

    function renderOperatorEvidence(items) {
      const el = document.getElementById("operatorEvidence");
      if (!el) return;
      el.innerHTML = "";
      (items || []).forEach(function(item) {
        const div = document.createElement("div");
        div.className = "evidence " + (item.status || "neutral");
        div.innerHTML = '<span class="label"></span><div class="ev-value"></div>';
        div.querySelector(".label").textContent = item.label;
        div.querySelector(".ev-value").textContent = item.value;
        el.appendChild(div);
      });
    }

    function averageNumber(values) {
      const nums = (values || []).filter(function(value) { return typeof value === "number" && Number.isFinite(value); });
      if (nums.length === 0) return null;
      return nums.reduce(function(sum, value) { return sum + value; }, 0) / nums.length;
    }

    function renderCommands(commands) {
      const el = document.getElementById("commandList");
      if (!el) return;
      el.innerHTML = "";
      (commands || []).forEach(function(item) {
        const div = document.createElement("div");
        div.className = "command";
        div.innerHTML = '<div class="label"></div><code></code>';
        div.querySelector(".label").textContent = item.label;
        div.querySelector("code").textContent = item.command;
        el.appendChild(div);
      });
    }

    function findCandidatePoint(data, candidateId) {
      if (!candidateId) return null;
      const pools = []
        .concat(data.recentCandidates || [])
        .concat(data.trend || [])
        .concat(data.score && data.score.latest ? [data.score.latest] : []);
      for (let i = pools.length - 1; i >= 0; i -= 1) {
        if (pools[i] && pools[i].candidateId === candidateId) return pools[i];
      }
      return null;
    }

    function renderStrategyAnalysis(prefix, strategy) {
      text(prefix + "Id", strategy ? shortId(strategy.candidateId) : "-");
      text(prefix + "Summary", strategy ? (strategy.summary || strategy.title || "요약 없음") : "-");
      renderChipList(prefix + "Features", strategy ? strategy.features : []);
      const rows = [];
      if (strategy) {
        rows.push(row([{ value: "진입", className: "mono" }, { value: strategy.entryShape || "-" }]));
        rows.push(row([{ value: "청산", className: "mono" }, { value: strategy.exitShape || "-" }]));
        rows.push(row([{ value: "리스크", className: "mono" }, { value: strategy.riskShape || "-" }]));
        Object.keys(strategy.routeInputs || {}).forEach(function(key) {
          rows.push(row([{ value: key, className: "mono" }, { value: strategy.routeInputs[key] === null ? "-" : String(strategy.routeInputs[key]) }]));
        });
      }
      renderRows(prefix + "Table", rows);
    }

    function explainStrategy(strategy, recordPoint) {
      if (!strategy) {
        return {
          summary: "분석할 전략 파일이 아직 없습니다.",
          rows: [],
          checklist: ["최고 수익률 후보가 생성되면 전략 구조를 자동으로 요약합니다."]
        };
      }
      const metrics = recordPoint && recordPoint.metrics;
      const drawdown = metrics ? metrics.maxDrawdownPercent : null;
      const highDrawdown = drawdown !== null && drawdown !== undefined && drawdown >= 35;
      const entryWindow = strategy.routeInputs && strategy.routeInputs.eventWindowBars !== null && strategy.routeInputs.eventWindowBars !== undefined
        ? strategy.routeInputs.eventWindowBars + "봉"
        : "최근 이벤트 구간";
      const summary = "이 전략은 AF 이벤트가 최근에 발생한 구간에서만 롱 진입을 허용하고, 여러 슬롯을 나눠 보유한 뒤 약한 포지션부터 정리하는 구조입니다.";
      return {
        summary: summary,
        rows: [
          ["진입", (strategy.entryShape || "AF 이벤트 진입") + ": 이벤트 발생 후 " + entryWindow + " 안에서만 참여해 신호가 오래된 구간을 피합니다."],
          ["포지션", (strategy.features || []).indexOf("slot replacement") >= 0 ? "여러 슬롯을 나눠 잡고, 더 강한 신호가 나오면 약한 슬롯을 교체합니다." : "여러 진입을 분산해 한 번의 신호에 과하게 의존하지 않습니다."],
          ["청산", (strategy.exitShape || "약한 포지션 정리") + ": 오래 버티지 못하는 손실 슬롯을 먼저 줄여 전체 변동성을 낮추는 쪽입니다."],
          ["리스크", (strategy.riskShape || "위험 회피 조건") + ": 추세가 약하거나 위험 신호가 강하면 추가 진입과 보유를 제한합니다."],
          ["주의", highDrawdown ? "수익률은 강하지만 최대 낙폭이 큽니다. 실제 적용 전 수동 TradingView 검증과 구간별 손실 확인이 필요합니다." : "낙폭은 상대적으로 억제되어 있지만, TradingView 수동 검증 전까지는 로컬 결과로만 봐야 합니다."]
        ],
        checklist: [
          "최근 최고 수익률 후보와 최고 점수 후보가 같은지 먼저 확인합니다.",
          "수익률만 보지 말고 거래 수, 수익 팩터, 최대 낙폭을 같이 봅니다.",
          "TradingView는 수동 검증으로만 돌리고, major_drift가 있으면 실전 판단에서 보류합니다."
        ]
      };
    }

    function renderExplanation(strategy, recordPoint) {
      const explanation = explainStrategy(strategy, recordPoint);
      text("explanationSummary", explanation.summary);
      const el = document.getElementById("explainRows");
      if (el) {
        el.innerHTML = "";
        explanation.rows.forEach(function(pair) {
          const div = document.createElement("div");
          div.className = "explain-row";
          div.innerHTML = '<div class="label"></div><p class="copy"></p>';
          div.querySelector(".label").textContent = pair[0];
          div.querySelector(".copy").textContent = pair[1];
          el.appendChild(div);
        });
      }
      renderSimpleList("explainChecklist", explanation.checklist, "체크리스트 없음.");
    }

    function setupPageTabs() {
      document.querySelectorAll(".page-tab").forEach(function(tab) {
        tab.addEventListener("click", function() {
          const target = tab.getAttribute("data-page-target");
          document.querySelectorAll(".page-tab").forEach(function(item) {
            item.classList.toggle("active", item === tab);
          });
          document.querySelectorAll(".page").forEach(function(page) {
            page.classList.toggle("active", page.getAttribute("data-page") === target);
          });
        });
      });
    }

    function render(data) {
      const brief = data.operatorBrief || {};
      const external = data.externalValidation || {};
      const latest = data.score.latest;
      const latestMetrics = latest && latest.metrics;
      const returnProfile = data.score.returnProfile || {};
      const latestReturn = returnProfile.latestPercent !== null && returnProfile.latestPercent !== undefined
        ? returnProfile.latestPercent
        : latestMetrics
          ? latestMetrics.netProfitPercent
          : null;
      const researchMode = data.researchMode || {};
      const strategyReview = data.strategyReview || {};
      const targetLabel = [researchMode.symbol, researchMode.timeframe ? researchMode.timeframe + "m" : null]
        .filter(Boolean)
        .join(" / ") || "-";
      text("subline", "상태 " + data.project.stateRoot + " / " + new Date(data.generatedAt).toLocaleTimeString());
      text("generatedAt", new Date(data.generatedAt).toLocaleTimeString());
      text("researchModeBadge", goalModeLabel(researchMode.goalMode));
      text("researchTargetLabel", targetLabel);
      text("researchObjectiveFocus", researchMode.objectiveFocus || "목표 profile을 기다리는 중입니다.");
      renderChipList("researchFocusChips", researchMode.strategyReviewFocus || []);
      renderRows("researchContextRows", [
        row([{ value: "target", className: "mono" }, { value: researchMode.targetId || "-", className: "mono" }]),
        row([{ value: "profile", className: "mono" }, { value: researchMode.goalProfileId || "-", className: "mono" }]),
        row([{ value: "branch bias", className: "mono" }, { value: researchMode.branchKindBias || "balanced", className: researchMode.branchKindBias ? "goodText" : "mutedText" }]),
        row([{ value: "criterion seed", className: "mono" }, { value: researchMode.criterionDirectiveSeed || "-", className: researchMode.criterionDirectiveSeed ? "goodText" : "mutedText" }]),
        row([{ value: "calibration", className: "mono" }, { value: calibrationPolicyLabel(researchMode.calibrationPolicy), className: "mono" }]),
        row([{ value: "suppressed branch", className: "mono" }, { value: (researchMode.suppressedBranchKinds || []).join(", ") || "-", className: (researchMode.suppressedBranchKinds || []).length ? "warnText" : "mutedText" }])
      ]);
      text("strategyReviewConfidence", strategyReview.confidence === null || strategyReview.confidence === undefined ? "대기" : fmt(strategyReview.confidence * 100, 0) + "%");
      text("strategyReviewDecision", reviewDecisionLabel(strategyReview.latestDecision));
      text("strategyReviewReason", strategyReview.reason || strategyReview.debateSummary || "아직 적용 가능한 전략 리뷰 지시가 없습니다.");
      renderChipList("strategyReviewFocus", strategyReview.nextMutationFocus || []);
      renderRows("strategyReviewRows", [
        row([{ value: "candidate", className: "mono" }, { value: strategyReview.latestCandidateId ? shortId(strategyReview.latestCandidateId) : "-", className: "mono" }]),
        row([{ value: "review mode", className: "mono" }, { value: strategyReview.reviewMode || "-", className: "mono" }]),
        row([{ value: "branch bias", className: "mono" }, { value: strategyReview.branchKindBias || "-", className: strategyReview.branchKindBias ? "goodText" : "mutedText" }]),
        row([{ value: "parent", className: "mono" }, { value: strategyReview.parentCandidateId ? shortId(strategyReview.parentCandidateId) : "-", className: "mono" }]),
        row([{ value: "required", className: "mono" }, { value: (strategyReview.requiredChanges || []).join(", ") || "-" }]),
        row([{ value: "validation", className: "mono" }, { value: (strategyReview.validationFocus || []).join(", ") || "-" }]),
        row([{ value: "forbidden", className: "mono" }, { value: (strategyReview.forbiddenPatterns || []).join(", ") || "-", className: (strategyReview.forbiddenPatterns || []).length ? "warnText" : "mutedText" }]),
        row([{ value: "suppressed family", className: "mono" }, { value: (strategyReview.suppressedFamilies || []).join(", ") || "-", className: (strategyReview.suppressedFamilies || []).length ? "badText" : "mutedText" }])
      ]);
      text("operatorMode", modeLabel(brief.mode));
      text("briefHeadline", brief.headline || "-");
      text("briefSummary", brief.summary || "-");
      renderOperatorEvidence(brief.evidence || []);
      renderSimpleList("nextActionList", brief.nextActions || [], "즉시 할 일 없음.");
      renderSimpleList("warningList", brief.warnings || [], "");
      renderCommands(brief.commands || []);
      const isAuto = external.autoProcessCalibration;
      const calibrationWorker = (data.runtime && data.runtime.calibrationWorker) || {};
      const workerEnabled = !!calibrationWorker.enabled;
      const workerRunning = !!calibrationWorker.running;
      const workerLastExit = calibrationWorker.lastExitCode === null || calibrationWorker.lastExitCode === undefined
        ? "-"
        : String(calibrationWorker.lastExitCode);
      const workerCheckedAt = calibrationWorker.heartbeat && calibrationWorker.heartbeat.lastCheckedAt
        ? new Date(calibrationWorker.heartbeat.lastCheckedAt).toLocaleTimeString()
        : "-";
      const workerMode = workerEnabled
        ? "병렬 워커"
        : isAuto
          ? "인라인"
          : "큐 보관";
      const workerLabel = workerRunning
        ? "실행 중 pid " + calibrationWorker.pid
        : workerEnabled
          ? "대기/중지"
          : "비활성";
      const toggleHtml = '<div class="toggle-wrapper"><div class="toss-toggle ' + (isAuto ? 'active' : '') + '"></div><span>' + (isAuto ? '자동 검증' : '수동') + '</span></div>';
      const elExt = document.getElementById("externalMode");
      if(elExt) elExt.innerHTML = toggleHtml;
      renderRows("externalRows", [
        row([{ value: "TV 큐 처리", className: "mono" }, { value: external.autoProcessCalibration ? "자동" : "수동", className: external.autoProcessCalibration ? "goodText" : "mutedText" }]),
        row([{ value: "처리 방식", className: "mono" }, { value: workerMode, className: workerEnabled ? "goodText" : isAuto ? "warnText" : "mutedText" }]),
        row([{ value: "TV 워커", className: "mono" }, { value: workerLabel, className: workerRunning ? "goodText" : workerEnabled ? "warnText" : "mutedText" }]),
        row([{ value: "워커 상태", className: "mono" }, { value: (calibrationWorker.status || "-") + " / exit " + workerLastExit + " / " + workerCheckedAt, className: workerRunning ? "goodText" : "mono" }]),
        row([{ value: "승격 검증 실행기", className: "mono" }, { value: external.promotionVerificationExecutor || "없음", className: external.promotionVerificationExecutor === "none" ? "mutedText" : "goodText" }]),
        row([{ value: "대기 후보", className: "mono" }, { value: String(external.pendingCount || 0), className: (external.pendingCount || 0) > 0 ? "warnText" : "goodText" }]),
        row([{ value: "대기 ID", className: "mono" }, { value: (external.pendingCandidateIds || []).map(shortId).join(", ") || "-" }])
      ]);
      text("latestScore", latest && latest.score !== null ? fmt(latest.score, 4) : "-");
      text("latestDecision", latest ? shortId(latest.candidateId) + " / " + decisionLabel(latest.decision) : "-");
      text("latestNet", pct(latestReturn));
      text("latestTrades", latestMetrics ? latestMetrics.totalTrades + "회 거래" : "-");
      text("bestReturn", pct(returnProfile.recentBestPercent));
      text("bestReturnId", returnProfile.recentBestCandidateId ? shortId(returnProfile.recentBestCandidateId) : "-");
      text("averageReturn", pct(returnProfile.recentAveragePercent));
      text("averageReturnDetail", "최근 로컬 후보 기준");
      toneValue("latestNet", latestReturn);
      toneValue("bestReturn", returnProfile.recentBestPercent);
      toneValue("averageReturn", returnProfile.recentAveragePercent);
      text("latestPf", latestMetrics ? fmt(latestMetrics.profitFactor, 2) : "-");
      text("latestDd", latestMetrics ? "최대 DD " + pct(latestMetrics.maxDrawdownPercent) : "-");
      text("championScore", data.score.activeChampion ? fmt(data.score.activeChampion.score, 4) : "-");
      text("championId", data.score.activeChampion ? shortId(data.score.activeChampion.candidateId) : "-");
      text("bestScore", data.score.bestEligible ? fmt(data.score.bestEligible.score, 4) : "-");
      text("bestId", data.score.bestEligible ? shortId(data.score.bestEligible.candidateId) : "-");
      text("healthValue", data.score.recentEligibleCount + "/10");
      text("healthDetail", "적격 " + data.score.recentEligibleCount + ", 희소 " + data.score.recentSparseProblemCount + ", 수리 " + data.score.recentPreflightRepairCount);
      const memory = data.runtime.nodeMemory || {};
      text("memoryValue", memory.rssMB ? fmt(memory.rssMB, 0) + "MB" : "-");
      text("memoryDetail", memory.heapUsedMB ? "heap " + fmt(memory.heapUsedMB, 0) + "MB / 비율 " + fmt(memory.rssToSystemRatio || 0, 4) : "-");
      text("storageValue", data.score.ledgerSizeMB !== undefined ? fmt(data.score.ledgerSizeMB, 1) + "MB" : "-");
      text("storageDetail", data.score.artifactSizeMB !== undefined ? "아티팩트 " + fmt(data.score.artifactSizeMB, 1) + "MB" : "-");
      text("chartMeta", "로컬 " + (data.trend || []).length + "개");
      text("improvementSummary", data.improvement.summary);
      renderChipList("nextFocus", data.improvement.nextFocus);
      text("paths", data.project.workspaceRoot);

      const verified = data.verifiedAutoresearch || {};
      text("verifiedCandidate", verified.verifiedPromotionCandidateId ? shortId(verified.verifiedPromotionCandidateId) : "-");
      renderRows("verifiedContractRows", [
        row([{ value: "검증 점수", className: "mono" }, { value: verified.verifiedPromotionScore === null || verified.verifiedPromotionScore === undefined ? "-" : fmt(verified.verifiedPromotionScore, 4), className: "mono" }]),
        row([{ value: "일치 상태", className: "mono" }, { value: queueStatusLabel(verified.parityStatus), className: verified.parityStatus === "matched" ? "goodText" : "warnText" }]),
        row([{ value: "워크포워드", className: "mono" }, { value: queueStatusLabel(verified.walkForwardStatus), className: verified.walkForwardStatus === "passed" ? "goodText" : "warnText" }]),
        row([{ value: "격리", className: "mono" }, { value: String(verified.quarantineCount || 0), className: (verified.quarantineCount || 0) > 0 ? "badText" : "goodText" }]),
        row([{ value: "단계", className: "mono" }, { value: summarizeCounts(verified.researchStageCounts) }]),
        row([{ value: "일치 집계", className: "mono" }, { value: summarizeCounts(verified.parityStatusCounts) }]),
        row([{ value: "WF 집계", className: "mono" }, { value: summarizeCounts(verified.walkForwardStatusCounts) }]),
        row([{ value: "시도 압력", className: "mono" }, { value: summarizeTrialPressure(verified.trialPressure) }])
      ]);
      const branchBudget = verified.branchBudget || {};
      const branchEntries = branchBudget.entries || [];
      text("branchBudgetMeta", branchBudget.totalBranches === undefined ? "0개 브랜치" : branchBudget.totalBranches + "개 브랜치");
      renderRows("branchBudgetRows", branchEntries.map(function(entry) {
        return row([
          { value: entry.branchKind || "-", className: "mono" },
          { value: entry.targetPct === undefined ? "-" : fmt(entry.targetPct, 0) + "%", className: "mono" },
          { value: entry.actualPct === undefined ? "-" : fmt(entry.actualPct, 1) + "% (" + (entry.actualCount || 0) + ")", className: "mono" },
          { value: entry.deficitPct === undefined ? "-" : fmt(entry.deficitPct, 1) + "%", className: entry.deficitPct > 0 ? "warnText" : "goodText" }
        ]);
      }));

      text("queueMeta", (external.pendingCount || 0) + "개 대기");
      const tvResults = external.tvResults || [];
      const tvMatched = tvResults.filter(function(item) { return item.parityStatus === "matched"; }).length;
      const tvMajorDrift = tvResults.filter(function(item) { return item.parityStatus === "major_drift"; }).length;
      const avgTvReturn = averageNumber(tvResults.map(function(item) { return item.tvReturnPercent; }));
      const avgNetDelta = averageNumber(tvResults.map(function(item) { return item.netProfitDelta; }));
      const avgTradeDelta = averageNumber(tvResults.map(function(item) { return item.tradeCountDelta; }));
      text("tvResultMeta", tvResults.length + "개");
      text("tvResultSummaryMeta", tvMatched + "일치 / " + tvMajorDrift + "큰 차이");
      renderTvResultChart(tvResults);
      renderRows("tvResultSummaryRows", [
        row([{ value: "최근 TV 수익률 평균", className: "mono" }, { value: pct(avgTvReturn), className: avgTvReturn !== null && avgTvReturn >= 0 ? "goodText" : "badText" }]),
        row([{ value: "평균 수익률 차이", className: "mono" }, { value: pct(avgNetDelta), className: avgNetDelta !== null && Math.abs(avgNetDelta) <= 2 ? "goodText" : "warnText" }]),
        row([{ value: "평균 거래수 차이", className: "mono" }, { value: avgTradeDelta === null ? "-" : fmt(avgTradeDelta, 1), className: avgTradeDelta !== null && Math.abs(avgTradeDelta) <= 25 ? "goodText" : "warnText" }]),
        row([{ value: "일치 / 큰 차이", className: "mono" }, { value: tvMatched + " / " + tvMajorDrift, className: tvMajorDrift > 0 ? "warnText" : "goodText" }])
      ]);
      renderRows("externalEventRows", (external.recentEvents || []).slice(0, 8).map(function(item) {
        return row([
          { value: shortId(item.candidateId), className: "mono" },
          { value: queueStatusLabel(item.status), className: item.status === "processed" ? "goodText" : item.status === "skipped" || item.status === "failed" ? "badText" : item.status === "deactivated" ? "mutedText" : "warnText" },
          { value: item.reason || item.tvDecision || item.parityStatus || "-" },
          { value: item.recordedAt ? new Date(item.recordedAt).toLocaleTimeString() : "-", className: "mono" }
        ]);
      }));

      const drift = external.latestDivergence;
      text("driftMeta", drift ? shortId(drift.candidateId) : "-");
      renderRows("driftRows", drift ? [
        row([{ value: "일치 상태", className: "mono" }, { value: queueStatusLabel(drift.parityStatus), className: drift.parityStatus === "major_drift" ? "badText" : "warnText" }]),
        row([{ value: "수익률 차이", className: "mono" }, { value: drift.netProfitDelta === null || drift.netProfitDelta === undefined ? "-" : pct(drift.netProfitDelta), className: Math.abs(drift.netProfitDelta || 0) > 10 ? "badText" : "warnText" }]),
        row([{ value: "거래수 차이", className: "mono" }, { value: drift.tradeCountDelta === null || drift.tradeCountDelta === undefined ? "-" : String(drift.tradeCountDelta), className: Math.abs(drift.tradeCountDelta || 0) > 100 ? "badText" : "warnText" }]),
        row([{ value: "조정 후 신뢰도", className: "mono" }, { value: drift.confidenceAfter === null || drift.confidenceAfter === undefined ? "-" : fmt(drift.confidenceAfter, 2), className: (drift.confidenceAfter || 0) < 0.8 ? "warnText" : "goodText" }]),
        row([{ value: "기록", className: "mono" }, { value: drift.recordedAt ? new Date(drift.recordedAt).toLocaleString() : "-" }])
      ] : [
        row([{ value: "상태", className: "mono" }, { value: "최근 차이 증거 없음" }])
      ]);

      const loopClass = data.runtime.running ? "pill good" : data.runtime.stopRequested ? "pill warn" : "pill bad";
      cls("loopStatus", loopClass);
      text("loopStatus", data.runtime.running ? "실행 중 pid " + data.runtime.pid : data.runtime.stopRequested ? "중지 요청됨" : "중지됨");
      cls("improvementStatus", "pill " + (data.improvement.status === "improving" ? "good" : data.improvement.status === "blocked" ? "bad" : "warn"));
      text("improvementStatus", improvementLabel(data.improvement.status));
      setRefreshStatus("good", "갱신 " + new Date().toLocaleTimeString());

      renderChart(data.trend || []);

      const strategy = data.bestStrategy;
      const recordStrategy = data.bestReturnStrategy || strategy;
      const recordCandidateId = returnProfile.recentBestCandidateId || (recordStrategy && recordStrategy.candidateId);
      const recordPoint = findCandidatePoint(data, recordCandidateId);
      const recordMetrics = recordPoint && recordPoint.metrics;
      text("recordCandidateId", recordCandidateId ? shortId(recordCandidateId) : "-");
      text("recordReturn", pct(returnProfile.recentBestPercent));
      text("recordSummary", recordCandidateId
        ? "최근 후보 구간에서 가장 높은 수익률을 낸 기록입니다. 이 페이지는 그 후보의 전략 구조와 최고 점수 전략을 분리해서 보여줍니다."
        : "최근 최고 수익률 후보가 아직 없습니다.");
      text("recordScore", recordPoint && recordPoint.score !== null ? fmt(recordPoint.score, 4) : "-");
      text("recordTrades", recordMetrics ? recordMetrics.totalTrades + "회 / PF " + fmt(recordMetrics.profitFactor, 2) : "-");
      text("recordDrawdown", recordMetrics ? "최대 DD " + pct(recordMetrics.maxDrawdownPercent) : "-");
      renderStrategyAnalysis("recordStrategy", recordStrategy);
      text("recordStrategySource", recordStrategy && recordStrategy.sourcePath ? recordStrategy.sourcePath : "-");
      renderStrategyAnalysis("strategy", strategy);
      renderRows("recordCompareRows", [
        row([{ value: "최근 최고 수익률", className: "mono" }, { value: (recordCandidateId ? shortId(recordCandidateId) + " / " : "") + pct(returnProfile.recentBestPercent), className: "goodText" }]),
        row([{ value: "최고 적격 점수", className: "mono" }, { value: data.score.bestEligible ? shortId(data.score.bestEligible.candidateId) + " / " + fmt(data.score.bestEligible.score, 4) : "-" }]),
        row([{ value: "최근 평균 수익률", className: "mono" }, { value: pct(returnProfile.recentAveragePercent) }]),
        row([{ value: "차이 해석", className: "mono" }, { value: recordCandidateId && data.score.bestEligible && recordCandidateId !== data.score.bestEligible.candidateId ? "수익률 최고와 점수 최고가 다릅니다. 수익률 후보는 낙폭/검증을 더 봐야 합니다." : "수익률 최고와 점수 최고가 같은 후보입니다." }])
      ]);
      text("explainStrategyId", recordStrategy ? shortId(recordStrategy.candidateId) : "-");
      renderExplanation(recordStrategy, recordPoint);
      text("explainParamMeta", recordStrategy ? shortId(recordStrategy.candidateId) : "-");
      renderRows("explainParamRows", recordStrategy ? Object.keys(recordStrategy.routeInputs || {}).map(function(key) {
        return row([{ value: key, className: "mono" }, { value: recordStrategy.routeInputs[key] === null ? "-" : String(recordStrategy.routeInputs[key]) }]);
      }) : []);

      const hyp = data.hypothesis;
      text("repairMode", hyp ? hyp.repairMode : "-");
      const hypEl = document.getElementById("hypothesisGrid");
      if (hypEl) {
        hypEl.innerHTML = "";
        [
          ["가설", hyp && hyp.hypothesis],
          ["기대 효과", hyp && hyp.expectedEffect],
          ["무효 조건", hyp && hyp.invalidIf],
          ["경로", hyp ? "선호 " + hyp.route.preferred.join(", ") + " / 변형 " + (hyp.route.variant || "-") : null],
          ["다음 방향", hyp && hyp.nextMutationDirection]
        ].forEach(function(pair) {
          const div = document.createElement("div");
          div.className = "hypothesis-row";
          div.innerHTML = '<div class="label"></div><p class="copy"></p>';
          div.querySelector(".label").textContent = pair[0];
          div.querySelector(".copy").textContent = pair[1] || "-";
          hypEl.appendChild(div);
        });
      }

      const topCandidates = (data.history && data.history.topCandidates) || [];
      const topWithTv = topCandidates.filter(function(item) { return item.tvReturnPercent !== null && item.tvReturnPercent !== undefined; });
      const topMajorDrift = topCandidates.filter(function(item) { return item.tvParityStatus === "major_drift"; });
      const topVerified = topCandidates.filter(function(item) { return item.verifiedEligible === true; });
      const topAvgReturn = averageNumber(topCandidates.map(function(item) { return item.localReturnPercent; }));
      const topBestReturn = topCandidates.reduce(function(best, item) {
        if (item.localReturnPercent === null || item.localReturnPercent === undefined) return best;
        if (!best || item.localReturnPercent > best.localReturnPercent) return item;
        return best;
      }, null);
      text("topCandidateMeta", topCandidates.length + "개");
      text("topCandidateSummaryMeta", topVerified.length + "승격 / " + topMajorDrift.length + "드리프트");
      renderRows("topCandidateRows", topCandidates.map(function(item) {
        return row([
          { value: item.rank === null || item.rank === undefined ? "-" : String(item.rank), className: "mono" },
          { value: shortId(item.candidateId), className: "mono" },
          { value: pct(item.localReturnPercent), className: item.localReturnPercent !== null && item.localReturnPercent >= 150 ? "goodText" : "mono" },
          { value: pct(item.tvReturnPercent), className: item.tvReturnPercent !== null && item.tvReturnPercent >= 150 ? "goodText" : "mono" },
          { value: item.score === null || item.score === undefined ? "-" : fmt(item.score, 4), className: "mono" },
          { value: item.riskLabel, className: item.riskTone === "good" ? "goodText" : item.riskTone === "bad" ? "badText" : item.riskTone === "warn" ? "warnText" : "mutedText" }
        ]);
      }));
      renderRows("topCandidateSummaryRows", [
        row([{ value: "상위 평균 로컬 수익률", className: "mono" }, { value: pct(topAvgReturn), className: topAvgReturn !== null && topAvgReturn >= 0 ? "goodText" : "badText" }]),
        row([{ value: "최고 로컬 수익률", className: "mono" }, { value: topBestReturn ? shortId(topBestReturn.candidateId) + " / " + pct(topBestReturn.localReturnPercent) : "-", className: "goodText" }]),
        row([{ value: "TV 결과 보유", className: "mono" }, { value: topWithTv.length + " / " + topCandidates.length, className: topWithTv.length > 0 ? "goodText" : "warnText" }]),
        row([{ value: "major_drift", className: "mono" }, { value: String(topMajorDrift.length), className: topMajorDrift.length > 0 ? "badText" : "goodText" }])
      ]);
      renderTopCandidateDetails(topCandidates);

      renderRows("candidateRows", (data.recentCandidates || []).map(function(item) {
        return row([
          { value: shortId(item.candidateId), className: "mono" },
          { value: item.score === null ? "-" : fmt(item.score, 4), className: "mono" },
          { value: item.metrics ? pct(item.metrics.netProfitPercent) : "-", className: "mono" },
          { value: item.metrics ? String(item.metrics.totalTrades) : "-", className: "mono" },
          { value: decisionLabel(item.decision), className: item.eligible ? "goodText" : "warnText" }
        ]);
      }));

      text("problemCount", String((data.failureMemory.recentProblems || []).length));
      renderRows("problemRows", (data.failureMemory.recentProblems || []).slice(-6).reverse().map(function(item) {
        return row([
          { value: item.iteration === null ? "-" : String(item.iteration), className: "mono" },
          { value: item.problemKind, className: "mono" },
          { value: item.diagnosis.slice(0, 96) }
        ]);
      }));

      text("repairCount", String((data.failureMemory.recentRepairs || []).length));
      renderRows("repairRows", (data.failureMemory.recentRepairs || []).slice(-6).reverse().map(function(item) {
        return row([
          { value: item.iteration === null ? "-" : String(item.iteration), className: "mono" },
          { value: item.repairKind, className: "mono" },
          { value: item.result + " / " + shortId(item.repairedCandidateId) }
        ]);
        }));
      }

    function summarizeCounts(counts) {
      const entries = Object.entries(counts || {}).filter(function(entry) { return Number(entry[1]) > 0; });
      if (entries.length === 0) return "-";
      return entries.map(function(entry) { return countKeyLabel(entry[0]) + ":" + entry[1]; }).join(" / ");
    }

    function summarizeTrialPressure(pressure) {
      if (!pressure) return "-";
      const total = pressure.totalCandidatesTried === undefined ? "-" : pressure.totalCandidatesTried;
      const family = pressure.familyTrials === undefined ? "-" : pressure.familyTrials;
      const threshold = pressure.minimumRequiredScore === undefined || pressure.minimumRequiredScore === null
        ? "-"
        : fmt(pressure.minimumRequiredScore, 2);
      return "전체 " + total + " / 계열 " + family + " / 최소 " + threshold;
    }

    function setRefreshStatus(tone, value) {
      const className = tone === "bad" ? "pill bad" : tone === "warn" ? "pill warn" : "pill good";
      cls("refreshStatus", className);
      text("refreshStatus", value);
    }

    function scheduleNextLoad(delayMs) {
      if (state.timer) {
        clearTimeout(state.timer);
      }
      state.timer = setTimeout(load, delayMs);
    }

    async function load() {
      if (state.loading) {
        scheduleNextLoad(1000);
        return;
      }
      state.loading = true;
      const controller = new AbortController();
      const timeout = setTimeout(function() {
        controller.abort();
      }, state.requestTimeoutMs);
      try {
        setRefreshStatus("warn", "갱신 중 " + new Date().toLocaleTimeString());
        const response = await fetch("/api/status?ts=" + Date.now(), {
          cache: "no-store",
          signal: controller.signal
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const data = await response.json();
        state.failures = 0;
        state.lastDataGeneratedAt = data.generatedAt || state.lastDataGeneratedAt;
        render(data);
      } catch (error) {
        state.failures += 1;
        setRefreshStatus("bad", "갱신 실패 " + state.failures + "회");
        console.error(error);
      } finally {
        clearTimeout(timeout);
        state.loading = false;
        scheduleNextLoad(state.refreshIntervalMs);
      }
    }

    window.addEventListener("focus", function() {
      load();
    });
    document.addEventListener("visibilitychange", function() {
      if (!document.hidden) load();
    });
    window.addEventListener("online", function() {
      load();
    });

    setupPageTabs();
    load();
  </script>
</body>
</html>`;
}
