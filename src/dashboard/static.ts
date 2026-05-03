export function renderDashboardHtml(): string {
  return String.raw`<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AF 로컬 루프 대시보드</title>
  <style>
    :root {
      --paper: #f6f7f9;
      --ink: #111827;
      --muted: #64748b;
      --line: #cbd5e1;
      --panel: #ffffff;
      --accent: #2563eb;
      --good: #0f766e;
      --warn: #b45309;
      --bad: #be123c;
      --blue: #1d4ed8;
      --mono: "Cascadia Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
      --body: "Aptos", "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--body);
      letter-spacing: 0;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.18;
      background-image:
        repeating-linear-gradient(0deg, transparent 0 23px, rgba(15,23,42,0.035) 24px),
        repeating-linear-gradient(90deg, transparent 0 47px, rgba(15,23,42,0.026) 48px);
    }

    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 58px minmax(0, 1fr);
    }

    .rail {
      background: var(--ink);
      color: var(--paper);
      display: flex;
      align-items: center;
      justify-content: center;
      border-right: 3px solid var(--good);
    }

    .rail span {
      writing-mode: vertical-rl;
      transform: rotate(180deg);
      font-family: var(--mono);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    main {
      width: min(1680px, 100%);
      margin: 0 auto;
      padding: 22px;
      min-width: 0;
    }

    header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      padding-bottom: 18px;
      border-bottom: 2px solid var(--ink);
    }

    h1 {
      margin: 0;
      font-family: var(--mono);
      font-size: clamp(24px, 4vw, 54px);
      line-height: 0.95;
      text-transform: uppercase;
    }

    .subline {
      margin-top: 8px;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 13px;
      overflow-wrap: anywhere;
    }

    .status-strip {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .pill {
      border: 1px solid var(--ink);
      padding: 6px 9px;
      font-family: var(--mono);
      font-size: 12px;
      background: var(--panel);
      white-space: nowrap;
    }

    .pill.good { color: var(--good); border-color: var(--good); }
    .pill.warn { color: var(--warn); border-color: var(--warn); }
    .pill.bad { color: var(--bad); border-color: var(--bad); }

    .grid {
      display: grid;
      grid-template-columns: 1.35fr 0.85fr;
      gap: 18px;
      margin-top: 18px;
      min-width: 0;
    }

    .brief-band {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr);
      gap: 18px;
      margin-top: 18px;
      min-width: 0;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 10px;
      margin-top: 18px;
    }

    .metric,
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: 3px 3px 0 var(--ink);
    }

    .metric {
      min-height: 96px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .label {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
      text-transform: uppercase;
    }

    .value {
      font-family: var(--mono);
      font-size: clamp(20px, 2.2vw, 34px);
      line-height: 1;
    }

    .delta {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .panel {
      padding: 16px;
      min-width: 0;
    }

    .brief-title {
      margin: 0 0 8px;
      font-family: var(--mono);
      font-size: 20px;
      line-height: 1.15;
    }

    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 14px;
    }

    .evidence {
      border: 1px solid var(--line);
      background: #f8fafc;
      padding: 9px;
      min-height: 68px;
    }

    .evidence.good { border-left: 4px solid var(--good); }
    .evidence.watch { border-left: 4px solid var(--warn); }
    .evidence.bad { border-left: 4px solid var(--bad); }
    .evidence.neutral { border-left: 4px solid var(--blue); }

    .evidence .label {
      display: block;
      margin-bottom: 6px;
    }

    .evidence .ev-value {
      font-family: var(--mono);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .action-list,
    .warning-list {
      margin: 12px 0 0;
      padding-left: 18px;
      line-height: 1.45;
      font-size: 13px;
    }

    .warning-list {
      color: var(--bad);
    }

    .command-list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }

    .command {
      border: 1px solid var(--line);
      background: #f8fafc;
      padding: 9px;
    }

    .command code {
      display: block;
      margin-top: 5px;
      color: var(--ink);
      font-family: var(--mono);
      font-size: 11px;
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .panel h2 {
      margin: 0 0 12px;
      font-family: var(--mono);
      font-size: 14px;
      text-transform: uppercase;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
    }

    .chart {
      width: 100%;
      height: 270px;
      display: block;
      border: 1px solid var(--line);
      background: #fffdf7;
    }

    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 18px;
      min-width: 0;
    }

    .stack {
      display: grid;
      gap: 18px;
      min-width: 0;
    }

    .copy {
      margin: 0;
      color: var(--ink);
      line-height: 1.55;
      font-size: 14px;
      overflow-wrap: anywhere;
    }

    .small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .feature-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }

    .chip {
      font-family: var(--mono);
      font-size: 11px;
      border: 1px solid var(--line);
      padding: 5px 7px;
      background: #fffdf7;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      table-layout: fixed;
    }

    th, td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      overflow-wrap: anywhere;
    }

    th {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
      text-transform: uppercase;
    }

    td.mono { font-family: var(--mono); }
    .goodText { color: var(--good); }
    .warnText { color: var(--warn); }
    .badText { color: var(--bad); }

    .hypothesis-grid {
      display: grid;
      gap: 10px;
    }

    .hypothesis-row {
      border-left: 4px solid var(--accent);
      padding-left: 10px;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .footer {
      margin-top: 18px;
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .footer span {
      min-width: 0;
      overflow-wrap: anywhere;
    }

    @media (max-width: 1100px) {
      .shell { grid-template-columns: 1fr; }
      .rail { display: none; }
      .grid, .two-col, .brief-band { grid-template-columns: minmax(0, 1fr); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .evidence-grid { grid-template-columns: 1fr; }
      header { grid-template-columns: 1fr; }
      .status-strip { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="rail"><span>AF 검증 / QQQ 120분</span></aside>
    <main>
      <header>
        <div>
          <h1>자율 연구 대시보드</h1>
          <div class="subline" id="subline">로컬 상태를 불러오는 중...</div>
        </div>
        <div class="status-strip">
          <span class="pill" id="loopStatus">루프</span>
          <span class="pill" id="improvementStatus">상태</span>
          <span class="pill" id="refreshStatus">갱신</span>
        </div>
      </header>

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

      <section class="two-col">
        <div class="panel">
          <h2><span>최고 전략 분석</span><span id="strategyId">-</span></h2>
          <p class="copy" id="strategySummary">-</p>
          <div class="feature-list" id="strategyFeatures"></div>
          <table style="margin-top: 12px">
            <tbody id="strategyTable"></tbody>
          </table>
        </div>
        <div class="panel">
          <h2><span>현재 가설</span><span id="repairMode">-</span></h2>
          <div class="hypothesis-grid" id="hypothesisGrid"></div>
        </div>
      </section>

      <section class="grid">
        <div class="panel">
          <h2><span>최근 후보</span><span>tail window</span></h2>
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
        grid.setAttribute("stroke", "#c9c2b4");
        grid.setAttribute("stroke-width", "1");
        svg.appendChild(grid);
      }

      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "#d9472f");
      poly.setAttribute("stroke-width", "3");
      poly.setAttribute("points", linePoints.map(function(pt) { return pt.x + "," + pt.y; }).join(" "));
      svg.appendChild(poly);

      linePoints.forEach(function(pt) {
        const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        dot.setAttribute("cx", String(pt.x));
        dot.setAttribute("cy", String(pt.y));
        dot.setAttribute("r", pt.p.eligible ? "4" : "3");
        dot.setAttribute("fill", pt.p.eligible ? "#13795b" : "#22577a");
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
      text("externalMode", external.autoProcessCalibration ? "자동 검증" : "수동");
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
      text("strategyId", strategy ? shortId(strategy.candidateId) : "-");
      text("strategySummary", strategy ? (strategy.summary || strategy.title || "요약 없음") : "-");
      renderChipList("strategyFeatures", strategy ? strategy.features : []);
      const strategyRows = [];
      if (strategy) {
        strategyRows.push(row([{ value: "진입", className: "mono" }, { value: strategy.entryShape }]));
        strategyRows.push(row([{ value: "청산", className: "mono" }, { value: strategy.exitShape }]));
        strategyRows.push(row([{ value: "리스크", className: "mono" }, { value: strategy.riskShape }]));
        Object.keys(strategy.routeInputs || {}).forEach(function(key) {
          strategyRows.push(row([{ value: key, className: "mono" }, { value: strategy.routeInputs[key] === null ? "-" : String(strategy.routeInputs[key]) }]));
        });
      }
      renderRows("strategyTable", strategyRows);

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

    load();
    state.timer = setInterval(load, 8000);
  </script>
</body>
</html>`;
}
