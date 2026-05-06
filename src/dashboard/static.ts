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
      --good: #f04452;
      --warn: #ffb020;
      --bad: #3182f6;
      --positive: #f04452;
      --negative: #3182f6;
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
    .pill.good { color: var(--good); background: var(--soft-red); }
    .pill.warn { color: #b7791f; background: var(--soft-warn); }
    .pill.bad { color: var(--bad); background: var(--soft-blue); }

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

    .evidence.good { background: var(--soft-red); }
    .evidence.watch { background: var(--soft-warn); }
    .evidence.bad { background: var(--soft-blue); }
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
      .grid, .two-col, .brief-band { grid-template-columns: minmax(0, 1fr); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 560px) {
      main { padding: 20px 16px 40px; }
      .metrics { grid-template-columns: minmax(0, 1fr); }
      .evidence-grid { grid-template-columns: 1fr; }
      .page-nav { position: sticky; top: 0; z-index: 2; }
      .page-tab { flex: 1 1 auto; font-size: 13px; padding: 8px 10px; }
      .record-stat-grid { grid-template-columns: minmax(0, 1fr); }
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
      background: var(--blue, #3182f6);
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
            <h2><span>최근 점수 추적</span><span id="chartMeta">-</span></h2>
            <svg class="chart" id="scoreChart" role="img" aria-label="최근 점수 추세"></svg>
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
    const state = { timer: null };

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
        failed: "실패"
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
      text("subline", "상태 " + data.project.stateRoot + " / " + new Date(data.generatedAt).toLocaleTimeString());
      text("generatedAt", new Date(data.generatedAt).toLocaleTimeString());
      text("operatorMode", modeLabel(brief.mode));
      text("briefHeadline", brief.headline || "-");
      text("briefSummary", brief.summary || "-");
      renderOperatorEvidence(brief.evidence || []);
      renderSimpleList("nextActionList", brief.nextActions || [], "즉시 할 일 없음.");
      renderSimpleList("warningList", brief.warnings || [], "");
      renderCommands(brief.commands || []);
      const isAuto = external.autoProcessCalibration;
      const toggleHtml = '<div class="toggle-wrapper"><div class="toss-toggle ' + (isAuto ? 'active' : '') + '"></div><span>' + (isAuto ? '자동 검증' : '수동') + '</span></div>';
      const elExt = document.getElementById("externalMode");
      if(elExt) elExt.innerHTML = toggleHtml;
      renderRows("externalRows", [
        row([{ value: "TV 큐 처리", className: "mono" }, { value: external.autoProcessCalibration ? "자동" : "수동", className: external.autoProcessCalibration ? "warnText" : "goodText" }]),
        row([{ value: "승격 검증 실행기", className: "mono" }, { value: external.promotionVerificationExecutor || "없음", className: external.promotionVerificationExecutor === "none" ? "goodText" : "warnText" }]),
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
      text("chartMeta", (data.trend || []).length + "개");
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
      renderRows("externalEventRows", (external.recentEvents || []).slice(0, 8).map(function(item) {
        return row([
          { value: shortId(item.candidateId), className: "mono" },
          { value: queueStatusLabel(item.status), className: item.status === "processed" ? "goodText" : item.status === "skipped" || item.status === "failed" ? "badText" : "warnText" },
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
      text("refreshStatus", "갱신 " + new Date().toLocaleTimeString());

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

    async function load() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const data = await response.json();
        render(data);
      } catch (error) {
        cls("refreshStatus", "pill bad");
        text("refreshStatus", "갱신 실패");
        console.error(error);
      }
    }

    setupPageTabs();
    load();
    state.timer = setInterval(load, 8000);
  </script>
</body>
</html>`;
}
