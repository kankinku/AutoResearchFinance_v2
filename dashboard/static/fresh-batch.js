/* Independent, read-only deterministic batch tracker. Never blends GPT cohorts. */
(function () {
  "use strict";
  const byId=id=>document.getElementById(id);
  const put=(id,value)=>{byId(id).textContent=String(value);};
  const chart=byId("batch-candidate-chart");
  function renderBatch(payload) {
    const b=payload.batch;
    if(!b) {put("batch-status","연구 배치 없음");return;}
    const progress=b.requested>0 ? Math.max(0,Math.min(100,b.completed/b.requested*100)):0;
    put("batch-status",b.status);
    put("batch-progress",b.completed+" / "+b.requested);
    put("batch-source","배치 "+b.batch_id.slice(0,12)+" · "+b.status);
    put("batch-candidates",b.candidates_evaluated);
    put("batch-duplicates",b.duplicate_skipped);
    put("batch-promoted",b.promoted);
    put("batch-rejected","평가 탈락 "+b.rejected+"개");
    put("batch-integrity",b.checkpoints_consistent ?
      "세대 원장 일치 · 고정 파라미터 탐색 · 개발 데이터 전용" :
      "경고: 완료 세대 수와 저장된 원장 불일치");
    put("batch-updated","최근 조회 "+new Date(payload.generated_at).toLocaleTimeString("ko-KR"));
    byId("batch-progress-fill").style.width=progress.toFixed(1)+"%";
    const recent=b.generations.slice(-40);
    if(!recent.length) {chart.innerHTML="";return;}
    const max=Math.max(1,...recent.map(g=>Number(g.candidates_evaluated)));
    const width=840/recent.length;
    const bars=recent.map((g,i)=>{
      const h=90*g.candidates_evaluated/max;
      const x=40+i*width+2,y=110-h;
      return '<rect x="'+x.toFixed(2)+'" y="'+y.toFixed(2)+'" width="'+
        Math.max(2,width-4).toFixed(2)+'" height="'+h.toFixed(2)+
        '" fill="#3774aa"><title>G'+Number(g.generation)+': 후보 '+
        Number(g.candidates_evaluated)+'개</title></rect>';
    });
    chart.innerHTML='<text x="8" y="20" fill="#667588" font-size="12">'+max+
      '</text>'+bars.join("")+'<text x="40" y="131" fill="#667588" font-size="12">G'+
      Number(recent[0].generation)+'</text><text x="880" y="131" text-anchor="end" fill="#667588" font-size="12">G'+
      Number(recent[recent.length-1].generation)+'</text>';
  }
  let busy=false;
  async function refreshBatch() {
    if(busy)return;
    busy=true;
    try {
      const response=await fetch("api/research-batches/latest",{cache:"no-store",credentials:"same-origin"});
      if(!response.ok)throw new Error("batch-status "+response.status);
      renderBatch(await response.json());
    } catch(_error) {
      put("batch-status","배치 조회 실패");
      put("batch-updated","이전 수치 표시 중 · 연결 확인 필요");
    } finally {busy=false;}
  }
  refreshBatch();
  setInterval(refreshBatch,5000);
})();
