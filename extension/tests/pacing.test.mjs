import test from 'node:test';
import assert from 'node:assert/strict';
import * as collector from '../collector.mjs';
const pacing=await import('../pacing.mjs').catch(()=>({}));
test('waits a new random interval after each read and rests at the segment boundary',async()=>{
 assert.equal(typeof pacing.createPacer,'function');
 let time=0;const random=[0,0.99,0.5];const state={};
 const p=pacing.createPacer({minSeconds:3,maxSeconds:5,restEvery:3,restSeconds:60},state,{now:()=>time,random:()=>random.shift(),sleep:async ms=>{time+=ms;}});
 await p.wait();assert.equal(time,0);
 p.recordAttempt();await p.wait();assert.equal(time,3000);
 p.recordAttempt();await p.wait();assert.equal(time,8000);
 p.recordAttempt();await p.wait();assert.equal(time,68000);
});
test('pause interrupts a rest and reopening preserves the remaining deadline',async()=>{
 assert.equal(typeof pacing.createPacer,'function');
 let time=0,stop=false;const state={};const settings={minSeconds:3,maxSeconds:5,restEvery:1,restSeconds:60};
 const p=pacing.createPacer(settings,state,{now:()=>time,sleep:async ms=>{time+=ms;stop=true;},stopped:()=>stop});
 p.recordAttempt();await p.wait();assert.ok(time<1000);
 const restored=JSON.parse(JSON.stringify(state));time=20000;
 const resumed=pacing.createPacer(settings,restored,{now:()=>time,sleep:async ms=>{time+=ms;}});
 await resumed.wait();assert.equal(time,60000);
});
test('rejects reversed intervals before a collection can begin',()=>{
 assert.equal(typeof pacing.validateTiming,'function');
 assert.throws(()=>pacing.validateTiming({minSeconds:5,maxSeconds:3,restEvery:10,restSeconds:60}),/最小.*最大/);
});
test('consecutive duplicate pages wait between loads and count toward the segment rest',async()=>{
 assert.equal(typeof collector.advanceWithPacing,'function');
 let time=0;const events=[],saved=[];const state={};
 const pacer=pacing.createPacer({minSeconds:3,maxSeconds:5,restEvery:2,restSeconds:60},state,{now:()=>time,random:()=>0,sleep:async ms=>{time+=ms;}});
 for(let page=0;page<2;page++)await collector.advanceWithPacing({pacer,advance:async()=>events.push(['load',time]),stopped:()=>false,save:async()=>saved.push({...state})});
 events.push(['read-new-job',time]);
 assert.deepEqual(events,[['load',0],['load',3000],['read-new-job',63000]]);
 assert.equal(saved[1].phase,'rest');assert.equal(saved[1].dueAt,63000);
});
test('pausing during a pending interval prevents the next duplicate-page load',async()=>{
 assert.equal(typeof collector.advanceWithPacing,'function');
 let time=0,stop=false,loads=0;
 const pacer=pacing.createPacer({minSeconds:3,maxSeconds:5,restEvery:10,restSeconds:60},{dueAt:3000,phase:'interval'},{now:()=>time,sleep:async ms=>{time+=ms;stop=true;},stopped:()=>stop});
 const result=await collector.advanceWithPacing({pacer,advance:async()=>{loads++;},stopped:()=>stop,save:async()=>{}});
 assert.equal(loads,0);assert.equal(result,false);
});
