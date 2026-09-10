"""Evidence-backed matching and natural draft composition."""
from .model import request_json

DIMENSIONS={'responsibilities':('核心职责与项目',40),'skills':('必需技能与方法',25),'industry':('行业与项目规模',15),'qualifications':('年限与学历',15),'bonus':('加分项',5)}
STATUS={'matched':1,'partial':0.5,'unknown':0,'unmet':0}

def validate_evaluation(raw,job,profile):
    criteria=raw.get('criteria')
    if not isinstance(criteria,list) or not 5<=len(criteria)<=50:raise ValueError('模型匹配结果缺少完整要求清单')
    facts={f['id']:f for f in profile['facts']};groups={d:[] for d in DIMENSIONS};matches=[];gaps=[];clean=[]
    for row in criteria:
        if not isinstance(row,dict):raise ValueError('模型匹配条目格式错误')
        d,r,s=row.get('dimension'),row.get('requirement'),row.get('status')
        if d not in groups or s not in (*STATUS,'not_applicable') or not isinstance(r,str):raise ValueError('模型匹配维度或状态错误')
        ev=row.get('evidence',[])
        if not isinstance(ev,list) or len(ev)>5:raise ValueError('匹配证据格式错误')
        if s=='not_applicable':
            if r or ev:raise ValueError('无相关要求的维度不能附带要求或证据')
        elif not r.strip():raise ValueError('匹配要求不能为空')
        if s in ('matched','partial') and not ev:raise ValueError('符合的要求必须给出简历依据')
        evidence=[]
        for item in ev:
            fid,q=item.get('fact_id'),item.get('quote')
            if fid not in facts or not isinstance(q,str) or not 2<=len(q)<=1000 or q not in facts[fid]['text']:raise ValueError('匹配证据不在简历原文中')
            evidence.append({'fact_id':fid,'quote':q})
            if s in ('matched','partial'):matches.append({'requirement':r,'fact_id':fid,'quote':q})
        reason=row.get('reason','')
        if not isinstance(reason,str):raise ValueError('匹配说明格式错误')
        reason=reason[:500]
        cleaned={'dimension':d,'requirement':r,'status':s,'reason':reason,'evidence':evidence}
        clean.append(cleaned);groups[d].append(cleaned)
        if s in ('unknown','partial','unmet'):gaps.append(('明确不符：' if s=='unmet' else '待核实：' if s=='unknown' else '部分符合：')+r+'；'+reason)
    dims=[];total=weight=0
    for d,(name,w) in DIMENSIONS.items():
        rows=groups[d]
        if not rows:raise ValueError('模型未覆盖全部匹配维度')
        active=[x for x in rows if x['status']!='not_applicable']
        if active and len(active)!=len(rows):raise ValueError('同一维度不能同时标记无要求和存在要求')
        ratio=sum(STATUS[x['status']] for x in active)/len(active) if active else None
        dims.append({'id':d,'name':name,'weight':w,'score':int(ratio*100+0.5) if ratio is not None else None})
        if ratio is not None:total+=ratio*w;weight+=w
    if not weight:raise ValueError('未识别到可评分的岗位要求')
    return {'score':int(total/weight*100+0.5),'dimensions':dims,'criteria':clean,'matches':matches,'gaps':gaps,'scoring_version':2,'engine':'model'}

def evaluate_job(config,job,profile):
    instruction=('逐项分析 JD 与简历的适配程度。覆盖岗位职责、每条必需条件、行业和规模、年限学历、加分项，避免只挑简历擅长的要求。'
        '按 dimensions 的五个维度归类，每个维度至少一条。必须拆开复合条件，例如学历与年限分别评估，每条只表达一个可判断的要求，要求描述不超过180字。不要把团队背景介绍或产品名称当作必须做过同一产品的要求；可迁移的相同职责经验可以支持匹配。'
        '招聘年限范围通常是岗位级别参考，候选人超过上限不构成明确不符，达到最低年限即可支持经验条件；只有 JD 明确写明不接受超出年限才可判不符。学历和经验必须分开，不可因为一项不符就把两项全判不符。'
        'status 只能是 matched（原文充分支持）、partial（部分支持）、unknown（没有依据）、unmet（有明确相反依据）。'
        'JD 完全没有该维度的要求时只返回一条 not_applicable，requirement 为空字符串、evidence 为空数组。'
        'requirement 可以忠实概括 JD 要求，不必逐字复述，不要新增 JD 没有的条件。evidence 的 quote 引用对应简历事实原文。不得推断未写出的年限或学历。'
        '每项 reason 用100字以内解释。返回 {"criteria":[{"dimension":"responsibilities","requirement":"岗位要求概括","status":"matched","reason":"具体依据或缺口","evidence":[{"fact_id":"真实编号","quote":"简历原文"}]}]}。')
    raw=request_json(config,instruction,{'job':{k:job.get(k,'') for k in ('title','company','description')},'resume_facts':profile['facts'],'dimensions':DIMENSIONS})
    return validate_evaluation(raw,job,profile)

