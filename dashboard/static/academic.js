/* Read-only 3-second polling; no model submission, mutations or external scripts. */
"use strict";
const $ = id => document.getElementById(id);
let selected = null, busy = false;
const pct = x => typeof x === "number" && Number.isFinite(x) ? (100*x).toFixed(2)+"%" : "—";
const num = (x,d=3) => typeof x === "number" && Number.isFinite(x) ? x.toFixed(d) : "—";
const write = (id,v) => {$(id).textContent = v ?? "—";};
function valueCards(prefix,row) {
 const m=row?.metrics||{};
 write(prefix+"-return",pct(m.total_return));write(prefix+"-dd",pct(m.max_drawdown));
 write(prefix+"-sharpe",num(m.sharpe));write(prefix+"-trades",m.trade_count??"—");
 $(prefix+"-return").className=(typeof m.total_return==="number"&&m.total_return<0)?"negative":"positive";
}
function updateInfo(d){
 const phase=d.checkpoint?.code||"UNKNOWN";
 write("phase-status",d.checkpoint?.label||"상태 확인 불가");
 $("phase-status").className="phase"+(phase==="RUNNING"?" active":["INTERRUPTED","FAILED","CANCELLED"].includes(phase)?" terminal":"");
 const descriptions={AWAITING_PLAN:"다음 계획 입력 대기 — 실제 연구 실행 중이 아닙니다.",AWAITING_DIAGNOSIS:"진단 제출을 기다립니다 — 실제 연구 실행 중이 아닙니다.",RUNNING:"연구 원장이 계산 중으로 표시됩니다. 별도 작업자 heartbeat는 확인되지 않습니다.",INTERRUPTED:"연구가 중단되었습니다.",COMPLETED:"요청된 모든 세대가 완료됐습니다.",CANCELLED:"연구 세션이 취소됐습니다."};
 write("phase-context",descriptions[phase]||"체크포인트 상태를 확인하십시오.");
 write("completed",d.completed);write("requested",d.requested);
 write("progress-percent",num(d.progress_pct,0)+"%");
 $("progress-fill").style.width=Math.min(100,Math.max(0,d.progress_pct))+"%";
 write("remaining","남은 "+(d.requested-d.completed)+"세대");
 write("record-state","S7 미측정 "+d.missing_s7_count+"건 · 읽기 전용");
 const m=d.current_model||{}, staged=m.evaluation_status==="STAGED_NOT_COMMITTED";
 write("current-name",m.plan_id||"모델 없음");
 write("current-tag",staged?"진단 대기":"최근 완료");
 write("current-sub",staged?"제"+m.generation+"세대 · 아직 커밋 전인 모델입니다. 이전 세대 성과를 복사하지 않습니다.":m.generation?"제"+m.generation+"세대에서 확정된 개발 평가":"미완료");
 valueCards("current",staged?null:m);
 const best=d.best_by_return;
 write("best-name",best?.plan_id||"후보 없음");
 write("best-sub",best?"제"+best.generation+"세대 · 최고 누적수익률 (개발기간 기준)":"후보 없음");
 valueCards("best",best);
 write("latest-return",pct(d.latest_completed_model?.metrics?.total_return));
 write("latest-winrate",pct(d.latest_completed_model?.metrics?.win_rate));
 write("best-sharpe-val",num(d.best_by_sharpe?.metrics?.sharpe));
 write("best-sharpe-id",d.best_by_sharpe?.plan_id||"후보 없음");
 write("missing-s7",d.missing_s7_count);
}
function draw(history){
 const svg=$("evolution-chart");
 svg.replaceChildren();
 const ns="http:"+"//"+"www.w3.org/2000/svg";
 function element(tag,attributes={},content=""){
  const e=document.createElementNS(ns,tag);
  Object.entries(attributes).forEach(([k,v])=>e.setAttribute(k,String(v)));
  if(content)e.textContent=content;
  svg.appendChild(e);return e;
 }
 const W=900,H=255,L=60,R=24,T=20,B=36;
 const values=history.flatMap(h=>[100*(h.metrics?.total_return??0),-100*(h.metrics?.max_drawdown??0)]).filter(Number.isFinite);
 const lo=values.length?Math.min(-10,Math.floor(Math.min(...values)/20)*20):-20;
 const hi=values.length?Math.max(10,Math.ceil(Math.max(...values)/20)*20):20;
 const x=i=>L+(history.length<2?(W-L-R)/2:i*(W-L-R)/(history.length-1));
 const y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
 for(let i=0;i<=4;i++){
  const v=lo+(hi-lo)*i/4;
  element("line",{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:"#2c394d"});
  element("text",{x:48,y:y(v)+4,fill:"#8393ac","text-anchor":"end","font-size":11},Math.round(v)+"%");
 }
 if(!history.length){
  element("text",{x:W/2,y:H/2,fill:"#9fb0c6","text-anchor":"middle"},"아직 완료된 세대가 없습니다.");
  return;
 }
 [...new Set([0,Math.floor((history.length-1)/2),history.length-1])].forEach(i=>
  element("text",{x:x(i),y:H-11,fill:"#8393ac","text-anchor":"middle","font-size":11},history[i].generation+"세대")
 );
 const path=fn=>history.map((h,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(fn(h)).toFixed(1)).join(" ");
 element("path",{d:path(h=>100*(h.metrics?.total_return??0)),fill:"none",stroke:"#78dfc3","stroke-width":2.7});
 element("path",{d:path(h=>-100*(h.metrics?.max_drawdown??0)),fill:"none",stroke:"#ad99ec","stroke-width":2.7});
 for(const [v,color] of [[100*(history.at(-1).metrics?.total_return??0),"#78dfc3"],[-100*(history.at(-1).metrics?.max_drawdown??0),"#ad99ec"]]){
  element("circle",{cx:x(history.length-1),cy:y(v),r:4,fill:color});
 }
}
function table(history){
 const body=$("history-rows");body.replaceChildren();
 write("history-count",history.length+"세대");
 if(!history.length){
  const tr=document.createElement("tr"),td=document.createElement("td");
  td.colSpan=8;td.className="empty";td.textContent="저장된 세대가 없습니다.";tr.appendChild(td);body.appendChild(tr);return;
 }
 for(const g of [...history].reverse()){
  const tr=document.createElement("tr");
  const m=g.metrics||{};
  const values=[g.generation,g.plan_id,pct(m.total_return),pct(m.max_drawdown),num(m.sharpe),pct(m.win_rate),m.trade_count??"—",g.s7_status==="MEASURED"?"측정됨":"미측정"];
  values.forEach((value,i)=>{
   const td=document.createElement("td");td.textContent=String(value);
   if(i===1){td.className="model-id";td.title=String(value);}
   if(i===2)td.className=typeof m.total_return==="number"&&m.total_return<0?"negative":"positive";
   if(i===7)td.className=g.s7_status==="MEASURED"?"s7-ok":"s7-warn";
   tr.appendChild(td);
  });
  body.appendChild(tr);
 }
}
function options(sessions){
 const select=$("session-select"),previous=select.value;
 select.replaceChildren();
 for(const s of sessions){
  const option=document.createElement("option");
  option.value=s.session_id;
  option.textContent=s.completed+"/"+s.requested+"세대 · "+s.session_id.slice(0,8)+"… · "+s.status;
  select.appendChild(option);
 }
 if(sessions.some(s=>s.session_id===previous))select.value=previous;
 else if(selected&&sessions.some(s=>s.session_id===selected))select.value=selected;
 selected=select.value||null;
}
async function refresh(){
 if(busy)return;
 busy=true;
 const ctrl=new AbortController(),timeout=setTimeout(()=>ctrl.abort(),5000);
 try{
  const endpoint=selected?"/api/academic/sessions/"+encodeURIComponent(selected):"/api/academic/overview";
  const response=await fetch(endpoint,{cache:"no-store",signal:ctrl.signal});
  if(!response.ok)throw new Error("서버 상태 "+response.status);
  const data=await response.json();
  if(data.status!=="OK")throw new Error("연구 세션을 찾을 수 없습니다");
  options(data.sessions);
  updateInfo(data);draw(data.history);table(data.history);
  write("last-refresh",new Date().toLocaleTimeString("ko-KR"));
  write("conn-status","연구 원장 연결됨");
  $("conn-status").className="chip";
 }catch(err){
  write("conn-status","원장 조회 오류");
  $("conn-status").className="chip chip-danger";
  write("phase-status","조회 실패");
  write("phase-context",String(err.message||err));
 }finally{clearTimeout(timeout);busy=false;}
}
$("session-select").addEventListener("change",event=>{selected=event.target.value;refresh();});
$("reload").addEventListener("click",refresh);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
refresh();
setInterval(()=>{if(!document.hidden)refresh();},3000);
