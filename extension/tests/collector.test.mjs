import test from 'node:test';import assert from 'node:assert/strict';
import {collectUntilTarget} from '../collector.mjs';
test('duplicates and failed reads never consume successful target',async()=>{
 let count=0,i=0;const attempts=[];
 const result=await collectUntilTarget({target:2,count:0,next:async()=>['old','broken','one','two','three'][i++]||null,read:async id=>{attempts.push(id);if(id==='broken')throw Error('读取超时');return id;},save:async id=>({count:id==='old'?0:1,batch:{count:id==='old'?count:++count}}),stopped:()=>false,progress:()=>{}});
 assert.equal(result.count,2);assert.deepEqual(attempts,['old','broken','one','two']);assert.equal(result.status,'completed');
});
test('exhaustion retains successful captures',async()=>{let i=0;const r=await collectUntilTarget({target:30,count:0,next:async()=>i++?null:'one',read:async x=>x,save:async()=>({count:1,batch:{count:1}}),stopped:()=>false,progress:()=>{}});assert.equal(r.count,1);assert.equal(r.status,'exhausted');});
test('pause stops before persisting another job',async()=>{let stop=false;const r=await collectUntilTarget({target:2,count:0,next:async()=>'one',read:async x=>{stop=true;return x;},save:async()=>{throw Error('must not persist');},stopped:()=>stop,progress:()=>{}});assert.equal(r.status,'paused');assert.equal(r.count,0);});
test('security verification is reported as a collection pause, not a search-page requirement',async()=>{
 const {collectPage}=await import('../collector.mjs');
 globalThis.location={hostname:'www.zhipin.com',pathname:'/web/common/security-check'};
 globalThis.document={body:{innerText:'安全验证 您的账号可能存在异常访问行为，完成验证后即可正常使用。点击按钮进行验证'}};
 const result=collectPage('list');
 assert.match(result.error,/采集.*暂停/);assert.match(result.error,/安全验证/);assert.doesNotMatch(result.error,/请保持/);
});
test('pause during the pacing wait prevents advancing or opening another job',async()=>{
 let stop=false,advances=0;
 const result=await collectUntilTarget({target:2,count:1,beforeNext:async()=>{stop=true;},next:async()=>{advances++;return null;},read:async()=>{},save:async()=>{},stopped:()=>stop,progress:()=>{}});
 assert.equal(advances,0);assert.equal(result.status,'paused');assert.equal(result.count,1);
});
