const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const fmt = (value) => value == null ? "—" : Number(value).toLocaleString("ko-KR", {maximumFractionDigits:2});
const fmtPct = (value) => value == null ? "—" : `${(Number(value) * 100).toLocaleString("ko-KR", {maximumFractionDigits:1})}%`;
const formatDate = (value) => { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", {dateStyle:"medium", timeStyle:"short"}); };
const statusText = (value) => value ? statusLabel(value) : "확인 필요";
let payload = {runs:[], generations:[], capabilities:[], summary:{}, research:{}};
let selectedGeneration = null;
// generation_summary is the user-facing unit; run IDs stay in diagnostics.

function setText(id, value) { const node = $(id); if (node) node.textContent = value; }
function formatElapsed(seconds) {
  if (seconds == null) return "확인 불가";
  const total = Math.max(0, Math.floor(Number(seconds)));
  const hours = Math.floor(total / 3600); const minutes = Math.floor((total % 3600) / 60); const secs = total % 60;
  if (hours) return `${hours}시간 ${minutes}분`;
  if (minutes) return `${minutes}분 ${secs}초`;
  return `${secs}초`;
}
function stateClass(status) { return ["SURVIVOR", "SUCCEEDED", "PASS", "VALIDATED"].includes(String(status).toUpperCase()) ? "positive" : "warning"; }

function renderResearch(research) {
  const requested = Number(research.requested_generations || 0); const completed = Number(research.completed_generations || 0);
  const running = String(research.status || "").toUpperCase() === "RUNNING";
  const progress = requested > 0 ? Math.min(completed / requested, 1) : 0;
  setText("research-status", statusText(research.status));
  setText("current-generation", running ? (research.current_generation || completed + 1) : (completed || "—"));
  setText("generation-progress-copy", requested ? `${completed} / ${requested}세대 완료` : "요청 세대 정보 없음");
  setText("research-progress-text", requested ? `${(progress * 100).toFixed(1)}%` : "—");
  $("research-progress-bar").style.width = `${progress * 100}%`;
  setText("current-phase", `현재 단계: ${research.current_phase || "확인 불가"}`);
  setText("phase-elapsed", formatElapsed(research.phase_elapsed_seconds));
  setText("last-generation", research.last_completed_generation ? `마지막 완료 ${research.last_completed_generation}세대` : "완료된 세대 없음");
  setText("research-connection", running ? "연결됨" : (research.status ? statusText(research.status) : "대기"));
}

function renderSummary(summary) {
  setText("best-strategy-cagr", fmtPct(summary.best_strategy_cagr)); setText("best-qqq-cagr", fmtPct(summary.best_qqq_cagr));
  setText("best-qqq-delta", fmtPct(summary.best_qqq_cagr_delta)); setText("best-total-return", fmtPct(summary.best_total_return));
  setText("best-drawdown", fmtPct(summary.best_max_drawdown)); setText("best-sharpe", fmt(summary.best_sharpe));
  setText("best-trades", summary.best_trade_count == null ? "—" : `${fmt(summary.best_trade_count)}회`); setText("risk-rate", fmtPct(summary.risk_compliance_rate));
  setText("generation-count", `세대 ${summary.generation_count || 0}개 · 통과 ${summary.passing_generation_count || 0}개`);
  setText("ledger-count", `${summary.total_runs || 0}회`);
}

function barRow(generation, label, value, max, className) {
  const width = value == null || !max ? 0 : Math.min(100, Math.abs(Number(value)) / max * 100);
  return `<div class="performance-row"><span class="performance-generation">${generation}세대</span><span class="performance-label">${label}</span><span class="metric-bar ${className}" style="width:${width}%"></span><strong>${value == null ? "—" : fmtPct(value)}</strong></div>`;
}
function renderCharts(generations) {
  const sorted = [...generations].sort((a, b) => a.generation - b.generation); const cagrValues = sorted.flatMap((item) => [item.best_strategy_cagr, item.best_qqq_cagr]).filter((value) => value != null).map(Math.abs); const scores = sorted.map((item) => item.best_score).filter((value) => value != null).map(Math.abs);
  const cagrMax = Math.max(...cagrValues, 0.01); const scoreMax = Math.max(...scores, 0.01);
  $("cagr-chart").innerHTML = sorted.map((item) => `<div class="performance-group"><div class="performance-row-title">${item.generation}세대</div>${barRow(item.generation, "전략", item.best_strategy_cagr, cagrMax, "bar-strategy")}${barRow(item.generation, "QQQ", item.best_qqq_cagr, cagrMax, "bar-benchmark")}</div>`).join("") || `<p class="empty-copy">아직 평가 전</p>`;
  $("score-chart").innerHTML = sorted.map((item) => { const width = item.best_score == null ? 0 : Math.min(100, Math.abs(Number(item.best_score)) / scoreMax * 100); return `<div class="performance-row"><span class="performance-generation">${item.generation}세대</span><span class="metric-bar bar-score" style="width:${width}%"></span><strong>${fmt(item.best_score)}</strong></div>`; }).join("") || `<p class="empty-copy">아직 평가 전</p>`;
}

function renderGenerations(generations) {
  const sorted = [...generations].sort((a, b) => b.generation - a.generation); const select = $("generation-select");
  select.innerHTML = sorted.map((item) => `<option value="${item.generation}">${item.generation}세대 · 최고 후보</option>`).join("");
  if (selectedGeneration == null || !sorted.some((item) => item.generation === selectedGeneration)) selectedGeneration = sorted[0]?.generation ?? null;
  if (selectedGeneration != null) select.value = String(selectedGeneration);
  $("generation-summary-table").innerHTML = sorted.map((item) => `<tr data-generation="${item.generation}" class="generation-row ${item.generation === selectedGeneration ? "selected" : ""}"><td><button class="generation-link" type="button" data-generation="${item.generation}">${item.generation}세대</button></td><td>${fmt(item.candidate_count)}개</td><td>${fmtPct(item.best_strategy_cagr)}</td><td>${fmtPct(item.best_qqq_cagr)}</td><td>${fmtPct(item.best_qqq_cagr_delta)}</td><td>${fmt(item.best_score)}</td><td>${item.best_trade_count == null ? "—" : `${fmt(item.best_trade_count)}회`}</td><td><span class="badge ${stateClass(item.status)}">${escapeHtml(statusText(item.status))}</span></td></tr>`).join("") || `<tr><td colspan="8" class="muted">아직 평가 전</td></tr>`;
  document.querySelectorAll(".generation-link").forEach((button) => button.addEventListener("click", () => { selectedGeneration = Number(button.dataset.generation); renderGenerations(payload.generations); renderSelectedGeneration(); }));
  renderCharts(sorted);
}

function featureRows(item, summary) {
  let features = item?.feature_lineage || [];
  if (!features.length) features = summary?.proposal?.feature_selections || [];
  if (!features.length) return `<tr><td colspan="6" class="muted">이 세대에는 인디케이터 lineage가 저장되지 않았습니다.</td></tr>`;
  return features.map((feature) => `<tr><td><strong>${escapeHtml(feature.alias || feature.feature_id || "—")}</strong><br><span class="muted">${escapeHtml(feature.feature_id || "—")}</span></td><td>${escapeHtml((feature.inputs || []).join(", ") || "전략 기본 자료")}</td><td>${escapeHtml(timeframeLabel(feature.timeframe || "1d"))}</td><td>${fmt(feature.lag_bars)} / ${fmt(feature.lookback)}</td><td>${escapeHtml(JSON.stringify(feature.parameters || {}))}</td><td>${escapeHtml(statusText(feature.status || "REGISTERED"))}</td></tr>`).join("");
}
function yearlyRows(item) {
  const rows = item?.yearly_metrics || [];
  if (!rows.length) return `<tr><td colspan="5" class="muted">연도별 기록 없음</td></tr>`;
  return rows.map((year) => { const complete = Boolean(year.complete); const trades = Number(year.trade_count || 0); const passed = complete && trades > 30; return `<tr><td>${escapeHtml(year.year)}${complete ? "" : " · 진행 중"}</td><td>${fmt(year.trade_count)}</td><td>${fmtPct(year.total_return)}</td><td>${fmtPct(year.max_drawdown)}</td><td><span class="gate-${passed ? "pass" : complete ? "fail" : "pending"}">${passed ? "통과" : complete ? "탈락" : "판정 제외"}</span></td></tr>`; }).join("");
}
function renderProposal(proposal) {
  if (!proposal || !Object.keys(proposal).length) return "이 세대의 제안 기록 없음";
  const selections = proposal.feature_selections || []; const operations = proposal.operations || [];
  return `<dl class="proposal-list"><dt>연구 모드</dt><dd>${escapeHtml(proposal.mode || "—")}</dd><dt>제안 상태</dt><dd>${escapeHtml(proposal.intent_status || proposal.status || "—")}</dd><dt>부모 전략</dt><dd>${escapeHtml((proposal.parent_ids || []).join(", ") || "—")}</dd><dt>선택 인디케이터</dt><dd>${selections.length ? selections.map((item) => escapeHtml(item.alias || item.feature_id || "—")).join(", ") : "없음"}</dd><dt>변경 작업</dt><dd>${operations.length ? operations.map((item) => escapeHtml(item.op || item)).join(", ") : "없음"}</dd></dl>${proposal.intent_error ? `<p class="warning-copy">검증 참고: ${escapeHtml(proposal.intent_error)}</p>` : ""}`;
}
function renderDiagnostics(item) {
  if (!item) return "";
  const gates = item.gates || []; const folds = item.validation_folds || [];
  const gateTable = gates.length ? `<table><caption>평가 gate 상세</caption><thead><tr><th>gate</th><th>실제값</th><th>기준</th><th>판정</th></tr></thead><tbody>${gates.map((gate) => `<tr><td>${escapeHtml(gate.name || gate.id || "—")}</td><td>${fmt(gate.actual)}</td><td>${fmt(gate.threshold)}</td><td>${gate.passed ? "통과" : "탈락"}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">gate 기록 없음</p>`;
  const foldTable = folds.length ? `<table><caption>검증 구간별 결과</caption><thead><tr><th>구간</th><th>전략 CAGR</th><th>QQQ CAGR</th><th>QQQ 대비</th><th>판정</th></tr></thead><tbody>${folds.map((fold) => `<tr><td>${escapeHtml(fold.fold || fold.name || "—")}</td><td>${fmtPct(fold.strategy_cagr)}</td><td>${fmtPct(fold.qqq_cagr)}</td><td>${fmtPct(fold.qqq_delta)}</td><td>${fold.passed ? "통과" : "탈락"}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">검증 폴드 기록 없음</p>`;
  return `<div class="diagnostic-grid"><dl class="details"><dt>실행 ID</dt><dd>${escapeHtml(item.run_id)}</dd><dt>전략 해시</dt><dd>${escapeHtml(item.strategy_hash)}</dd><dt>데이터 해시</dt><dd>${escapeHtml(item.dataset_hash || "—")}</dd><dt>벤치마크 해시</dt><dd>${escapeHtml(item.benchmark_dataset_hash || "—")}</dd><dt>기록 시각</dt><dd>${escapeHtml(formatDate(item.timestamp))}</dd></dl><div>${gateTable}${foldTable}</div></div>`;
}
function renderSelectedGeneration() {
  const summary = payload.generations.find((item) => item.generation === selectedGeneration); const item = summary ? payload.runs.find((run) => run.run_id === summary.best_run_id) : null;
  if (!summary) { $("analysis-empty").hidden = false; $("analysis-content").hidden = true; return; }
  $("analysis-empty").hidden = true; $("analysis-content").hidden = false;
  setText("selected-generation-label", `${summary.generation}세대 · 최고 후보`); setText("selected-status-copy", `${summary.candidate_count}개 후보 중 선택된 전략`); setText("selected-status", statusText(summary.status));
  $("selected-status").className = `badge ${stateClass(summary.status)}`; setText("selected-rationale", summary.proposal?.rationale || "이 세대의 제안 사유가 저장되지 않았습니다.");
  setText("selected-strategy-cagr", fmtPct(summary.best_strategy_cagr)); setText("selected-qqq-cagr", fmtPct(summary.best_qqq_cagr)); setText("selected-qqq-delta", fmtPct(summary.best_qqq_cagr_delta)); setText("selected-total-return", fmtPct(summary.best_total_return)); setText("selected-drawdown", fmtPct(summary.best_max_drawdown)); setText("selected-sharpe", fmt(summary.best_sharpe)); setText("selected-sortino", fmt(summary.best_sortino)); setText("selected-profit-factor", fmt(summary.best_profit_factor)); setText("selected-trades", summary.best_trade_count == null ? "—" : `${fmt(summary.best_trade_count)}회`); setText("selected-risk", summary.best_risk_compliant == null ? "확인 필요" : (summary.best_risk_compliant ? "준수" : "검토 필요"));
  $("selected-features").innerHTML = featureRows(item, summary); $("selected-yearly").innerHTML = yearlyRows(item); $("selected-proposal").innerHTML = renderProposal(summary.proposal); $("selected-diagnostics").innerHTML = renderDiagnostics(item);
}

function renderStatusOptions(items) { const filter = $("status-filter"); const previous = filter.value; const statuses = [...new Set(items.map((item) => item.status))].sort(); filter.innerHTML = `<option value="ALL">전체 상태</option>${statuses.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(statusText(value))}</option>`).join("")}`; filter.value = statuses.includes(previous) ? previous : "ALL"; }
function visibleRuns() { const query = $("run-search").value.trim().toLowerCase(); const status = $("status-filter").value; return payload.runs.filter((item) => (status === "ALL" || item.status === status) && (!query || `${item.generation} ${item.status} ${item.run_id} ${item.strategy_hash}`.toLowerCase().includes(query))); }
function renderRuns() { const runs = visibleRuns(); $("runs").innerHTML = runs.map((item) => `<tr class="run-row" data-generation="${item.generation}" tabindex="0"><td>${formatDate(item.timestamp)}</td><td><strong>${item.generation}세대</strong></td><td>${fmtPct(item.strategy_cagr)}</td><td>${fmtPct(item.qqq_cagr_delta ?? item.nasdaq_excess_return)}</td><td>${fmtPct(item.max_drawdown)}</td><td>${item.risk_compliant == null ? "확인 필요" : item.risk_compliant ? "통과" : "실패"}</td><td>${escapeHtml(statusText(item.status))}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">조건에 맞는 실행 기록이 없습니다.</td></tr>`; document.querySelectorAll(".run-row").forEach((row) => { row.addEventListener("click", () => { selectedGeneration = Number(row.dataset.generation); $("generation-select").value = String(selectedGeneration); renderGenerations(payload.generations); renderSelectedGeneration(); }); }); }

