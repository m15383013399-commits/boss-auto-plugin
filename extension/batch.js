import {collectUntilTarget,collectPage,advanceWithPacing} from './collector.mjs';
import {createPacer,defaultTiming,validateTiming} from './pacing.mjs';
import {readCurrentJob} from './reader.mjs';import {normalizeCapture} from './extract.mjs';
const $=id=>document.getElementById(id),base='http://127.0.0.1:8765';
const tabId=Number(new URL(location.href).searchParams.get('tab'));
let session=null,running=false,halt=false,stopRequested=false,localKey='';
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const timingFields={minSeconds:'interval-min',maxSeconds:'interval-max',restEvery:'rest-every',restSeconds:'rest-seconds'};
function readTiming(){return validateTiming(Object.fromEntries(Object.entries(timingFields).map(([key,id])=>[key,Number($(id).value)])));}
function fillTiming(value){for(const [key,id] of Object.entries(timingFields))$(id).value=value[key];}
async function api(path,body){const r=await fetch(base+path,{method:body===undefined?'GET':'POST',headers:{'X-Local-Key':localKey,...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(12000)});const v=await r.json();if(!r.ok)throw Error(v.error||'本机工作台未响应');return v;}
async function page(func,args=[]){const r=await chrome.scripting.executeScript({target:{tabId},world:'MAIN',func,args});if(r[0]?.error)throw Object.assign(Error('无法读取岗位页面'),{fatal:true});const v=r[0]?.result;if(!v||v.error)throw Object.assign(Error(v?.error||'读取权限已失效，请回到 BOSS 页面重新打开插件'),{fatal:true});return v;}
function signature(url){const u=new URL(url);u.searchParams.delete('page');u.searchParams.delete('ka');return u.origin+u.pathname+'?'+[...u.searchParams].sort().map(([k,v])=>k+'='+v).join('&');}
function show(message){$('progress').textContent=session?`成功新增 ${session.count} / ${session.target}`:'准备开始';$('bar').max=session?.target||30;$('bar').value=session?.count||0;$('status').textContent=message;$('start').disabled=running;$('name').disabled=running;$('target').disabled=running;for(const id of Object.values(timingFields))$(id).disabled=running;$('pause').hidden=!running;$('stop').hidden=!session||session.count>=session.target||stopRequested;$('resume').hidden=running||!session||session.count>=session.target||stopRequested;}
async function saveSession(){await chrome.storage.local.set({batchSession:session});}
async function runSession(){
 if(running)return;running=true;halt=false;stopRequested=false;show('准备读取岗位…');
 let currentId=null;
 let finalStatus='paused',message='已暂停，成功新增的岗位已保存';
 try{
  session.timing=readTiming();session.pacing??={};await saveSession();
  await chrome.storage.local.set({collectionTiming:session.timing});
  const pacer=createPacer(session.timing,session.pacing,{stopped:()=>halt,onTick:(phase,seconds)=>show(`${phase==='rest'?'分段休息':'采集间隔'} · ${seconds} 秒后继续，可随时暂停`)});
  const state=await api('/api/state');const b=state.batches.find(b=>b.id===session.id);if(!b)throw Error('批次不存在');session.count=b.count;
  await api('/api/batches/status',{id:session.id,status:'collecting'});
  const known=new Set((await api('/api/known')).urls),visited=new Set();let pending=[],last='';
  async function scan(){const v=await page(collectPage,['list']);if(signature(v.url)!==session.signature)throw Object.assign(Error('筛选条件已改变，请新建批次或恢复原筛选后继续'),{fatal:true});return v.items;}
  const result=await collectUntilTarget({target:session.target,count:session.count,stopped:()=>halt,
   beforeNext:()=>pacer.wait(),
   next:async()=>{
    while(!halt){
     if(!pending.length){let items=await scan();pending=items.filter(j=>!visited.has(j.id)&&!known.has(j.url));
      if(!pending.length){const before=items.map(j=>j.id).join('|');show('当前列表没有未导入岗位，准备加载后续岗位…');
       if(!await advanceWithPacing({pacer,advance:()=>page(collectPage,['advance']),stopped:()=>halt,save:saveSession}))return null;
       for(let n=0;n<8&&!halt;n++){await wait(750);items=await scan();if(items.map(j=>j.id).join('|')!==before)break;}
       pending=items.filter(j=>!visited.has(j.id)&&!known.has(j.url));
       if(!pending.length&&(last===before||items.map(j=>j.id).join('|')===before))return null;last=before;continue;
      }
     }
     const item=pending.shift();currentId=item.id;visited.add(item.id);return item;
    }return null;
   },read:async item=>{
    show('正在读取：'+item.title);await scan();if(halt)return;
    try{
    await page(collectPage,['open',item.id]);
    let lastError='岗位详情未完成加载';
    for(let n=0;n<14&&!halt;n++){await wait(800);await scan();try{const raw=await page(readCurrentJob);const j=normalizeCapture(raw);if(j.job_id===item.id){await wait(1000);return j;}}catch(e){lastError=e.message;if(/验证|登录|权限|筛选条件/.test(lastError))throw e;}}
    throw Error(lastError);
    }finally{pacer.recordAttempt();await saveSession();}
   },save:async job=>{const r=await api('/api/import',{jobs:[job],batch_id:session.id});known.add(job.source_url);return r;},progress:async(count,msg)=>{currentId=null;session.count=count;await saveSession();show(msg);}});
  session.count=result.count;finalStatus=stopRequested?'stopped':result.status;
  message=finalStatus==='completed'?'已完成目标，前往工作台进行匹配验证':finalStatus==='exhausted'?'当前列表未加载出更多岗位，已保留成果；可加载后续岗位再继续':stopRequested?'本批次已停止，成功新增的岗位已保留':'已暂停，可以继续导入';
 }catch(e){message=e.message||'导入暂停，请检查页面与本机服务';}
 finally{
  running=false;
  try{const r=await api('/api/batches/status',{id:session.id,status:finalStatus==='completed'?'paused':finalStatus,message});session.count=r.count;}catch{}
  await saveSession();show(message);
 }
}
async function exclusive(action){return navigator.locks.request('targeted-apply-import',{ifAvailable:true},async lock=>{if(!lock){show('已有导入任务正在运行，请回到原控制页操作');return;}return action();});}
async function run(){return exclusive(()=>runSession());}
$('start').onclick=async()=>exclusive(async()=>{try{const target=Number($('target').value);if(!Number.isInteger(target)||target<1||target>200)throw Error('请输入 1–200 的成功新增目标');const timing=readTiming();const v=await page(collectPage,['list']);const b=await api('/api/batches',{target,name:$('name').value.trim()||'职位搜索 · '+new Date().toLocaleDateString('zh-CN'),source_url:v.url});session={id:b.id,tabId,target,count:0,signature:signature(v.url),timing,pacing:{}};await saveSession();await runSession();}catch(e){show(e.message);}});
$('resume').onclick=()=>run();$('pause').onclick=()=>{halt=true;show('正在暂停，当前岗位处理结束后停止');};$('stop').onclick=async()=>{stopRequested=true;halt=true;if(!running){await api('/api/batches/status',{id:session.id,status:'stopped'});show('本批次已停止');}};
try{const v=await chrome.storage.local.get(['localKey','batchSession','collectionTiming']);localKey=v.localKey||'';if(!localKey)throw Error('请先在插件中保存本机连接密钥');if(v.batchSession?.tabId===tabId){session=v.batchSession;const b=(await api('/api/state')).batches.find(b=>b.id===session.id);if(b){session.count=b.count;stopRequested=b.status==='stopped';$('target').value=b.target;$('name').value=b.name;}else session=null;}fillTiming({...defaultTiming,...(session?.timing||v.collectionTiming)});show('准备就绪。开始后请保留这两个标签页。');}catch(e){show(e.message);}
