// Mock DOM smoke: runs the exact browser-served original scripts against live SQLite APIs.
'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm');
async function test(file) {
 const base='http://127.0.0.1:8082/';
 const els=new Map();const handlers=new Map();const errs=[];
 const el=id=>{
  if(!els.has(id))els.set(id,{id,style:{},dataset:{},value:'',hidden:false,
   disabled:false,textContent:'',innerHTML:'',className:'',
   classList:{toggle(){},add(){},remove(){}},
   addEventListener(event,fn){handlers.set(id+':'+event,fn);}
  });
  return els.get(id);
 };
 const ctx=vm.createContext({
  document:{getElementById:el,querySelectorAll:()=>[]},
  navigator:{clipboard:{writeText:async()=>undefined}},
  fetch:async (url,options)=>{
   const result=await fetch(new URL(url,base),options);
   if(!result.ok)errs.push(String(result.status)+' '+url);
   return result;
  },
  Date,Math,Number,String,Object,Array,JSON,Promise,
  console:{log(){},warn(){},error(){}},
  setTimeout(){},setInterval(){}
 });
 for(const name of ['labels.js',file]){
  const response=await fetch(new URL('static/'+name,base));
  assert.equal(response.status,200);
  vm.runInContext(await response.text(),ctx,{filename:name});
 }
 await new Promise(r=>setTimeout(r,800));
 assert.equal(el('api-state').textContent,'정상 연결');
 if(file==='app.js'){
  assert.match(el('academic-progress').textContent,/^[0-9]+ \/ 152$/);
  assert.equal(el('academic-evidence').textContent,'검증 통과');
  assert.equal(typeof handlers.get('refresh:click'),'function');
  await handlers.get('refresh:click')();
  await new Promise(r=>setTimeout(r,200));
  assert.equal(el('refresh').disabled,false);
 } else {
  assert.match(el('generation-progress-copy').textContent,/^[0-9]+ \/ 152세대 완료$/);
  assert.notEqual(el('best-strategy-cagr').textContent,'—');
  assert.notEqual(el('best-qqq-cagr').textContent,'—');
 }
 assert.deepEqual(errs,[]);
 console.log(file,el('api-state').textContent,el('academic-progress').textContent||el('generation-progress-copy').textContent);
}
(async()=>{await test('app.js');await test('backtest.js')})().catch(e=>{console.error(e);process.exitCode=1});
