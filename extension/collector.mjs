/** Successful server insertions, never attempts, own the completion target. */
export async function collectUntilTarget({target,count,next,read,save,stopped,progress,beforeNext=async()=>{}}){
 let consecutiveErrors=0;
 while(count<target&&!stopped()){
  await beforeNext();if(stopped())break;
  const item=await next();if(stopped())break;if(!item)return {count,status:'exhausted'};
  let job;
  try{job=await read(item);consecutiveErrors=0;}catch(e){if(e.fatal||++consecutiveErrors>=3)throw e;await progress(count,'正在继续读取后续岗位');continue;}
  if(stopped())break;
  // A transport failure can have committed on the server: stop and reconcile,
  // rather than guessing a count or losing the ability to retry this job.
  const r=await save(job);count=r.batch?.count??count+r.count;
  await progress(count,'成功新增');
 }
 return {count,status:count>=target?'completed':'paused'};
}

/** Loading another result page is a paced operation even when every job is known. */
export async function advanceWithPacing({pacer,advance,stopped,save}){
 await pacer.wait();if(stopped())return false;
 try{await advance();}finally{pacer.recordAttempt();await save();}
 await pacer.wait();return !stopped();
}

/** Page bridge: normal card clicks and scrolling, no direct BOSS requests. */
export function collectPage(action,id){
 try{
  if(location.hostname!=='www.zhipin.com')return {error:'采集已暂停：请回到 BOSS 职位搜索页后继续采集'};
  const visible=el=>el?.isConnected&&typeof el.getClientRects==='function'&&el.getClientRects().length>0;
  const body=document.body?.innerText||'';
  if(/安全验证|异常访问行为|访问过于频繁|滑动完成验证/.test(body))return {error:'采集已暂停：BOSS 要求安全验证。已保存的岗位可正常匹配；继续采集前请在 BOSS 完成验证。'};
  if(/请先登录/.test(body))return {error:'采集已暂停：请先登录 BOSS。已保存的岗位仍可匹配。'};
  if(location.pathname!=='/web/geek/jobs')return {error:'采集已暂停：请回到已筛选的 BOSS 职位搜索页。已保存的岗位仍可匹配。'};
  const links=Array.from(document.querySelectorAll('a[href*="/job_detail/"]')).filter(a=>visible(a)&&a.closest('.job-card-wrap,.job-card-box,.job-card-wrapper,li')&&!/^查看更多/.test(a.innerText.trim()));
  const items=Array.from(new Map(links.map(a=>{const m=new URL(a.href).pathname.match(/^\/job_detail\/([a-zA-Z0-9_-]+)\.html$/);return m?[m[1],{id:m[1],title:a.innerText.trim(),url:'https://www.zhipin.com/job_detail/'+m[1]+'.html'}]:['',null];})).values()).filter(Boolean);
  if(action==='list')return {items,url:location.href};
  if(action==='open'){
   const a=links.find(a=>new URL(a.href).pathname===`/job_detail/${id}.html`);
   if(!a)return {error:'岗位卡片已变化，请重新开始当前批次'};
   // Clicking the card container uses the site's existing inline-detail handler.
   const card=a.closest('.job-card-wrap,.job-card-box,.job-card-wrapper,li');
   if(!card)return {error:'无法识别岗位卡片容器，请更新读取插件'};
   card.scrollIntoView({block:'nearest'});card.click();return {ok:true};
  }
  if(action==='advance'){
   const next=Array.from(document.querySelectorAll('button,a')).find(e=>visible(e)&&/^(下一页|下页)$/.test((e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||'').trim())&&!e.disabled&&!/disabled/.test(e.className));
   if(next){next.click();return {advanced:true};}
   const last=links.at(-1);if(!last)return {advanced:false};
   last.scrollIntoView({block:'end'});
   for(let p=last.parentElement;p;p=p.parentElement)if(p.scrollHeight>p.clientHeight+50&&['auto','scroll'].includes(getComputedStyle(p).overflowY))p.scrollTop=p.scrollHeight;
   window.scrollTo(0,document.documentElement.scrollHeight);return {advanced:true};
  }
  return {error:'未知读取操作'};
 }catch(e){return {error:e.message||'页面读取失败'};}
}