async function selectRun(runId) { const response = await fetch(`/api/backtest/runs/${encodeURIComponent(runId)}`); if (!response.ok) throw new Error("run unavailable"); return response.json(); }

function commandText() { const source = $("strategy-source").value.trim() || "<strategy.py>"; const data = $("data-source").value.trim() || "<data.parquet>"; const method = $("method").value; const count = Math.max(1, Number.parseInt($("count").value || "1", 10)); return `python cli.py run-generation --source ${source} --data ${data} --method ${method} --count ${count} --seed 0 --min-trades 10 --min-annual-trades 30 --min-qqq-cagr 0.10`; }
function renderCommand() { $("run-command").textContent = commandText(); }
async function loadBacktest() {
  $("api-state").textContent = "불러오는 중";
  try { const response = await fetch("/api/backtest"); if (!response.ok) throw new Error("backtest unavailable"); payload = await response.json(); renderResearch(payload.research || {}); renderSummary(payload.summary || {}); renderStatusOptions(payload.runs || []); renderGenerations(payload.generations || []); renderSelectedGeneration(); renderRuns(); $("last-updated").textContent = formatDate(payload.generated_at); $("api-state").textContent = "정상 연결"; }
  catch (error) { $("api-state").textContent = "연결 실패"; $("analysis-empty").hidden = false; $("analysis-content").hidden = true; $("generation-summary-table").innerHTML = `<tr><td colspan="8" class="muted">백테스트 데이터를 불러오지 못했습니다.</td></tr>`; }
}

$("generation-select").addEventListener("change", () => { selectedGeneration = Number($("generation-select").value); renderGenerations(payload.generations); renderSelectedGeneration(); });
$("run-search").addEventListener("input", renderRuns); $("status-filter").addEventListener("change", renderRuns); $("refresh").addEventListener("click", loadBacktest);
[$("strategy-source"), $("data-source"), $("method"), $("count")].forEach((input) => input.addEventListener("input", renderCommand));
$("copy-run-command").addEventListener("click", async () => { try { await navigator.clipboard.writeText(commandText()); $("command-feedback").textContent = "실행 명령을 클립보드에 복사했습니다. 터미널에서 검토 후 실행하세요."; } catch (error) { $("command-feedback").textContent = "복사에 실패했습니다. 명령을 직접 선택해 복사하세요."; } });
renderCommand(); loadBacktest(); setInterval(loadBacktest, 15000);
