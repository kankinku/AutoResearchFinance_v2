export const DASHBOARD_STYLES = String.raw`
    :root {
      --paper: #f6f7f9;
      --ink: #151922;
      --muted: #647183;
      --line: #dfe4ea;
      --panel: #ffffff;
      --accent: #1e40af;
      --good: #008f5d;
      --warn: #b7791f;
      --bad: #d92d3d;
      --positive: #d92d3d;
      --negative: #2563eb;
      --soft-good: #e7f8ef;
      --soft-red: #fdecee;
      --soft-blue: #eaf2ff;
      --soft-gray: #eef2f6;
      --soft-warn: #fff5dd;
      --display: "Pretendard Variable", "Pretendard", "Noto Sans KR", "SUIT", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      --body: "Pretendard Variable", "Pretendard", "Noto Sans KR", "SUIT", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      --mono: "D2Coding", "Cascadia Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
    }

    * { box-sizing: border-box; }
    html {
      font-size: 15px;
      text-size-adjust: 100%;
      word-break: keep-all;
    }

    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--body);
      font-size: 15px;
      line-height: 1.65;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      letter-spacing: 0;
    }

    .shell {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .rail { display: none; }

    main {
      width: min(1280px, 100%);
      margin: 0 auto;
      padding: 34px 28px 64px;
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
      font-family: var(--display);
      font-size: 34px;
      font-weight: 800;
      line-height: 1.25;
      letter-spacing: 0;
    }

    .subline {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      font-weight: 600;
      overflow-wrap: anywhere;
      word-break: break-all;
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
      line-height: 1.35;
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
      line-height: 1.35;
      background: var(--soft-gray);
      color: #4e5968;
      white-space: nowrap;
    }
    .pill.good { color: var(--good); background: var(--soft-good); }
    .pill.warn { color: #b7791f; background: var(--soft-warn); }
    .pill.bad { color: var(--bad); background: var(--soft-red); }

    .grid, .two-col, .brief-band {
      display: grid;
      gap: 18px;
      margin-top: 16px;
      min-width: 0;
    }
    .grid { grid-template-columns: 1.35fr 0.85fr; }
    .brief-band { grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr); }
    .two-col { grid-template-columns: 1fr 1fr; }
    .stack { display: grid; gap: 16px; min-width: 0; }

    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 18px;
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
      font-weight: 700;
      line-height: 1.45;
      letter-spacing: 0;
    }

    .value {
      font-family: var(--display);
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 0;
      line-height: 1.15;
      margin: 8px 0;
      font-variant-numeric: tabular-nums;
    }

    .value.positive { color: var(--positive); }
    .value.negative { color: var(--negative); }

    .delta {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      line-height: 1.45;
      overflow-wrap: anywhere;
      word-break: keep-all;
    }

    .panel h2 {
      margin: 0 0 20px;
      font-size: 18px;
      font-weight: 800;
      line-height: 1.4;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: var(--ink);
    }

    .panel h2 > span:last-child {
      font-size: 13px;
      font-weight: 600;
      line-height: 1.35;
      color: var(--muted);
      background: var(--soft-gray);
      padding: 6px 10px;
      border-radius: 8px;
    }

    .brief-title {
      margin: 0 0 12px;
      font-size: 22px;
      font-weight: 800;
      line-height: 1.4;
      letter-spacing: 0;
    }

    .copy {
      margin: 0;
      color: #333d4b;
      line-height: 1.75;
      font-size: 15px;
      overflow-wrap: anywhere;
      font-weight: 500;
    }

    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 10px;
      margin-top: 20px;
    }

    .evidence {
      background: var(--soft-gray);
      border-radius: 12px;
      padding: 16px;
      min-height: 84px;
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
      line-height: 1.45;
      font-weight: 700;
      color: var(--ink);
      overflow-wrap: anywhere;
    }
    
    .evidence.good .ev-value { color: var(--good); }
    .evidence.bad .ev-value { color: var(--bad); }

    .action-list, .warning-list {
      margin: 16px 0 0;
      padding-left: 20px;
      line-height: 1.75;
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
      line-height: 1.55;
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
      gap: 18px;
      margin: 0 0 18px;
      min-width: 0;
    }

    .context-title {
      font-family: var(--display);
      font-size: 30px;
      font-weight: 800;
      line-height: 1.25;
      margin: 4px 0 12px;
      overflow-wrap: anywhere;
      font-variant-numeric: tabular-nums;
    }

    .mode-picker {
      display: grid;
      gap: 6px;
      margin: 8px 0 14px;
      max-width: 420px;
    }

    .mode-picker label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      line-height: 1.35;
    }

    .mode-picker select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      font-family: var(--body);
      font-size: 14px;
      font-weight: 800;
      line-height: 1.35;
      padding: 8px 10px;
    }

    .context-rows {
      margin-top: 16px;
    }

    .chip {
      font-size: 13px;
      font-weight: 600;
      line-height: 1.45;
      border-radius: 8px;
      padding: 7px 10px;
      background: var(--soft-gray);
      color: #4e5968;
      min-width: 0;
      overflow-wrap: anywhere;
      word-break: keep-all;
    }

    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
      line-height: 1.55;
      table-layout: fixed;
    }

    th, td {
      text-align: left;
      padding: 14px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: keep-all;
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
      line-height: 1;
    }

    .candidate-name {
      margin: 0 0 6px;
      font-family: var(--mono);
      font-size: 16px;
      font-weight: 800;
      line-height: 1.35;
      color: var(--ink);
      overflow-wrap: anywhere;
    }

    .risk-badge {
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.3;
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
      line-height: 1.35;
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
      line-height: 1.65;
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
      line-height: 1.55;
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
      h1 { font-size: 28px; }
      .value { font-size: 30px; }
      .context-title { font-size: 26px; }
      .record-stat-grid { grid-template-columns: minmax(0, 1fr); }
      .candidate-detail-head,
      .detail-columns,
      .detail-metrics { grid-template-columns: minmax(0, 1fr); }
      .panel { padding: 20px; }
      .metric { padding: 20px; min-height: auto; }
      table { display: block; overflow-x: auto; }
      th, td { white-space: normal; }
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
`;
