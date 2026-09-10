/** Runs once in MAIN world. Does not call page methods or write page state. */
export function readCurrentJob() {
  try {
    if(location.hostname!=='www.zhipin.com')throw new Error('请先打开 BOSS 直聘岗位页面');
    const seen=new Set(), queue=[], details=[], items=[];
    const pick=(o,keys)=>Object.fromEntries(keys.map(k=>[k,typeof o?.[k]==='string'?o[k]:'']));
    // Vue can mount a component on a comment node while its children are visible.
    const visible=el=>el&&el.isConnected&&typeof el.getClientRects==='function'&&el.getClientRects().length>0;
    for(const el of Array.from(document.querySelectorAll('#wrap, #wrap *')).slice(0,8000)) {
      if(el.__vue__&&visible(el))queue.push(el.__vue__);
    }
    for(let n=0;queue.length&&n<1500;n++) {
      const vm=queue.shift();if(!vm||seen.has(vm))continue;seen.add(vm);
      if(visible(vm.$el)) {
        const data=vm.$data||{};
        const detail=data.jobDetail||vm.jobDetail;
        if(detail?.jobInfo?.postDescription)details.push({lid:detail.lid||'',jobInfo:pick(detail.jobInfo,['encryptId','encryptUserId','jobName','locationName','salaryDesc','postDescription']),brandComInfo:pick(detail.brandComInfo,['brandName']),bossInfo:pick(detail.bossInfo,['name','title','brandName'])});
        const list=data.jobList||vm.jobList;
        if(Array.isArray(list))for(const item of list.slice(0,100))items.push(pick(item,['lid','encryptJobId','encryptBossId','jobName','brandName','cityName','salaryDesc']));
      }
      if(Array.isArray(vm.$children))queue.push(...vm.$children);
    }
    const unique=Array.from(new Map(details.map(d=>[d.jobInfo.encryptId+'|'+d.lid,d])).values());
    const directId=location.pathname.match(/^\/job_detail\/([a-zA-Z0-9_-]+)\.html$/)?.[1];
    if(!unique.length&&directId) {
      // Standalone job pages are server-rendered and need not expose a Vue jobDetail.
      const all=selector=>Array.from(document.querySelectorAll(selector)).filter(visible);
      const text=el=>(el?.innerText||'').trim();
      const heading=all('h3').find(el=>text(el).replace(/\s/g,'')==='职位描述');
      const section=heading?.closest?.('.job-detail-section')||heading?.parentElement;
      const descriptions=Array.from(section?.querySelectorAll('.job-sec-text')||[]).filter(visible);
      const titles=all('h1');
      const companies=all('a[href*="/gongsi/"]').filter(el=>/\/gongsi\/[a-zA-Z0-9_~-]+\.html(?:[?#]|$)/.test(el.getAttribute('href')||'')&&text(el)&&!text(el).startsWith('查看'));
      if(descriptions.length!==1||titles.length!==1||!companies.length)throw new Error('无法可靠定位岗位标题、公司或完整 JD，请展开详情后重试，或使用手动导入。');
      const bossName=text(all('.job-boss-info h2')[0]).replace(/(刚刚活跃|今日活跃|昨日活跃|本周活跃|本月活跃|\d+.*前活跃).*$/,'').trim();
      const company=text(companies[0]);
      const bossRole=text(all('.job-boss-info .boss-info-attr')[0]).replace(company,'').replace(/^[\s·]+/,'');
      unique.push({lid:'',jobInfo:{encryptId:directId,jobName:text(titles[0]),postDescription:text(descriptions[0]),salaryDesc:text(all('.job-banner .salary')[0]),locationName:text(all('.job-banner a[href]')[0])},brandComInfo:{brandName:company},bossInfo:{name:bossName,title:bossRole}});
    }
    if(unique.length!==1)throw new Error(unique.length?'存在多个岗位详情，无法可靠判断当前岗位，请关闭其他详情后重试':'未找到当前已加载的完整详情。请先点击岗位卡片；若页面结构变化，请使用手动导入。');
    // Vue may retain the last detail after its panel closes. Require rendered JD evidence.
    const rendered=(document.body?.innerText||'').replace(/\s+/g,'');
    const description=unique[0].jobInfo.postDescription.replace(/\s+/g,'');
    if(!rendered.includes(description.slice(0,100))||!rendered.includes(description.slice(-80)))throw new Error('岗位详情未完整显示，请打开目标 JD 并展开全文后重试');
    return {detail:unique[0],items,url:location.origin+location.pathname};
  } catch (error) {
    return {error:error.message||'页面读取失败，请重新打开完整岗位详情'};
  }
}
