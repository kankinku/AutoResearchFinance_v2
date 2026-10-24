// Mock-DOM browser smoke for actual ORIGINAL+performance JavaScript and live read-only API.
// Node built-ins only, no untrusted browser plugin/network requests.
"use strict";
const assert=require("node:assert/strict");
const vm=require("node:vm");
const http=require("node:http");

// Node undici's global fetch is unstable with this HTTP/1.0 local test server.
// Use an explicit buffered request so the DOM simulation exercises the
// complete real response deterministically without mutating the server.
function request(url, options={}) {
  return new Promise((resolve,reject)=>{
    const req=http.request(url,{method:options.method||"GET",headers:{"Cache-Control":"no-store"}},res=>{
      const chunks=[];
      res.on("data",chunk=>chunks.push(chunk));
      res.on("error",reject);
      res.on("end",()=>{
        const body=Buffer.concat(chunks).toString("utf8");
        resolve({ok:res.statusCode>=200&&res.statusCode<300,status:res.statusCode,
          text:async()=>body,json:async()=>JSON.parse(body)});
      });
    });
    req.on("error",reject);
    req.end();
  });
}
async function scenario(file) {
  const base="http://127.0.0.1:8082/";
  const els=new Map(),handlers=new Map(),errs=[];
  function make(id) {
    if(!els.has(id)) {
      let opened=false;
      els.set(id,{
        id,dataset:{},value:"",hidden:false,disabled:false,textContent:"",
        innerHTML:"",className:"",attributes:{},style:{},
        classList:{toggle(){},add(){},remove(){}},
        addEventListener(event,cb){handlers.set(id+":"+event,cb);},
        setAttribute(k,v){this.attributes[k]=v;},
        removeAttribute(k){delete this.attributes[k];},
        showModal(){opened=true;this.attributes.open="";},
        close(){opened=false;delete this.attributes.open;},
        get open(){return opened;},
      });
    }
    return els.get(id);
  }
  const filters=["all","30","50","100"].map((n)=>{
    const node=make("filter-"+n);
    node.dataset.perfWindow=n;
    return node;
  });
  const ctx=vm.createContext({
    document:{
      getElementById:make,
      querySelectorAll:(selector)=>selector==="[data-perf-window]"?filters:[],
    },
    navigator:{clipboard:{writeText:async()=>undefined}},
    fetch:async (url,options)=>{
      const response=await request(new URL(url,base),options);
      if(!response.ok)errs.push(response.status+" "+url);
      return response;
    },
    Date,Math,Number,String,Object,Array,JSON,Promise,
    console:{log(){},warn(...x){errs.push(x.join(" "));},error(...x){errs.push(x.join(" "));}},
    setTimeout(){},setInterval(){}
  });
  const sources=file==="app.js"
    ?["labels.js","app.js","fresh-performance.js"]
    :["labels.js","backtest.js"];
  for(const name of sources){
    const response=await request(new URL("static/"+name,base));
    assert.equal(response.status,200,name);
    vm.runInContext(await response.text(),ctx,{filename:name});
  }
  await new Promise(resolve=>setTimeout(resolve,1300));
  assert.equal(make("api-state").textContent,"정상 연결",file);
  const active=await (await request(new URL("api/status",base))).json();
  assert.equal(active.requested,100);
  assert.equal(active.additional_target,100);
  assert.equal(active.source_kind,"GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT");
  assert.ok(active.completed>=68 && active.completed<=100);
  if(file==="app.js") {
    assert.equal(make("perf-progress").textContent,active.completed+" / "+active.requested);
    assert.equal(make("perf-cohort").textContent,
      "추가 "+active.additional_completed+" / "+active.additional_target+"세대");
    assert.match(make("perf-cohort-label").textContent,/GPT 작성 MCP/);
    assert.equal(make("perf-qqq-return").textContent,"187.77%");
    assert.match(make("perf-best-return").textContent,/%$/);
    assert.match(make("perf-qqq-return").textContent,/%$/);
    assert.match(make("perf-excess").textContent,/%p$/);
    assert.match(make("perf-best-mdd").textContent,/%$/);
    assert.match(make("perf-return-chart").innerHTML,/<path /);
    assert.match(make("perf-risk-chart").innerHTML,/<path /);
    assert.match(make("perf-status").textContent,/세대 실험 진행 중|실험 완료|GPT 전략 계획 대기|GPT 진단 대기/);
    assert.equal(make("connect-evidence").textContent,"연결 정상");
    assert.equal(typeof handlers.get("connection-toggle:click"),"function");
    handlers.get("connection-toggle:click")();
    assert.equal(make("connection-dialog").open,true);
    handlers.get("connection-close:click")();
    assert.equal(make("connection-dialog").open,false);
    handlers.get("filter-30:click")();
    assert.equal(make("filter-30").attributes["aria-pressed"],"true");
    assert.match(make("perf-return-summary").textContent,/G[0-9]+~G[0-9]+/);
    assert.equal(typeof handlers.get("refresh:click"),"function");
    await handlers.get("refresh:click")();
    await new Promise(resolve=>setTimeout(resolve,300));
    assert.equal(make("refresh").disabled,false);
  } else {
    assert.equal(make("generation-progress-copy").textContent,
      active.completed+" / "+active.requested+"세대 완료");
    assert.notEqual(make("best-strategy-cagr").textContent,"—");
    assert.notEqual(make("best-qqq-cagr").textContent,"—");
  }
  assert.deepEqual(errs,[],file);
  console.log(file,make("api-state").textContent,
    make("perf-progress").textContent||make("generation-progress-copy").textContent);
}
(async()=>{await scenario("app.js");await scenario("backtest.js")})()
 .catch(error=>{console.error(error);process.exitCode=1;});
