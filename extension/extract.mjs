/** Normalize only the fields needed for a reviewed application draft. */
export function normalizeCapture({detail,items=[],url}) {
  const page=new URL(url);
  if(page.protocol!=='https:'||page.hostname!=='www.zhipin.com')throw new Error('请在 BOSS 直聘岗位页面使用');
  const info=detail?.jobInfo;
  if(!info||typeof info.postDescription!=='string'||info.postDescription.trim().length<30)throw new Error('未读取到完整 JD，请先打开岗位详情并等待加载');
  const direct=page.pathname.match(/^\/job_detail\/([a-zA-Z0-9_-]+)\.html$/)?.[1];
  const item=items.find(i=>detail.lid&&i.lid===detail.lid);
  if(!direct&&!item)throw new Error('详情与岗位列表无法关联，请重新打开目标岗位');
  const ident=info.encryptId||item?.encryptJobId||'';
  if(!/^[a-zA-Z0-9_-]+$/.test(ident)||(direct&&direct!==ident)||(item?.encryptJobId&&item.encryptJobId!==ident))throw new Error('岗位身份不一致，请等待详情完成加载后重试');
  const job={job_id:ident,recruiter_id:info.encryptUserId||item?.encryptBossId||'',title:info.jobName||item?.jobName||'',company:detail.brandComInfo?.brandName||detail.bossInfo?.brandName||item?.brandName||'',city:info.locationName||item?.cityName||'',salary:info.salaryDesc||item?.salaryDesc||'',recruiter:[detail.bossInfo?.name,detail.bossInfo?.title].filter(Boolean).join(' · '),description:info.postDescription.trim(),source_url:`https://www.zhipin.com/job_detail/${ident}.html`,source:'当前详情读取'};
  if(!job.title||!job.company)throw new Error('岗位名称或公司缺失，请手动导入完整 JD');
  return job;
}
