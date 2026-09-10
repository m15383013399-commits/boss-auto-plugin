import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import fs from 'node:fs';
// Exercise the app handlers with a small DOM adapter; no browser or model requests.
class Node {
 constructor(){this.children=[];this.value='';this.hidden=false;this.tagName='DIV';this.content='test-key';this.elements={title:{focus(){}}};this.classList={toggle(){}};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 setAttribute(){}removeAttribute(){}addEventListener(name,fn){this['on'+name]=fn;}querySelector(){return new Node();}focus(){}
}
async function app(){
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const fresh={profile:{version:1,facts:[]},model:{configured:false},preferences:{},batches:[{id:'a',name:'批次 A',count:1,target:1,status:'completed'},{id:'b',name:'批次 B',count:1,target:1,status:'completed'},{id:'empty',name:'空批次',count:0,target:1,status:'paused'}],jobs:[{id:'jb',batch_id:'b',title:'B 岗位',status:'new'},{id:'ja',batch_id:'a',title:'A 岗位',status:'new'}]};
 const ctx=vm.createContext({document:{getElementById:get,querySelector:get,createElement:()=>new Node(),activeElement:null},fetch:async()=>({ok:true,json:async()=>fresh}),setInterval(){},setTimeout(){},clearTimeout(){},URL,console});
 for(const file of ['state.js','batches.js','app.js'])vm.runInContext(fs.readFileSync(new URL('../'+file,import.meta.url),'utf8'),ctx);
 await ctx.refresh();return {ctx,get,fresh};
}
test('current-batch navigation and refresh never bring back jobs from another batch',async()=>{
 const {ctx,get}=await app();ctx.openBatch('a');get('nav-workbench').onclick();await ctx.refresh(false);
 assert.deepEqual(Array.from(ctx.batchJobs(),j=>j.id),['ja']);assert.equal(get('workbench-title').textContent,'批次 A');
 assert.equal(get('job-list').children.length,1);assert.equal(get('job-list').children[0].children[0].textContent,'A 岗位');
});
test('an empty batch stays empty after refresh, including its detail panel',async()=>{
 const {ctx,get}=await app();ctx.openBatch('empty');await ctx.refresh(false);
 assert.deepEqual(Array.from(ctx.batchJobs(),j=>j.id),[]);
 assert.equal(vm.runInContext('selected',ctx),null);
 assert.notEqual(get('detail').children[0]?.children[0]?.textContent,'B 岗位');
});
test('without a selected batch no global job list is exposed',async()=>{
 const {ctx}=await app();assert.deepEqual(Array.from(ctx.batchJobs(),j=>j.id),[]);
});
