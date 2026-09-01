const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const fmt = (value, suffix = "") => value == null ? "—" : `${Number(value).toLocaleString(undefined, {maximumFractionDigits: 2})}${suffix}`;

async function loadDashboard() {
  $("api-state").textContent = "Loading";
  try {
    const [healthResponse, dashboardResponse] = await Promise.all([fetch("/api/health"), fetch("/api/dashboard")]);
    if (!healthResponse.ok || !dashboardResponse.ok) throw new Error("dashboard unavailable");
    renderHealth(await healthResponse.json());
    renderDashboard(await dashboardResponse.json());
    $("api-state").textContent = "Online";
  } catch (error) {
    $("api-state").textContent = "Offline / stale data";
    $("kis-status").textContent = "OFFLINE";
    $("kis-detail").textContent = "Local snapshot may be stale";
    $("llm-status").textContent = "UNKNOWN";
    $("llm-detail").textContent = "Local status unavailable";
  }
}

function renderHealth(health) {
  $("mode").textContent = health.effective_mode.toUpperCase();
  $("mode-detail").textContent = health.live_enabled ? "Unexpected live flag" : "Live disabled";
  $("kis-status").textContent = health.kis_status;
  $("kis-detail").textContent = health.status;
  $("worker-status").textContent = `${health.online_workers} online`;
  $("worker-detail").textContent = `${health.stale_workers} stale · Docker ${health.docker_status}`;
}

function renderDashboard(data) {
  const strategy = data.strategy || {};
  const account = data.account || {};
  const workers = data.workers || [];
  const llm = data.llm || {};
  $("last-updated").textContent = data.generated_at || "—";
  $("llm-status").textContent = llm.status || "UNKNOWN";
  $("llm-detail").textContent = `${llm.provider || "codex_desktop"} · ${llm.last_result || "UNKNOWN"}`;
  $("account-badge").textContent = account.status || "UNKNOWN";
  $("account-number").textContent = account.account_number || "******";
  $("equity").textContent = fmt(account.equity);
  $("cash").textContent = fmt(account.cash);
  $("buying-power").textContent = fmt(account.buying_power);
  $("holdings").innerHTML = (account.holdings || []).map((item) => `<tr><td>${escapeHtml(item.symbol)}</td><td>${fmt(item.quantity)}</td><td>${fmt(item.market_value)}</td><td>${fmt(item.profit_loss)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">No holdings</td></tr>`;
  $("champion-badge").textContent = strategy.status || "EMPTY";
  $("champion-score").textContent = fmt(strategy.score);
  $("champion-detail").textContent = strategy.champion_hash || "No champion recorded";
  $("champion-hash").textContent = strategy.champion_hash || "—";
  $("champion-family").textContent = strategy.family || "—";
  $("champion-generation").textContent = strategy.generation == null ? "—" : strategy.generation;
  $("champion-features").textContent = (strategy.feature_ids || []).join(", ") || "None";
  $("champion-risk").textContent = strategy.risk_compliant == null ? "—" : (strategy.risk_compliant ? "Compliant" : "Review");
  $("workers-badge").textContent = `${workers.filter((item) => item.online_state === "ONLINE").length} online`;
  $("workers").innerHTML = workers.map((item) => `<tr><td>${escapeHtml(item.worker_id)}</td><td>${escapeHtml(item.role)}</td><td>${escapeHtml(item.online_state)}</td><td>${escapeHtml(item.last_heartbeat || "—")}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">No worker heartbeat</td></tr>`;
  const tests = data.tests || [];
  $("test-count").textContent = `${tests.length} runs`;
  $("tests").innerHTML = tests.map((item) => `<tr><td>${escapeHtml(item.timestamp)}</td><td>${escapeHtml(item.run_id)}</td><td>${item.generation}</td><td>${fmt(item.total_return, "")}</td><td>${fmt(item.nasdaq_excess_return, "")}</td><td>${item.risk_compliant == null ? "—" : (item.risk_compliant ? "PASS" : "FAIL")}</td><td>${escapeHtml(item.status)}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">No test records</td></tr>`;
  const trend = data.trend || [];
  $("trend").innerHTML = trend.map((item) => { const width = Math.max(2, Math.min(100, ((Number(item.score ?? 0) + 1) / 2) * 100)); return `<div class="trend-row"><strong>Gen ${item.generation}</strong><div class="trend-track"><div class="trend-fill" style="width:${width}%"></div></div><span class="trend-meta">score ${fmt(item.score)}</span></div>`; }).join("") || `<p class="muted">No generation trend yet</p>`;
  const warnings = data.warning_codes || [];
  $("warnings-card").hidden = warnings.length === 0;
  $("warnings").innerHTML = warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("");
}

$("refresh").addEventListener("click", async () => { $("refresh").disabled = true; try { const response = await fetch("/api/refresh", {method: "POST"}); if (!response.ok) throw new Error("refresh failed"); renderDashboard(await response.json()); await loadDashboard(); } finally { $("refresh").disabled = false; } });
loadDashboard();
setInterval(loadDashboard, 10000);
