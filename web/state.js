function syncDraftEdits(edits,previous,fresh){
 if(previous&&previous.profile.version!==fresh.profile.version){edits.clear();return;}
 for(const job of fresh.jobs){
  const edit=edits.get(job.id);if(edit?.dirty)continue;
  const old=previous?.jobs.find(x=>x.id===job.id);
  if(!old||old.draft!==job.draft||old.reviewed!==job.reviewed)edits.delete(job.id);
 }
}

function batchDisplay(batch,done){
 const collectionLabels={collecting:'正在采集',completed:'采集完成',paused:'采集已暂停',stopped:'采集已停止',exhausted:'本轮采集结束'};
 const matching=batch.matching||{};
 const labels={running:`正在匹配 ${done} / ${batch.count}`,stopping:`正在停止匹配 · 已完成 ${done} / ${batch.count}`,completed:`匹配完成 ${done} / ${batch.count}`,paused:`匹配已暂停 · 已完成 ${done} / ${batch.count}`};
 return {
  collectionLabel:collectionLabels[batch.status]||batch.status,
  collectionMessage:batch.status==='completed'?'':batch.message||'',
  matchingLabel:labels[matching.status]||`尚未匹配 · ${batch.count} 个岗位`,
  matchingMessage:matching.status==='paused'&&matching.message?matching.message:'使用已保存的 JD 和简历，无需打开 BOSS。'
 };
}
