/* Original Quant web dashboard: performance-priority academic cohort view.
   Metrics are persisted, costed DEVELOPMENT backtest results, not live P&L. */
(function () {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const pct = (value) => Number.isFinite(Number(value))
    ? (Number(value) * 100).toLocaleString("ko-KR", {maximumFractionDigits:2}) + "%"
    : "—";
  const signedPoints = (value) => Number.isFinite(value)
    ? (value >= 0 ? "+" : "−") + Math.abs(value).toFixed(2) + "%p"
    : "—";
  const number = (value) => Number.isFinite(value) ? value : null;
  let latest = null;
  let windowSize = "all";

  function updateText(id, value) { byId(id).textContent = String(value); }

  function scaleChart(generations, width, height, benchmark, field, includeBest) {
    const left = 54, right = 20, top = 18, bottom = 34;
    const x0 = left, x1 = width - right, y0 = top, y1 = height - bottom;
    const genMin = generations[0].generation;
    const genMax = generations[generations.length - 1].generation;
    const x = (g) => x0 + (g - genMin) * (x1 - x0) / Math.max(1,genMax - genMin);
    const values = generations.map((g) => Number(g[field]) * 100);
    if (includeBest) values.push(...generations.filter((g) => g.best_so_far !== null)
      .map((g) => g.best_so_far * 100));
    if (benchmark !== null) values.push(benchmark * 100);
    const rawMin = Math.min(0,...values);
    const rawMax = Math.max(5,...values);
    const step = (rawMax - rawMin > 150 ? 50 : rawMax - rawMin > 65 ? 25 : 10);
    const low = Math.floor(rawMin / step) * step - (rawMin < 0 ? step * .2 : 0);
    const high = Math.ceil(rawMax / step) * step + step * .2;
    const y = (v) => y1 - ((v - low) / Math.max(1,high - low)) * (y1 - y0);
    const axis = [];
    const start = Math.ceil(low / step) * step;
    for(let value = start; value <= high + 0.0001; value += step) {
      const ordinate = y(value);
      axis.push('<line x1="' + x0 + '" x2="' + x1 + '" y1="' + ordinate.toFixed(1) +
        '" y2="' + ordinate.toFixed(1) + '" stroke="#e8edf4" stroke-width="1"/>');
      axis.push('<text x="' + (x0 - 9) + '" y="' + (ordinate+4).toFixed(1) +
        '" font-size="11" text-anchor="end" fill="#8190a2">' + value.toFixed(0) + '%</text>');
    }
    const labelIndexes = [...new Set([0,Math.floor((generations.length-1)/2),generations.length-1])];
    for (const i of labelIndexes) {
      const g=generations[i].generation;
      axis.push('<text x="' + x(g).toFixed(1) + '" y="' + (height-8) +
        '" text-anchor="middle" font-size="11" fill="#8190a2">G' + g + '</text>');
    }
    return {x,y,x0,x1,y0,y1,axis:axis.join("")};
  }

  function linePath(items, x, y, pick) {
    let path="";
    let hasPrev=false;
    for(const g of items) {
      const value=pick(g);
      if(value === null || !Number.isFinite(value)) { hasPrev=false; continue; }
      path += (hasPrev ? "L" : "M") + x(g.generation).toFixed(2) + " " +
        y(value * 100).toFixed(2) + " ";
      hasPrev=true;
    }
    return path.trim();
  }

  function renderReturns(data, history) {
    const svg=byId("perf-return-chart");
    if (!history.length) {
      svg.innerHTML='<text x="480" y="160" text-anchor="middle" fill="#64748b">측정된 세대가 없습니다</text>';
      return;
    }
    const benchmark=number(Number(data.qqq_dev_bh_return));
    const dimensions=scaleChart(history,960,320,benchmark,"return",true);
    const {x,y,x0,x1,axis}=dimensions;
    const paths=[];
    paths.push(axis);
    if(benchmark !== null) {
      const yy=y(benchmark*100).toFixed(1);
      paths.push('<line x1="' + x0 + '" x2="' + x1 + '" y1="' + yy + '" y2="' + yy +
        '" stroke="#8a92a1" stroke-width="2" stroke-dasharray="7 6"/>');
    }
    paths.push('<path d="' + linePath(history,x,y,(g)=>g.return) +
      '" fill="none" stroke="#a6b9d0" stroke-width="1.7" stroke-linejoin="round"/>');
    paths.push('<path d="' + linePath(history,x,y,(g)=>g.best_so_far) +
      '" fill="none" stroke="#2364ae" stroke-width="3" stroke-linejoin="round"/>');
    // Actual points include accessible SVG title information for inspection.
    for(const g of history) {
      const gx=x(g.generation).toFixed(1), gy=y(g.return*100).toFixed(1);
      paths.push('<circle cx="' + gx + '" cy="' + gy +
        '" r="2.5" fill="#8c9fb7"><title>G' + g.generation +
        ' · 수익률 ' + pct(g.return) + ' · MDD ' + pct(g.mdd) + '</title></circle>');
    }
    svg.innerHTML=paths.join("");
    const first=history[0],last=history[history.length-1];
    updateText("perf-return-summary","G"+first.generation+"~G"+last.generation+
      " · 후보 수익률은 개별 백테스트 결과이며, 파란 선은 해당 시점까지 발견된 적격 최고 후보입니다.");
  }

  function renderRisk(history) {
    const svg=byId("perf-risk-chart");
    if (!history.length) { svg.innerHTML=""; return; }
    const dim=scaleChart(history,570,190,null,"mdd",false);
    const {x,y,axis}=dim;
    const path=linePath(history,x,y,(g)=>g.mdd);
    const circles=history.map((g)=>'<circle cx="' + x(g.generation).toFixed(1) +
      '" cy="' + y(g.mdd*100).toFixed(1) + '" r="2.6" fill="#8b76b6">' +
      '<title>G' + g.generation + ' · MDD ' + pct(g.mdd) + '</title></circle>');
    svg.innerHTML=axis+'<path d="'+path+
      '" stroke="#8b76b6" stroke-width="2" fill="none"/>'+circles.join("");
    const avg=history.reduce((sum,g)=>sum+g.mdd,0)/history.length;
    updateText("perf-risk-average","표시 구간 평균 "+pct(avg));
  }

  function enrich(rows) {
    let best = null;
    return rows.map((g) => {
      const entry = {
        generation:Math.trunc(Number(g.generation)), return:Number(g.return),
        mdd:Number(g.mdd), trades:Number(g.trades),
        eligible:Boolean(g.eligible), best_so_far:null,
      };
      if(entry.eligible && Number.isFinite(entry.return)) {
        best = best === null ? entry.return : Math.max(best,entry.return);
      }
      entry.best_so_far=best;
      return entry;
    });
  }

  function render(data) {
    latest=data;
    updateText("perf-cohort-label",data.cohort_label || "개발 연구 원장");
    const records=enrich(Array.isArray(data.generations)
      ? [...data.generations].sort((a,b)=>a.generation-b.generation):[]);
    const best=data.best_eligible, qqq=Number(data.qqq_dev_bh_return);
    const bestReturn=best ? Number(best.return) : null;
    updateText("perf-best-return",best ? pct(bestReturn) : "아직 없음");
    updateText("perf-best-generation",best
      ? "G"+best.generation+" · 거래 30건 이상 조건 충족" : "거래 30건 이상 적격 후보 없음");
    updateText("perf-best-mdd",best ? pct(best.mdd) : "—");
    updateText("perf-best-trades",best ? "완료 거래 "+best.trades+"건" : "거래 기록 없음");
    updateText("perf-qqq-return",pct(qqq));
    const gap=(bestReturn !== null && Number.isFinite(qqq)) ? (bestReturn - qqq)*100 : null;
    updateText("perf-excess",signedPoints(gap));
    byId("perf-excess").classList.toggle("is-negative",gap !== null && gap < 0);
    const cap=Math.max(1,qqq,bestReturn === null ? 0 : bestReturn);
    byId("perf-strategy-bar").style.width=
      (bestReturn===null?0:Math.max(0,bestReturn)/cap*100).toFixed(2)+"%";
    byId("perf-qqq-bar").style.width=(Math.max(0,qqq)/cap*100).toFixed(2)+"%";
    updateText("perf-strategy-compare",best ? pct(bestReturn) : "—");
    updateText("perf-qqq-compare",pct(qqq));
    const currentCohort=data.source_kind==="ISOLATED_100_GENERATION_DEVELOPMENT";
    const runCount=currentCohort ? data.additional_completed : data.completed;
    const runTarget=currentCohort ? data.additional_target : data.requested;
    updateText("perf-progress",runCount+" / "+runTarget);
    const progress=runTarget ? Math.max(0,Math.min(100,runCount/runTarget*100)):0;
    byId("perf-progress-fill").style.width=progress.toFixed(1)+"%";
    updateText("perf-progress-pct",progress.toFixed(0)+"% 완료");
    updateText("perf-cohort",currentCohort
      ? "전체 원장 G"+data.completed+"/G"+data.requested+" · 기준 G452 보존"
      : "추가 "+data.additional_completed+" / "+data.additional_target+"세대");
    updateText("perf-positive","양수 "+data.positive_count+" / "+data.completed+"세대");
    updateText("perf-mean-mdd","전체 평균 MDD "+pct(data.avg_mdd));
    updateText("perf-last-gen",data.last?"G"+data.last.generation:"—");
    updateText("perf-last-return",data.last?pct(data.last.return):"—");
    const finished=data.completed>=data.requested && data.requested>0;
    updateText("perf-status",finished?"실험 완료":data.research_running_confirmed?"세대 실험 진행 중":"연구 중단 · 확인 필요");
    updateText("perf-updated","자료 동기화 "+new Date(data.fetched_at).toLocaleTimeString("ko-KR"));
    const subset=windowSize==="all" ? records : records.slice(-Number(windowSize));
    renderReturns(data,subset);
    renderRisk(subset);
    updateConnection(data,true);
  }

  function updateConnection(data,available) {
    const put=(id,value)=>updateText(id,value);
    put("connect-api",available?"접속 정상":"접속 실패");
    if(!available) return;
    put("connect-research","G"+data.completed+"/"+data.requested+" · "+data.phase);
    put("connect-evidence",data.proof_chain_ok?"연결 정상":"검증 실패 · 점검 필요");
    put("connect-runner",data.completed>=data.requested?"완료 · 실행 불필요":
      data.research_running_confirmed?"실행 프로세스 확인":"연구 프로세스 미실행");
    put("connect-updated",new Date(data.fetched_at).toLocaleString("ko-KR"));
  }

  let busy=false;
  async function refresh() {
    if(busy)return;
    busy=true;
    try {
      const response=await fetch("api/status",{cache:"no-store",credentials:"same-origin"});
      if(!response.ok)throw new Error("status "+response.status);
      render(await response.json());
    } catch (error) {
      updateText("perf-status","연구 데이터 연결 실패");
      updateText("perf-updated","이전 데이터를 표시 중");
      updateConnection(null,false);
    } finally {busy=false;}
  }

  const dialog=byId("connection-dialog");
  byId("connection-toggle").addEventListener("click",()=> {
    if(dialog.showModal)dialog.showModal();
    else dialog.setAttribute("open","");
    refresh();
  });
  byId("connection-close").addEventListener("click",()=> {
    if(dialog.close)dialog.close();
    else dialog.removeAttribute("open");
  });
  byId("connection-recheck").addEventListener("click",refresh);
  document.querySelectorAll("[data-perf-window]").forEach((button)=> {
    button.addEventListener("click",()=> {
      windowSize=button.dataset.perfWindow;
      document.querySelectorAll("[data-perf-window]").forEach((peer)=>{
        const selected=peer===button;
        peer.classList.toggle("is-active",selected);
        peer.setAttribute("aria-pressed",String(selected));
      });
      if(latest)render(latest);
    });
  });
  refresh();
  setInterval(refresh,5000);
})();
