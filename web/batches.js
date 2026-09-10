function validScore(j){return j.analysis?.scoring_version===2&&j.analysis.profile_version===state.profile.version?j.analysis.score:null;}
function batchJobs(){return state.jobs.filter(j=>selectedBatch&&j.batch_id===selectedBatch).sort((a,b)=>(validScore(b)??-1)-(validScore(a)??-1));}
function openBatch(id){selectedBatch=id;$('nav-workbench').disabled=!id;selected=batchJobs()[0]?.id||null;filter='all';$('search').value='';renderList();renderDetail();navigate('workbench');const b=state.batches.find(b=>b.id===id);$('workbench-title').textContent=b?.name||'手动导入岗位';$('workbench-subtitle').textContent='仅显示本批次岗位，按当前简历匹配分降序排列。';}
function renderBatches(){
 const list=$('batch-list');list.replaceChildren();
 $('batch-total').textContent=`${state.batches.length} 个批次 · ${state.jobs.length} 个岗位`;
 if(!state.batches.length){const empty=el('div',undefined,'empty');empty.append(el('h2','从一次筛选开始'),el('p','在 BOSS 职位页筛选岗位，打开读取插件，设置成功新增数量并开始导入。'),button('手动导入一个岗位',()=>{openBatch(null);toggleImport(true);},'primary'));list.append(empty);return;}
 for(const b of state.batches){
  const row=el('section',undefined,'batch-row');const info=el('div',undefined,'batch-info');
  info.append(el('h2',b.name),el('p',new Date(b.created_at).toLocaleString('zh-CN'),'small muted'));
  if(b.source_url){const u=new URL(b.source_url),q=u.searchParams.get('query');if(q)info.append(el('span',q,'badge'));}
  const progress=el('div',undefined,'batch-progress');progress.append(el('strong',`${b.count} / ${b.target}`),el('span','成功新增','small muted'));
  const bar=el('progress');bar.max=b.target;bar.value=b.count;bar.setAttribute('aria-label',`${b.name}成功新增进度`);progress.append(bar);
  const jobs=state.jobs.filter(j=>j.batch_id===b.id),done=jobs.filter(j=>validScore(j)!==null).length;
  const running=['running','stopping'].includes(b.matching?.status),view=batchDisplay(b,done);
  progress.append(el('span',view.collectionLabel,'badge'));
  if(view.collectionMessage){const reason=el('details',undefined,'collection-note');reason.append(el('summary','查看采集说明'),el('p',view.collectionMessage,'small muted'));progress.append(reason);}
  const status=el('div',undefined,'batch-state');status.append(el('strong',view.matchingLabel),el('p',view.matchingMessage,'small muted'));
  const actions=el('div',undefined,'batch-actions');actions.append(button('查看岗位清单',()=>openBatch(b.id),'primary'));
  const match=button(running?'停止匹配':done===b.count&&done?'匹配已完成':done?'继续匹配':'开始匹配',async()=>{try{await api(running?'/api/batches/cancel-analysis':'/api/batches/analyze',{id:b.id});await refresh(false);notify(running?'当前模型请求结束后停止。':'开始逐个匹配，将使用已配置的模型服务。');}catch(e){notify(e.message,true);}});
  match.disabled=b.status==='collecting'||!b.count||!state.model.configured||!state.profile.facts.length||b.matching?.status==='stopping'||(!running&&done===b.count);
  actions.append(match);row.append(info,progress,status,actions);list.append(row);
 }
}