def validate_draft(raw,profile,style):
    rows=raw.get('sentences');facts={f['id']:f for f in profile['facts']}
    if not isinstance(rows,list) or not 2<=len(rows)<=15:raise ValueError('招呼内容格式不完整')
    texts=[];citations=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError('招呼句子格式错误')
        text,ids=row.get('text'),row.get('fact_ids')
        if not isinstance(text,str) or not text.strip() or not isinstance(ids,list) or any(not isinstance(fid,str) or fid not in facts for fid in ids):raise ValueError('招呼引用了不存在的简历事实')
        texts.append(text.strip());citations.append({'text':text.strip(),'facts':[{'fact_id':fid,'quote':facts[fid]['text'],'section':facts[fid].get('section','简历')} for fid in dict.fromkeys(ids)]})
    text='\n'.join(texts)
    if not 40<=len(text)<=(360 if style=='brief' else 850):raise ValueError('招呼长度不合适，请重新生成')
    if not any(x['facts'] for x in citations):raise ValueError('招呼没有引用任何简历经历')
    return text,citations

def compose_greeting(config,job,profile,style):
    if style not in ('brief','detailed'):raise ValueError('请选择简洁或详细招呼')
    instruction=('为求职者写真实、自然的 BOSS 招呼。结构：岗位方向与经历关联、最相关项目与具体能力、简短沟通邀请。'
        '允许概括和改写，不要拼接简历原文、逐条复述 JD、写“我的相关经历：职责：”或空泛恭维。'
        '优先选具体项目与负责事项，省略无关技能。只有简历明确写出的年限、人数、成果、项目名才能使用，不推算不夸大。'
        '项目客户和任职单位必须区分。简历写面向某客户负责项目时，必须写为该客户的项目或面向该客户，不得改为在该客户单位负责工作。例如面向客户公司的项目，不等于在客户公司任职。'
        'JD 是雇主需求，不能转写成候选人的经历。参考语气：您好，我看到这个岗位主要做数据治理平台，和我过往的项目方向比较接近。'
        '按句或段输出，每句包含候选人事实时必须附带支持全部声明的 fact_ids；纯岗位描述和沟通邀请允许空数组。'
        '简洁版约150–250字；详细版约300–500字，避免重复。返回 {"sentences":[{"text":"自然句子","fact_ids":["事实编号"]}]}。')
    data={'style':style,'job':{k:job.get(k,'') for k in ('title','company','description')},'resume_facts':profile['facts']}
    audit_instruction=(
        '你是事实审校员，只核验可以客观查证的候选人经历是否有简历依据。输入包含完整简历事实（section 是经历/项目上下文）及逐句引用。'
        '允许忠实概括、同义改写、跨同一项目多条事实合并，不要求简历出现完全相同的句子或职位名称；做过AI产品项目足以支持AI应用产品方向经验。'
        '“希望沟通”“期待回复”等礼貌用语、对匹配方向的主观判断，不是需要简历证明的客观经历，不得因此拒绝。'
        '“整体AI产品设计”概括为该AI平台的“整体产品设计”允许；只写参与不能改写成独立负责。'
        '重点拒绝：无来源或错误的年限/人数/成果/项目名称，混淆雇主与客户，引用不属于该项目的指标，把JD要求冒充自己的经验，夸大职责或技能程度。'
        '必须先检查完整简历和section，再判断缺少依据。不要仅因措辞不同或存在细微差异而拒绝。'
        '返回 {"supported":true,"issues":[]}，有具体无依据声明时返回 {"supported":false,"issues":["准确指出哪句哪个事实有问题及简历实际依据"]}。')
    for attempt in range(2):
        raw=request_json(config,instruction,data);text,citations=validate_draft(raw,profile,style)
        audit=request_json(config,audit_instruction,{'job':data['job'],'resume_facts':profile['facts'],'sentences':citations})
        if audit.get('supported') is True and audit.get('issues')==[]:
            return {'text':text,'citations':citations,'style':style}
        issues=audit.get('issues',[])
        if not isinstance(issues,list) or not issues or any(not isinstance(x,str) for x in issues):raise ValueError('模型事实核验格式不完整，已保留原草稿')
        data={**data,'previous_draft':raw,'corrections_required':issues}
        instruction+='上一稿未通过事实核验。请逐项根据 corrections_required 删除无依据的事实或按简历修正，保持自然表达，不必保留原稿结构。'
    raise ValueError('招呼事实核验未通过，已保留原草稿：'+str(issues[0])[:180])
