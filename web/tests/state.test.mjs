import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import fs from 'node:fs';
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync(new URL('../state.js',import.meta.url),'utf8'),ctx);
test('background matching preserves unsaved greeting edits',()=>{const edit={draft:'用户尚未保存的文本',dirty:true};const edits=new Map([['a',edit]]);const previous={profile:{version:1},jobs:[{id:'a',draft:'old'}]},fresh={profile:{version:1},jobs:[{id:'a',draft:'old',analysis:{score:80}}]};assert.equal(typeof ctx.syncDraftEdits,'function');ctx.syncDraftEdits(edits,previous,fresh);assert.equal(edits.get('a'),edit);});
test('resume change invalidates old edits',()=>{const edits=new Map([['a',{draft:'old',dirty:true}]]);assert.equal(typeof ctx.syncDraftEdits,'function');ctx.syncDraftEdits(edits,{profile:{version:1},jobs:[]},{profile:{version:2},jobs:[]});assert.equal(edits.size,0);});
test('paused collection message stays separate from running matching',()=>{
 assert.equal(typeof ctx.batchDisplay,'function');
 const view=ctx.batchDisplay({status:'paused',message:'请保持在已筛选的 BOSS 职位搜索页',count:31,matching:{status:'running'}},2);
 assert.equal(view.collectionLabel,'采集已暂停');
 assert.match(view.collectionMessage,/BOSS/);
 assert.equal(view.matchingLabel,'正在匹配 2 / 31');
 assert.doesNotMatch(view.matchingMessage,/请保持/);
 assert.match(view.matchingMessage,/无需打开 BOSS/);
});
