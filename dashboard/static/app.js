const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const STATUS_LABELS = {paper:"모의투자", PAPER:"모의투자", ONLINE:"온라인", OFFLINE:"오프라인", STALE:"응답 지연", UNKNOWN:"확인 필요", ERROR:"오류", DEGRADED:"일부 기능 제한", EMPTY:"없음", PASS:"통과", FAIL:"실패", VALIDATED:"검증 완료", FAILED:"실패"};
const WARNING_LABELS = {KIS_CONFIG_MISSING:"KIS 모의투자 설정이 없습니다", KIS_REFRESH_FAILED:"KIS 계좌 정보 갱신에 실패했습니다", LIVE_MODE_REJECTED:"실전투자 모드 요청이 차단되었습니다", LLM_STATUS_INVALID:"Codex 상태 정보를 읽을 수 없습니다"};
const statusLabel = (value) => STATUS_LABELS[String(value ?? "").toUpperCase()] || String(value ?? "확인 필요");
const providerLabel = (value) => ({codex_desktop:"Codex Desktop", codex_exec:"Codex CLI"}[String(value ?? "")] || String(value ?? "확인 필요"));
const warningLabel = (value) => WARNING_LABELS[value] || String(value ?? "확인 필요");
const fmt = (value, suffix = "") => value == null ? "—" : `${Number(value).toLocaleString("ko-KR", {maximumFractionDigits: 2})}${suffix}`;
const formatDate = (value, fallback = "—") => { if (!value) return fallback; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", {dateStyle:"medium", timeStyle:"short"}); };

async function loadDashboard() {
  $("api-state").textContent = "불러오는 중";
  try {
    const [healthResponse, dashboardResponse, catalogResponse] = await Promise.all([fetch("/api/health"), fetch("/api/dashboard"), fetch("/api/features/catalog")]);
    if (!healthResponse.ok || !dashboardResponse.ok || !catalogResponse.ok) throw new Error("dashboard unavailable");
    renderHealth(await healthResponse.json());
    renderDashboard(await dashboardResponse.json());
    renderFeatureCatalog(await catalogResponse.json());
    $("api-state").textContent = "정상 연결";
  } catch (error) {
    $("api-state").textContent = "오프라인 · 이전 데이터";
    $("kis-status").textContent = statusLabel("OFFLINE");
    $("kis-detail").textContent = "저장된 정보가 오래되었을 수 있음";
    $("llm-status").textContent = statusLabel("UNKNOWN");
    $("llm-detail").textContent = "로컬 상태를 확인할 수 없음";
  }
}

function renderHealth(health) {
  $("mode").textContent = statusLabel(health.effective_mode);
  $("mode-detail").textContent = health.live_enabled ? "주의: 실전투자 플래그 감지" : "실전투자 비활성화";
  $("kis-status").textContent = statusLabel(health.kis_status);
  $("kis-detail").textContent = statusLabel(health.status);
  $("worker-status").textContent = `온라인 ${health.online_workers}명`;
  $("worker-detail").textContent = `응답 지연 ${health.stale_workers}명 · Docker ${statusLabel(health.docker_status)}`;
}

function renderDashboard(data) {
  const strategy = data.strategy || {};
  const account = data.account || {};
  const workers = data.workers || [];
  const llm = data.llm || {};
  $("last-updated").textContent = formatDate(data.generated_at, "아직 갱신되지 않음");
  $("llm-status").textContent = statusLabel(llm.status);
  $("llm-detail").textContent = `${providerLabel(llm.provider)} · ${statusLabel(llm.last_result)}`;
  $("account-badge").textContent = statusLabel(account.status);
  $("account-number").textContent = account.account_number || "******";
  $("equity").textContent = fmt(account.equity);
  $("cash").textContent = fmt(account.cash);
  $("buying-power").textContent = fmt(account.buying_power);
  $("holdings").innerHTML = (account.holdings || []).map((item) => `<tr><td>${escapeHtml(item.symbol)}</td><td>${fmt(item.quantity)}</td><td>${fmt(item.market_value)}</td><td>${fmt(item.profit_loss)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">보유 종목 없음</td></tr>`;
  $("champion-badge").textContent = statusLabel(strategy.status);
  $("champion-score").textContent = fmt(strategy.score);
  $("champion-detail").textContent = strategy.champion_hash || "최고 전략 없음";
  $("champion-hash").textContent = strategy.champion_hash || "—";
  $("champion-family").textContent = strategy.family || "—";
  $("champion-generation").textContent = strategy.generation == null ? "—" : strategy.generation;
  $("champion-features").textContent = (strategy.feature_ids || []).join(", ") || "없음";
  $("champion-risk").textContent = strategy.risk_compliant == null ? "—" : (strategy.risk_compliant ? "준수" : "검토 필요");
  $("workers-badge").textContent = `온라인 ${workers.filter((item) => item.online_state === "ONLINE").length}명`;
  $("workers").innerHTML = workers.map((item) => `<tr><td>${escapeHtml(item.worker_id)}</td><td>${escapeHtml(item.role)}</td><td>${statusLabel(item.online_state)}</td><td>${formatDate(item.last_heartbeat)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">작업자 응답 기록 없음</td></tr>`;
  const tests = data.tests || [];
  $("test-count").textContent = `${tests.length}회 실행`;
  $("tests").innerHTML = tests.map((item) => `<tr><td>${formatDate(item.timestamp)}</td><td>${escapeHtml(item.run_id)}</td><td>${item.generation}</td><td>${fmt(item.total_return, "")}</td><td>${fmt(item.nasdaq_excess_return, "")}</td><td>${item.risk_compliant == null ? "—" : (item.risk_compliant ? "통과" : "실패")}</td><td>${escapeHtml(statusLabel(item.status))}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">테스트 기록 없음</td></tr>`;
  const trend = data.trend || [];
  $("trend").innerHTML = trend.map((item) => { const width = Math.max(2, Math.min(100, ((Number(item.score ?? 0) + 1) / 2) * 100)); return `<div class="trend-row"><strong>세대 ${item.generation}</strong><div class="trend-track"><div class="trend-fill" style="width:${width}%"></div></div><span class="trend-meta">점수 ${fmt(item.score)}</span></div>`; }).join("") || `<p class="muted">아직 전략 발전 기록이 없습니다.</p>`;
  const warnings = data.warning_codes || [];
  $("warnings-card").hidden = warnings.length === 0;
  $("warnings").innerHTML = warnings.map((warning) => `<li>${escapeHtml(warningLabel(warning))}</li>`).join("");
}

function renderFeatureCatalog(features) {
  const timeframeLabels = {"1m":"1분봉", "5m":"5분봉", "15m":"15분봉", "1h":"1시간봉", "1d":"일봉", "1w":"1주봉", "1mo":"1개월봉"};
  $("feature-count").textContent = `${features.length}개`;
  $("feature-catalog").innerHTML = features.map((item) => {
    const aliases = (item.aliases || []).map(escapeHtml).join(", ") || "없음";
    const sources = (item.source_repositories || []).map(escapeHtml).join(", ") || "독립 구현";
    const licenses = (item.source_licenses || []).map(escapeHtml).join(", ") || "내부";
    const timeframes = (item.supported_timeframes || []).map((value) => timeframeLabels[value] || escapeHtml(value)).join(" · ");
    return `<tr><td><strong>${escapeHtml(item.canonical_name)}</strong><br><span class="muted">${escapeHtml(item.family)} · ${escapeHtml(item.data_contract)}</span></td><td>${escapeHtml(item.calculator)}</td><td>${aliases}</td><td>${sources}<br><span class="muted">${licenses}</span></td><td>${timeframes}</td><td>${escapeHtml(statusLabel(item.verification_status))}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="muted">등록된 인디케이터가 없습니다.</td></tr>`;
}

$("refresh").addEventListener("click", async () => { $("refresh").disabled = true; try { const response = await fetch("/api/refresh", {method: "POST"}); if (!response.ok) throw new Error("refresh failed"); renderDashboard(await response.json()); await loadDashboard(); } finally { $("refresh").disabled = false; } });
document.querySelectorAll(".copy-command").forEach((button) => {
  button.addEventListener("click", async () => {
    const command = button.dataset.copy || "";
    try {
      await navigator.clipboard.writeText(command);
      const previous = button.textContent;
      button.textContent = "복사됨";
      setTimeout(() => { button.textContent = previous; }, 1200);
    } catch (error) {
      button.textContent = "복사 실패";
      setTimeout(() => { button.textContent = "복사"; }, 1200);
    }
  });
});
loadDashboard();
setInterval(loadDashboard, 10000);
