import test from 'node:test';
import assert from 'node:assert/strict';
import {readCurrentJob} from '../reader.mjs';
const description='负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。';
function fixture(shown){
  const root={isConnected:true,getClientRects:()=>[{}]};
  root.__vue__={$el:root,$data:{jobDetail:{lid:'a',securityId:'secret',jobInfo:{encryptId:'job',jobName:'产品经理',postDescription:description,securityId:'secret'},brandComInfo:{brandName:'测试公司'}},jobList:[{lid:'a',encryptJobId:'job',securityId:'secret'}]},$children:[]};
  globalThis.location={hostname:'www.zhipin.com',origin:'https://www.zhipin.com',pathname:'/web/geek/jobs'};
  globalThis.document={querySelectorAll:()=>[root],body:{innerText:shown?description:'岗位列表'}};
}
test('reader returns minimal current fields without tokens',()=>{fixture(true);const result=readCurrentJob();assert.equal(result.detail.jobInfo.postDescription,description);assert.ok(!JSON.stringify(result).includes('secret'));});
test('cached detail returns a serializable error across Chrome injection',()=>{fixture(false);assert.match(readCurrentJob().error,/可见|显示|详情/);});
test('standalone server-rendered detail can be read without Vue',()=>{
  const node=text=>({innerText:text,isConnected:true,getClientRects:()=>[{}]});
  const jd=node(description), title=node('产品经理（技术方向）'), salary=node('15-30K'), city=node('北京');
  const company={...node('测试公司'),getAttribute:()=>'/gongsi/company123.html'};
  const section={querySelectorAll:()=>[jd]};
  const heading={...node('职位描述'),parentElement:{querySelectorAll:()=>[]},closest:s=>s==='.job-detail-section'?section:null};
  globalThis.location={hostname:'www.zhipin.com',origin:'https://www.zhipin.com',pathname:'/job_detail/direct123.html'};
  const selectors={'h1':[title],'h3':[heading],'.job-banner .salary':[salary],'.job-banner a[href]':[city],'a[href*="/gongsi/"]':[company]};
  globalThis.document={querySelectorAll:s=>selectors[s]||[],body:{innerText:description}};
  const result=readCurrentJob();assert.ok(!result.error,result.error);assert.equal(result.detail.jobInfo.encryptId,'direct123');assert.equal(result.detail.jobInfo.postDescription,description);assert.equal(result.detail.brandComInfo.brandName,'测试公司');
});
test('Vue comment roots do not abort reading the visible detail',()=>{
  fixture(true);
  const root=document.querySelectorAll()[0];
  root.__vue__.$children.push({$el:{isConnected:true,nodeType:8},$data:{},$children:[]});
  const result=readCurrentJob();
  assert.ok(!result.error,result.error);
  assert.equal(result.detail.jobInfo.encryptId,'job');
});
