const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const STATUS_LABELS = {paper:"모의투자", PAPER:"모의투자", ONLINE:"온라인", OFFLINE:"오프라인", STALE:"응답 지연", UNKNOWN:"확인 필요", ERROR:"오류", DEGRADED:"일부 기능 제한", EMPTY:"없음", PASS:"통과", FAIL:"실패", VALIDATED:"검증 완료", FAILED:"실패", REGISTERED:"검증 완료", PROPOSED:"검증 대기", QUARANTINED:"격리"};
const WARNING_LABELS = {KIS_CONFIG_MISSING:"KIS 모의투자 설정이 없습니다", KIS_REFRESH_FAILED:"KIS 계좌 정보 갱신에 실패했습니다", LIVE_MODE_REJECTED:"실전투자 모드 요청이 차단되었습니다", LLM_STATUS_INVALID:"Codex 상태 정보를 읽을 수 없습니다", FRONTIER_STATE_INVALID:"Frontier 상태를 읽을 수 없습니다", RESCUE_POOL_STATE_INVALID:"Rescue Pool 상태를 읽을 수 없습니다"};
const statusLabel = (value) => STATUS_LABELS[String(value ?? "").toUpperCase()] || String(value ?? "확인 필요");
const providerLabel = (value) => ({codex_desktop:"Codex Desktop", codex_exec:"Codex CLI"}[String(value ?? "")] || String(value ?? "확인 필요"));
const fmt = (value, suffix = "") => value == null ? "—" : `${Number(value).toLocaleString("ko-KR", {maximumFractionDigits: 2})}${suffix}`;
const fmtPct = (value) => value == null ? "—" : `${(Number(value) * 100).toLocaleString("ko-KR", {maximumFractionDigits: 1})}%`;
const formatDate = (value, fallback = "—") => { if (!value) return fallback; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", {dateStyle:"medium", timeStyle:"short"}); };

function setStatus(element, value, status = "neutral") { element.textContent = value; element.dataset.status = status; }

function renderHealth(health) {
  const liveRequested = String(health.effective_mode).toLowerCase() !== "paper" || health.live_enabled;
  setStatus($("system-status"), statusLabel(health.status), health.status === "ONLINE" ? "positive" : "warning");
  $("system-detail").textContent = liveRequested ? "실전투자 요청이 차단됨 · 주문 비활성화" : `${health.status === "ONLINE" ? "정상" : "일부 기능 제한"} · 주문 비활성화`;
  setStatus($("health-badge"), statusLabel(health.status), health.status === "ONLINE" ? "positive" : "warning");
  setStatus($("kis-status"), statusLabel(health.kis_status), health.kis_status === "ONLINE" ? "positive" : "warning");
  $("kis-detail").textContent = health.kis_status === "ONLINE" ? "모의투자 계좌 응답 정상" : "계좌 정보가 없거나 오래됨";
  $("worker-status").textContent = `온라인 ${health.online_workers}명`;
  $("worker-detail").textContent = `응답 지연 ${health.stale_workers}명 · Docker ${statusLabel(health.docker_status)}`;
  $("safety-detail").textContent = liveRequested ? "실전투자 요청은 차단되며 주문 기능은 비활성화됩니다." : "주문 기능이 비활성화된 로컬 읽기 전용 화면입니다.";
  setStatus($("safety-badge"), liveRequested ? "확인 필요" : "안전 상태", liveRequested ? "warning" : "positive");
}

function buildAttention(data) {
  const items = []; const strategy = data.strategy || {}; const research = data.research || {}; const warnings = data.warning_codes || [];
  if (strategy.status === "EMPTY" || !strategy.champion_hash) items.push({level:"critical", title:"Champion이 없습니다", detail:"승격된 전략이 없어 성과 비교를 표시할 수 없습니다."});
  if (!research.frontier_count) items.push({level:"warning", title:"Frontier 전략이 없습니다", detail:"전략과 데이터가 준비된 뒤 평가 파이프라인을 실행하세요."});
  if (warnings.includes("KIS_CONFIG_MISSING") || warnings.includes("KIS_REFRESH_FAILED")) items.push({level:"warning", title:"KIS 계좌 연결을 확인하세요", detail:"설정이 없거나 최근 갱신에 실패했습니다. 계좌 수치는 현재 판단에 사용하지 마세요."});
  warnings.filter((code) => !["KIS_CONFIG_MISSING", "KIS_REFRESH_FAILED"].includes(code)).forEach((code) => items.push({level:"warning", title:WARNING_LABELS[code] || code, detail:"상세 상태는 원시 상태·작업자 기록에서 확인하세요."}));
  if (!items.length) items.push({level:"info", title:"즉시 확인할 문제 없음", detail:"현재 기록된 경고가 없습니다."});
  return items;
}

function renderAttention(data) {
  const items = buildAttention(data); $("attention-count").textContent = `${items.length}건`;
  $("attention-list").innerHTML = items.map((item) => `<li class="attention-${item.level}"><span class="attention-icon" aria-hidden="true">${item.level === "info" ? "i" : "!"}</span><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></div></li>`).join("");
}

function renderNextAction(data) {
  const strategy = data.strategy || {};
  if (strategy.status === "EMPTY" || !strategy.champion_hash) {
    $("next-action-copy").textContent = "연구를 시작하려면 검증된 전략 소스와 버전이 지정된 Parquet 데이터를 준비하세요.";
    $("next-action-command").textContent = "python cli.py run-generation --source <strategy.py> --data <data.parquet>";
  } else {
    $("next-action-copy").textContent = "Champion 근거와 최근 평가 기록을 확인한 뒤 다음 세대 연구 여부를 결정하세요.";
    $("next-action-command").textContent = "python cli.py dashboard-status --state-dir state";
  }
}

function renderResearch(research) {
  const value = research || {}; $("frontier-count").textContent = `${value.frontier_count || 0}개`; $("frontier-detail").textContent = `${value.family_count || 0}개 패밀리`;
  $("known-good-count").textContent = value.known_good_count || 0; $("known-bad-count").textContent = value.known_bad_count || 0; $("unexplored-count").textContent = value.unexplored_count || 0; $("rescue-count").textContent = value.rescue_count || 0;
  const total = (value.known_good_count || 0) + (value.known_bad_count || 0) + (value.unexplored_count || 0) + (value.rescue_count || 0); $("research-summary").textContent = `${total}개 기록`;
  const families = Object.entries(value.frontier_families || {}).sort((a, b) => b[1] - a[1]); const max = Math.max(1, ...families.map((item) => item[1]));
  $("family-summary").innerHTML = families.length ? families.map(([family, count]) => `<div class="family-row"><span>${escapeHtml(family)}</span><div class="family-track"><span style="width:${Math.max(5, Math.min(100, count / max * 100))}%"></span></div><strong>${count}</strong></div>`).join("") : `<p class="muted">아직 Frontier 패밀리 기록이 없습니다.</p>`;
}

function renderDashboard(data) {
  const strategy = data.strategy || {}; const account = data.account || {}; const workers = data.workers || []; const llm = data.llm || {}; const tests = data.tests || {}; const research = data.research || {};
  $("last-updated").textContent = formatDate(data.generated_at, "아직 갱신되지 않음");
  setStatus($("champion-score"), strategy.score == null ? "없음" : fmt(strategy.score), strategy.score == null ? "neutral" : "positive"); $("champion-detail").textContent = strategy.champion_hash || "승격된 전략 없음";
  setStatus($("champion-badge"), statusLabel(strategy.status), strategy.status === "CHAMPION" ? "positive" : "neutral"); $("champion-evidence").textContent = strategy.champion_hash ? "기록된 Champion 근거를 아래에서 확인하세요." : "아직 승격된 전략이 없습니다. 성과 비교를 표시할 근거가 없습니다.";
  $("champion-hash").textContent = strategy.champion_hash || "—"; $("champion-family").textContent = strategy.family || "—"; $("champion-generation").textContent = strategy.generation == null ? "—" : strategy.generation; $("champion-score-detail").textContent = fmt(strategy.score); $("champion-return").textContent = fmtPct(strategy.total_return); $("champion-risk").textContent = strategy.risk_compliant == null ? "확인 필요" : (strategy.risk_compliant ? "준수" : "검토 필요");
  const readinessReady = Boolean(strategy.champion_hash && research.frontier_count); setStatus($("readiness-status"), readinessReady ? "준비됨" : "확인 필요", readinessReady ? "positive" : "warning"); $("readiness-detail").textContent = readinessReady ? "Champion과 Frontier 근거가 있음" : "전략·데이터·평가 기록을 확인하세요";
  $("llm-status").textContent = statusLabel(llm.status); $("llm-detail").textContent = `${providerLabel(llm.provider)} · ${statusLabel(llm.last_result)}`;
  $("account-number").textContent = account.account_number || "******"; $("equity").textContent = fmt(account.equity); $("cash").textContent = fmt(account.cash); $("buying-power").textContent = fmt(account.buying_power); $("holdings").innerHTML = (account.holdings || []).map((item) => `<tr><td>${escapeHtml(item.symbol)}</td><td>${fmt(item.quantity)}</td><td>${fmt(item.market_value)}</td><td>${fmt(item.profit_loss)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">보유 종목 없음 또는 계좌 미연결</td></tr>`;
  $("workers").innerHTML = workers.map((item) => `<tr><td>${escapeHtml(item.worker_id)}</td><td>${escapeHtml(item.role)}</td><td>${escapeHtml(statusLabel(item.online_state))}</td><td>${formatDate(item.last_heartbeat)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">작업자 응답 기록 없음</td></tr>`;
  $("test-count").textContent = `${tests.length}회 실행`; $("tests").innerHTML = tests.map((item) => `<tr><td>${formatDate(item.timestamp)}</td><td>${escapeHtml(item.run_id)}</td><td>${item.generation}</td><td>${fmtPct(item.total_return)}</td><td>${fmtPct(item.nasdaq_excess_return)}</td><td>${item.risk_compliant == null ? "확인 필요" : (item.risk_compliant ? "통과" : "실패")}</td><td>${escapeHtml(statusLabel(item.status))}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">아직 평가 기록이 없습니다.</td></tr>`;
  const trend = data.trend || []; $("trend").innerHTML = trend.length ? trend.map((item) => `<div class="trend-row"><strong>세대 ${item.generation}</strong><span>${fmt(item.score)}</span><span>${fmtPct(item.total_return)}</span></div>`).join("") : `<p class="muted">아직 전략 발전 기록이 없습니다.</p>`;
  const warnings = data.warning_codes || []; $("warnings").hidden = warnings.length === 0; $("warnings-list").innerHTML = warnings.map((warning) => `<li>${escapeHtml(WARNING_LABELS[warning] || warning)}</li>`).join(""); renderAttention(data); renderNextAction(data); renderResearch(research);
}

function renderFeatureCatalog(features) { const timeframeLabels = {"1m":"1분봉", "5m":"5분봉", "15m":"15분봉", "1h":"1시간봉", "1d":"일봉", "1w":"1주봉", "1mo":"1개월봉"}; $("feature-count").textContent = `${features.length}개`; $("feature-catalog").innerHTML = features.map((item) => { const aliases = (item.aliases || []).map(escapeHtml).join(", ") || "없음"; const sources = (item.source_repositories || []).map(escapeHtml).join(", ") || "독립 구현"; const licenses = (item.source_licenses || []).map(escapeHtml).join(", ") || "내부"; const timeframes = (item.supported_timeframes || []).map((value) => timeframeLabels[value] || escapeHtml(value)).join(" · "); return `<tr><td><strong>${escapeHtml(item.canonical_name)}</strong><br><span class="muted">${escapeHtml(item.family)} · ${escapeHtml(item.data_contract)}</span></td><td>${escapeHtml(item.calculator)}</td><td>${aliases}</td><td>${sources}<br><span class="muted">${licenses}</span></td><td>${timeframes}</td><td>${escapeHtml(statusLabel(item.verification_status))}</td></tr>`; }).join("") || `<tr><td colspan="6" class="muted">등록된 인디케이터가 없습니다.</td></tr>`; }

async function loadDashboard() { $("api-state").textContent = "불러오는 중"; try { const [healthResponse, dashboardResponse, catalogResponse] = await Promise.all([fetch("/api/health"), fetch("/api/dashboard"), fetch("/api/features/catalog")]); if (!healthResponse.ok || !dashboardResponse.ok || !catalogResponse.ok) throw new Error("dashboard unavailable"); renderHealth(await healthResponse.json()); renderDashboard(await dashboardResponse.json()); renderFeatureCatalog(await catalogResponse.json()); $("api-state").textContent = "정상 연결"; } catch (error) { $("api-state").textContent = "연결 실패 · 이전 상태 확인 필요"; setStatus($("system-status"), "오프라인", "warning"); $("system-detail").textContent = "서버 응답을 확인할 수 없습니다."; $("attention-list").innerHTML = `<li class="attention-critical"><span class="attention-icon" aria-hidden="true">!</span><div><strong>대시보드 데이터를 불러오지 못했습니다</strong><span>서버가 실행 중인지 확인한 뒤 새로고침하세요.</span></div></li>`; } }

$("refresh").addEventListener("click", async () => { $("refresh").disabled = true; try { const response = await fetch("/api/refresh", {method: "POST"}); if (!response.ok) throw new Error("refresh failed"); renderDashboard(await response.json()); await loadDashboard(); } finally { $("refresh").disabled = false; } });
document.querySelectorAll(".copy-command").forEach((button) => { button.addEventListener("click", async () => { const target = $(button.dataset.copyTarget); const command = target ? target.textContent : (button.dataset.copy || ""); try { await navigator.clipboard.writeText(command); const previous = button.textContent; button.textContent = "복사됨"; setTimeout(() => { button.textContent = previous; }, 1200); } catch (error) { button.textContent = "복사 실패"; setTimeout(() => { button.textContent = "복사"; }, 1200); } }); });
loadDashboard(); setInterval(loadDashboard, 15000);
