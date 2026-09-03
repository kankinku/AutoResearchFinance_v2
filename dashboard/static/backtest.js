const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const fmt = (value) => value == null ? "—" : Number(value).toLocaleString("ko-KR", {maximumFractionDigits:2});
const fmtPct = (value) => value == null ? "—" : `${(Number(value) * 100).toLocaleString("ko-KR", {maximumFractionDigits:1})}%`;
const formatDate = (value) => { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", {dateStyle:"medium", timeStyle:"short"}); };
let payload = {runs:[], capabilities:[], summary:{}};
let selectedRunId = null;

function commandText() {
  const source = $("strategy-source").value.trim() || "<strategy.py>";
  const data = $("data-source").value.trim() || "<data.parquet>";
  const method = $("method").value;
  const count = Math.max(1, Number.parseInt($("count").value || "1", 10));
  return `python cli.py run-generation --source ${source} --data ${data} --method ${method} --count ${count} --seed 0 --min-trades 10 --min-annual-trades 30 --min-qqq-cagr 0.10`;
}

function renderCommand() { $("run-command").textContent = commandText(); }

function renderSummary(summary) {
  $("total-runs").textContent = `${summary.total_runs || 0}회`;
  $("succeeded-runs").textContent = `${summary.succeeded_runs || 0}회`;
  $("best-return").textContent = fmtPct(summary.best_total_return);
  $("best-run").textContent = summary.best_run_id ? `최고 실행 · ${summary.best_run_id}` : "최고 실행 없음";
  $("risk-runs").textContent = `${summary.risk_compliant_runs || 0}회`;
  $("ledger-count").textContent = `${summary.total_runs || 0}회`;
}

function renderCapabilities(items) {
  const connected = items.filter((item) => item.status === "CONNECTED").length;
  $("connection-count").textContent = `${connected}/${items.length}개 연결`;
  $("capabilities").innerHTML = items.map((item) => `<li class="capability-item"><div><strong>${escapeHtml(item.label)}</strong><span class="muted">${escapeHtml(item.description)}</span></div><span class="badge ${item.status === "CONNECTED" ? "badge-positive" : ""}">${statusLabel(item.status)}</span></li>`).join("") || `<li class="muted">연결된 기능이 없습니다.</li>`;
}

function renderStatusOptions(items) {
  const filter = $("status-filter"); const previous = filter.value;
  const statuses = [...new Set(items.map((item) => item.status))].sort();
  filter.innerHTML = `<option value="ALL">전체 상태</option>${statuses.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(statusLabel(value))}</option>`).join("")}`;
  filter.value = statuses.includes(previous) ? previous : "ALL";
}

function visibleRuns() {
  const query = $("run-search").value.trim().toLowerCase(); const status = $("status-filter").value;
  return payload.runs.filter((item) => {
    const matchesStatus = status === "ALL" || item.status === status;
    const haystack = `${item.run_id} ${item.strategy_hash}`.toLowerCase();
    return matchesStatus && (!query || haystack.includes(query));
  });
}

function renderRuns() {
  const runs = visibleRuns();
  $("runs").innerHTML = runs.map((item) => `<tr class="run-row ${item.run_id === selectedRunId ? "selected" : ""}" data-run-id="${escapeHtml(item.run_id)}" tabindex="0"><td>${formatDate(item.timestamp)}</td><td><strong>${escapeHtml(item.run_id)}</strong></td><td>${item.generation}</td><td>${fmtPct(item.total_return)}</td><td>${fmtPct(item.nasdaq_excess_return)}</td><td>${fmtPct(item.max_drawdown)}</td><td>${item.risk_compliant == null ? "확인 필요" : (item.risk_compliant ? "통과" : "실패")}</td><td>${escapeHtml(statusLabel(item.status))}</td></tr>`).join("") || `<tr><td colspan="8" class="muted">조건에 맞는 실행 기록이 없습니다.</td></tr>`;
  document.querySelectorAll(".run-row").forEach((row) => { row.addEventListener("click", () => selectRun(row.dataset.runId)); row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectRun(row.dataset.runId); } }); });
}

function renderSelected(item) {
  if (!item) { $("selected-status").textContent = "선택 없음"; $("selected-copy").textContent = "원장에서 실행을 선택하면 해당 결과의 수익률·벤치마크 초과·위험 상태를 확인할 수 있습니다."; ["run-id","strategy-hash","generation","score","return","excess","drawdown","risk"].forEach((key) => { $(`selected-${key}`).textContent = "—"; }); $("selected-yearly").innerHTML = `<tr><td colspan="4" class="muted">선택된 실행 없음</td></tr>`; $("selected-features").innerHTML = `<tr><td colspan="5" class="muted">선택된 실행 없음</td></tr>`; return; }
  $("selected-status").textContent = statusLabel(item.status); $("selected-status").dataset.status = item.status === "SURVIVOR" || item.status === "SUCCEEDED" ? "positive" : "warning"; $("selected-copy").textContent = `${formatDate(item.timestamp)}에 기록된 백테스트 결과입니다.`;
  $("selected-run-id").textContent = item.run_id; $("selected-strategy-hash").textContent = item.strategy_hash; $("selected-generation").textContent = item.generation; $("selected-score").textContent = fmt(item.score); $("selected-return").textContent = fmtPct(item.total_return); $("selected-excess").textContent = fmtPct(item.nasdaq_excess_return); $("selected-drawdown").textContent = fmtPct(item.max_drawdown); $("selected-risk").textContent = item.risk_compliant == null ? "확인 필요" : (item.risk_compliant ? "준수" : "검토 필요"); const yearly = item.yearly_metrics || []; $("selected-yearly").innerHTML = yearly.map((year) => `<tr><td>${escapeHtml(year.year)}${year.complete ? "" : " (진행 중)"}</td><td>${fmt(year.trade_count)}${year.complete && Number(year.trade_count) <= 30 ? " · 탈락" : ""}</td><td>${fmtPct(year.total_return)}</td><td>${year.complete ? (Number(year.trade_count) > 30 ? "통과" : "탈락") : "판정 제외"}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">연도별 기록 없음</td></tr>`; const lineage = item.feature_lineage || []; $("selected-features").innerHTML = lineage.map((feature) => `<tr><td>${escapeHtml(feature.alias || "—")}</td><td>${escapeHtml(feature.feature_id || "—")}</td><td>${escapeHtml((feature.inputs || []).join(", "))}<br>${escapeHtml(feature.timeframe || "—")}</td><td>${fmt(feature.lag_bars)} · ${fmt(feature.lookback)}</td><td>${escapeHtml(statusLabel(feature.status || "UNKNOWN"))}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">사용된 인디케이터 기록 없음</td></tr>`;
}

async function selectRun(runId) {
  if (!runId) return;
  selectedRunId = runId; renderRuns();
  try { const response = await fetch(`/api/backtest/runs/${encodeURIComponent(runId)}`); if (!response.ok) throw new Error("run unavailable"); renderSelected(await response.json()); } catch (error) { renderSelected(payload.runs.find((item) => item.run_id === runId)); }
}

async function loadBacktest() {
  $("api-state").textContent = "불러오는 중";
  try { const response = await fetch("/api/backtest"); if (!response.ok) throw new Error("backtest unavailable"); payload = await response.json(); renderSummary(payload.summary || {}); renderCapabilities(payload.capabilities || []); renderStatusOptions(payload.runs || []); renderRuns(); const selected = payload.runs.find((item) => item.run_id === selectedRunId) || payload.runs[0]; if (selected) await selectRun(selected.run_id); else renderSelected(null); $("last-updated").textContent = formatDate(payload.generated_at); $("api-state").textContent = "정상 연결"; } catch (error) { $("api-state").textContent = "연결 실패"; $("capabilities").innerHTML = `<li class="capability-item"><strong>백테스트 데이터를 불러오지 못했습니다.</strong><span class="muted">서버 실행 상태를 확인하고 새로고침하세요.</span></li>`; }
}

[$("strategy-source"), $("data-source"), $("method"), $("count")].forEach((input) => input.addEventListener("input", renderCommand));
$("run-search").addEventListener("input", renderRuns); $("status-filter").addEventListener("change", renderRuns); $("refresh").addEventListener("click", loadBacktest);
$("copy-run-command").addEventListener("click", async () => { try { await navigator.clipboard.writeText(commandText()); $("command-feedback").textContent = "실행 명령을 클립보드에 복사했습니다. 터미널에서 검토 후 실행하세요."; } catch (error) { $("command-feedback").textContent = "복사에 실패했습니다. 명령을 직접 선택해 복사하세요."; } });
renderCommand(); loadBacktest(); setInterval(loadBacktest, 15000);
