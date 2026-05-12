export const DASHBOARD_HEADER = String.raw`      <header>
        <div>
          <h1>AF 자율 투자 연구</h1>
          <div class="subline" id="subline">로컬 상태를 불러오는 중...</div>
        </div>
        <div class="status-strip">
          <span class="pill" id="loopStatus">루프</span>
          <span class="pill" id="improvementStatus">상태</span>
          <span class="pill" id="refreshStatus">갱신</span>
        </div>
      </header>`;

export const DASHBOARD_NAV = String.raw`      <nav class="page-nav" aria-label="대시보드 페이지">
        <button class="page-tab active" type="button" data-page-target="overview">요약</button>
        <button class="page-tab" type="button" data-page-target="strategy">최고 기록</button>
        <button class="page-tab" type="button" data-page-target="explain">쉬운 해설</button>
        <button class="page-tab" type="button" data-page-target="validation">검증</button>
        <button class="page-tab" type="button" data-page-target="history">기록</button>
      </nav>`;

export const DASHBOARD_CONTEXT_SECTION = String.raw`      <section class="context-band" aria-label="현재 연구 컨텍스트">
        <div class="panel">
          <h2><span>연구 컨텍스트</span><span id="researchModeBadge">-</span></h2>
          <div class="context-title" id="researchTargetLabel">-</div>
          <div class="mode-picker">
            <label for="trainingModeSelect">Training mode</label>
            <select id="trainingModeSelect" aria-label="Training mode"></select>
          </div>
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

`;

export const DASHBOARD_OVERVIEW_PAGE = String.raw`      <section class="page active" data-page="overview">
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

`;

export const DASHBOARD_STRATEGY_PAGE = String.raw`      <section class="page" data-page="strategy">
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

`;

export const DASHBOARD_EXPLANATION_PAGE = String.raw`      <section class="page" data-page="explain">
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

`;

export const DASHBOARD_VALIDATION_PAGE = String.raw`      <section class="page" data-page="validation">
        <section class="grid">
          <div class="panel">
            <h2><span>Local Validation 결과</span><span id="tvResultMeta">-</span></h2>
            <svg class="chart" id="tvResultChart" role="img" aria-label="Local Validation 결과"></svg>
          </div>
          <div class="panel">
            <h2><span>Local Validation 요약</span><span id="tvResultSummaryMeta">-</span></h2>
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
            <h2><span>로컬 승격 큐</span><span id="queueMeta">-</span></h2>
            <table>
              <thead><tr><th>ID</th><th>상태</th><th>사유</th><th>기록</th></tr></thead>
              <tbody id="externalEventRows"></tbody>
            </table>
          </div>
          <div class="panel">
            <h2><span>최신 로컬 검증 차이</span><span id="driftMeta">-</span></h2>
            <table>
              <tbody id="driftRows"></tbody>
            </table>
          </div>
        </section>
      </section>

`;

export const DASHBOARD_HISTORY_PAGE = String.raw`      <section class="page" data-page="history">
        <section class="grid">
          <div class="panel">
            <h2><span>상위 20개 후보 분석</span><span id="topCandidateMeta">-</span></h2>
            <table class="leaderboard-table">
              <thead><tr><th>순위</th><th>ID</th><th>로컬 수익률</th><th>검증 수익률</th><th>점수</th><th>검증</th></tr></thead>
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

`;

export const DASHBOARD_FOOTER = String.raw`      <div class="footer">
        <span id="paths">로컬 파일만 사용</span>
        <span>자동 갱신: 8초</span>
      </div>
`;
