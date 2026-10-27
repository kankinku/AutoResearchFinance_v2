"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");

(async()=>{
  const elements=new Map();
  const el=id=>{
    if(!elements.has(id)) elements.set(id,{textContent:"",innerHTML:"",style:{}});
    return elements.get(id);
  };
  const payload={
    generated_at:"2026-10-27T03:20:00Z",research_type:"FIXED_PARAMETER_BACKTEST_NOT_GPT_EVOLUTION",
    orders_enabled:false,
    batch:{batch_id:"123456789abcdef",status:"RUNNING",requested:10,completed:2,
      candidates_evaluated:13,duplicate_skipped:3,rejected:13,promoted:0,
      checkpoints_consistent:true,generations:[
        {generation:1,candidates_evaluated:8},{generation:2,candidates_evaluated:5}]}
  };
  let timer,requests=0;
  const ctx=vm.createContext({
    document:{getElementById:el},
    fetch:async(url,options)=>{
      requests++;
      assert.equal(url,"api/research-batches/latest");
      assert.equal(options.cache,"no-store");
      return {ok:true,json:async()=>payload};
    },
    setInterval: (fn,ms)=>{assert.equal(ms,5000);timer=fn;},
    Date,Number,Math,String,Object,Array,Promise,JSON,
  });
  vm.runInContext(fs.readFileSync("dashboard/static/fresh-batch.js","utf8"),ctx);
  await new Promise(setImmediate);
  assert.equal(el("batch-progress").textContent,"2 / 10");
  assert.equal(el("batch-candidates").textContent,"13");
  assert.equal(el("batch-duplicates").textContent,"3");
  assert.equal(el("batch-progress-fill").style.width,"20.0%");
  assert.match(el("batch-candidate-chart").innerHTML,/G2: 후보 5개/);
  payload.batch.completed=10;
  payload.batch.status="COMPLETED";
  payload.batch.candidates_evaluated=68;
  payload.batch.duplicate_skipped=12;
  payload.batch.rejected=68;
  payload.batch.generations=Array.from({length:10},(_,i)=>({generation:i+1,candidates_evaluated:i+1}));
  timer();
  await new Promise(setImmediate);
  assert.equal(el("batch-progress").textContent,"10 / 10");
  assert.equal(el("batch-candidates").textContent,"68");
  assert.equal(el("batch-status").textContent,"COMPLETED");
  assert.equal(el("batch-progress-fill").style.width,"100.0%");
  assert.equal(requests,2);
  console.log("batch browser smoke PASS: 2/10 -> 10/10 via polling");
})().catch(e=>{console.error(e);process.exitCode=1;});
