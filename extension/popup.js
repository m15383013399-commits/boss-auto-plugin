import {normalizeCapture} from './extract.mjs';
import {readCurrentJob} from './reader.mjs';
const $=id=>document.getElementById(id);let captured=null;
const status=text=>$('status').textContent=text;
chrome.storage.local.get('localKey').then(value=>$('key').value=value.localKey||'');
$('save').onclick=async()=>{await chrome.storage.local.set({localKey:$('key').value.trim()});status('本机连接密钥已保存。');};
$('read').onclick=async()=>{
  $('read').disabled=true;$('preview').hidden=true;captured=null;status('正在读取当前详情…');
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.url?.startsWith('https://www.zhipin.com/'))throw new Error('请切换到 BOSS 直聘岗位标签页再打开此扩展。');
    const results=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',func:readCurrentJob});
    if(results[0]?.error)throw new Error(results[0].error.message||'详情读取失败');
    const result=results[0]?.result;
    if(result?.error)throw new Error(result.error);
    if(!result?.url)throw new Error('浏览器未返回岗位数据，请关闭扩展弹窗后重新打开再读取。');
    captured=normalizeCapture(result);
    $('title').textContent=captured.title;$('meta').textContent=[captured.company,captured.city,captured.salary,captured.recruiter].filter(Boolean).join(' · ');$('jd').textContent=captured.description;
    $('preview').hidden=false;status('请核对岗位身份与完整 JD，再确认导入。');
  }catch(e){status(e.message||'读取失败，请先打开完整岗位详情。');}finally{$('read').disabled=false;}
};
$('import').onclick=async()=>{
  if(!captured)return;$('import').disabled=true;
  try{
    const key=$('key').value.trim();if(!key)throw new Error('请先从本机工作台复制连接密钥。');
    const response=await fetch('http://127.0.0.1:8765/api/import',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Key':key},body:JSON.stringify({jobs:[captured]}),signal:AbortSignal.timeout(10000)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'导入失败');
    status(result.count?'已导入。回到工作台查看批次，进行匹配分析与草稿审核。':'该岗位已在工作台中，已跳过。');
  }catch(e){status(e instanceof TypeError?'无法连接本机工作台，请先运行 python3 run.py。':e.message);}finally{$('import').disabled=false;}
};

$('batch').onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!tab?.url?.startsWith('https://www.zhipin.com/web/geek/jobs'))throw Error('请在 BOSS 职位搜索页筛选后使用批量导入');await chrome.tabs.create({url:chrome.runtime.getURL('batch.html')+'?tab='+tab.id});}catch(e){status(e.message);}};
