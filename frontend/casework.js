/* Case cards consume structured artifacts; no amount or score is inferred from prose. */
function caseField(name, label, value, type = 'text') {
    return `<label class="case-field">${escapeHtml(label)}<input name="${name}" type="${type}" value="${escapeHtml(value ?? '')}" ${type === 'number' ? 'min="0" step="0.01"' : ''}></label>`;
}
function caseSelect(name, label, value, options) {
    return `<label class="case-field">${label}<select name="${name}">${options.map(([key, text]) => `<option value="${key}" ${String(value ?? '') === key ? 'selected' : ''}>${text}</option>`).join('')}</select></label>`;
}
function wageRow(w = {}) {
    return `<div class="case-wage-row">${caseField('wage_start','工资起日',w.start,'date')}${caseField('wage_end','工资止日',w.end,'date')}${caseField('wage_due','应付工资（元）',w.due,'number')}${caseField('wage_paid','实付工资（元）',w.paid,'number')}<button type="button" data-case-remove-wage>移除此期间</button></div>`;
}
function renderConditionChecklist(items) {
    if (!items?.length) return '';
    return `<ul>${items.map(item => `<li>${escapeHtml(item.label)}：${item.status === 'user_stated' ? '用户陈述，待举证' : '待澄清'}</li>`).join('')}</ul>`;
}
function renderCaseReviewIssue(issue, sources) {
    const severity=['critical','warning','info'].includes(issue.severity)?issue.severity:'info';
    const symbols={critical:'!',warning:'?',info:'i'};
    const laws = (issue.law_excerpts || []).map(excerpt => {
        const source = sources.find(s => s.id === excerpt.source_id);
        const title = source ? `${source.title}${source.article ? ` 第${source.article}条` : ''}` : '法条片段';
        const link = source && /^https?:\/\//.test(source.url || '') ? `<a target="_blank" rel="noopener noreferrer" href="${escapeHtml(source.url)}">查看官方原文</a>` : '';
        return `<p>${escapeHtml(title)} ${link}</p><blockquote>${escapeHtml(excerpt.quote)}</blockquote>`;
    }).join('');
    const facts = (issue.fact_excerpts || []).map(excerpt => `<p>${excerpt.field.startsWith('calculations.') ? '核算结果' : '输入原文'}：</p><blockquote>${escapeHtml(excerpt.quote)}</blockquote>`).join('');
    return `<div class="case-review-issue review-${severity}"><p class="review-label"><span class="review-symbol" aria-hidden="true">${symbols[severity]}</span><strong>${escapeHtml(caseStatusLabel(severity))}</strong></p><p>${escapeHtml(issue.message)}</p>${severity==='critical'?'<button type="button" class="text-button" data-edit-facts>核对并补充事实</button>':''}${laws || facts ? `<details><summary>查看此问题引用的事实与法条</summary>${facts}${laws}<p>片段匹配不代表法律适用已经核验，仍须结合具体案件复核。</p></details>` : ''}</div>`;
}
function sortedReviewIssues(issues=[]) {
    const rank={critical:0,warning:1,info:2};
    return [...(issues||[])].sort((a,b)=>(rank[a.severity]??2)-(rank[b.severity]??2));
}
function renderCaseClaim(c,r,data) {
    const amount=r?.status === 'not_applicable' ? '当前情形不适用' : (r?.amount == null ? '金额待核验' : `${r.amount} 元（${r.status === 'no_unpaid_balance' ? '所填期间无欠付余额' : '条件测算'}）`);
    return `<div class="case-claim">
      <label><input type="checkbox" name="selected_claim" value="${escapeHtml(c.id)}" ${c.status !== 'conditional' || r?.amount == null ? 'disabled' : ''} ${data.confirmation?.selected_claims?.includes(c.id) ? 'checked' : ''}> ${escapeHtml(c.title)}（${escapeHtml(caseStatusLabel(c.status))}）</label>
      <p>${escapeHtml(c.conditions)}</p>${c.status !== 'not_selected' ? renderConditionChecklist(c.condition_checklist) : ''}
      <strong>${escapeHtml(amount)}</strong><p class="calculation-label">按当前输入进行规则测算</p><p>计算前提：${escapeHtml(c.conditions || '仍须核对请求条件')}</p><p>${escapeHtml(r?.formula || '')}</p><p>${escapeHtml((r?.missing_parameters || []).join('；'))}</p>
      ${(data.analysis?.arguments || []).filter(a => a.claim_id === c.id).map(a => `<p>支持材料：${escapeHtml(a.supporting_evidence.join('；'))}<br>不利因素：${escapeHtml(a.adverse_factors.join('；'))}<br>追问：${escapeHtml(a.questions.join('；'))}</p>`).join('')}
    </div>`;
}
function renderAnalysisReviewHistory(data) {
    const history=data.analysis_review_history || [];
    if (!history.length) return '';
    const repair=data.analysis_repair || {};
    const note=repair.attempts ? `<p>${repair.status === 'review_passed' ? '引用分析已修订并完成复审；请继续核对事实、请求和金额。' : '引用修订仍需核查，当前结果以本页确认状态为准。'}</p>` : '';
    return `<details><summary>查看分析修订与审查记录</summary>${note}${history.map(entry => `<section><h4>v${entry.case_version} · ${entry.phase === 'after_revision' ? '修订后复审' : '首次审查'}</h4>${sortedReviewIssues(entry.issues).map(issue => renderCaseReviewIssue(issue,entry.source_refs || [])).join('') || '<p>本轮未提出新增问题，不表示证据真实性或法律结论已确认。</p>'}</section>`).join('')}</details>`;
}
const CASE_CONDITION_SCOPES = {
    agreement_reached:['employer_agreement'],
    worker38_ground:['worker_38'],worker38_conditions:['worker_38'],worker38_notice_delivered:['worker_38'],
    article40_category:['article_40'],article40_conditions:['article_40'],written_notice_30:['article_40'],
    protected_status:['article_40','article_41'],layoff_conditions:['article_41'],layoff_procedure:['article_41'],
    continued_performance:['illegal_claim']
};
function renderCaseFields(fields,basis) {
    return fields.map(html => {
        const name=html.match(/name="([^"]+)"/)?.[1], scope=CASE_CONDITION_SCOPES[name];
        return scope ? html.replace('class="case-field"',`class="case-field" data-case-condition="${scope.join(' ')}" style="display:${scope.includes(basis) ? '' : 'none'}"`) : html;
    }).join('');
}
document.addEventListener('change',event => {
    if (event.target.name !== 'termination_basis') return;
    event.target.closest('.case-fact-form')?.querySelectorAll('[data-case-condition]').forEach(field => {
        field.style.display=field.dataset.caseCondition.split(' ').includes(event.target.value) ? '' : 'none';
    });
});
function buildCaseReport(data, content, runtimeStatus) {
    const f = data.facts || {}, id = `case-${data.case_version}-${Math.random().toString(36).slice(2,8)}`;
    const calculations = new Map((data.calculations || []).map(r => [r.claim_id,r]));
    const cityOptions = [['','待补充'],...['广州','深圳','珠海','佛山','惠州','东莞','中山','江门','肇庆','香港','澳门'].map(c => [c,c])];
    const boolOptions = [['','未知'],['true','是'],['false','否']];
    const fields = [caseSelect('workplace','你主要在哪个城市工作？',f.workplace,cityOptions),caseSelect('employer_city','单位在哪个城市？',f.employer_city,cityOptions),
        caseField('dispute_date','争议发生日期',f.dispute_date,'date'),caseField('start_date','入职日期',f.start_date,'date'),caseField('end_date','解除／离职日期',f.end_date,'date'),
        caseField('wage_statement','工资约定、当期工作及在职情况陈述（待举证）',f.wage_statement),
        caseSelect('employment_status','当前在职状态（用户陈述）',f.employment_status || 'unknown',[['unknown','尚不明确'],['active','仍在职'],['terminated','已离职']]),
        caseSelect('initiator','是谁提出结束劳动关系？',f.initiator,[['unknown','未知'],['employer','单位'],['worker','劳动者'],['mutual','双方协商']]),
        caseSelect('termination_basis','你了解的离职情况是什么？不确定可保留未知',f.termination_basis,[['unknown','尚不清楚／目前不涉及解除'],['employer_agreement','单位提出，双方协商结束'],['worker_38','因单位欠薪等原因提出解除'],['article_40','单位称因身体、工作能力或客观变化解除'],['article_41','单位称进行经济性裁员'],['article_39','单位称因违纪等过失解除'],['voluntary','个人主动辞职'],['illegal_claim','认为单位解除违法（尚未认定）']]),
        caseField('termination_reason','具体解除理由',f.termination_reason),caseField('monthly_average','解除前12个月应得月平均工资（元）',f.monthly_average,'number'),caseField('previous_month_wage','解除前一个月工资（元）',f.previous_month_wage,'number'),
        caseSelect('agreement_reached','单位提出协商解除：双方已达成一致',f.agreement_reached,boolOptions),
        caseSelect('worker38_ground','第38条：具体解除事由',f.worker38_ground,[['unknown','待澄清'],['unpaid_wages','未及时足额支付工资'],['labor_conditions','未提供约定劳动保护或劳动条件'],['unpaid_social_insurance','未依法缴纳社会保险'],['unlawful_rules','违法规章损害劳动者权益'],['invalid_contract','因第26条第一款导致合同无效'],['other','其他事由（需专业复核）']]),
        caseSelect('worker38_conditions','第38条：具体事由事实条件已具备（用户陈述）',f.worker38_conditions,boolOptions),caseSelect('worker38_notice_delivered','第38条：具体解除理由已送达单位',f.worker38_notice_delivered,boolOptions),
        caseSelect('article40_category','第40条：具体类别',f.article40_category,[['unknown','待澄清'],['medical','医疗期满不能从事原工作及另行安排工作'],['incompetence','经培训或调岗后仍不能胜任'],['objective_change','客观情况重大变化且未协商达成变更']]),
        caseSelect('written_notice_30','提前30日书面通知',f.written_notice_30,boolOptions),caseSelect('article40_conditions','第40条：所选类别全部事实条件已具备',f.article40_conditions,boolOptions),caseSelect('protected_status','第42条保护情形（如孕期、医疗期）',f.protected_status,boolOptions),
        caseSelect('layoff_conditions','第41条：法定裁员事由与人数比例已核对',f.layoff_conditions,boolOptions),caseSelect('layoff_procedure','第41条：说明、听取意见及报告等程序已履行',f.layoff_procedure,boolOptions),
        caseSelect('continued_performance','主张违法解除：继续履行请求',f.continued_performance,[['unknown','待澄清'],['not_requested','不请求继续履行'],['requested','请求继续履行（应核对救济路径）'],['impossible','继续履行确已不能（待举证）']]),
        caseSelect('actual_cross_border_work','实际跨境履行（身份或股东标签不算）',f.actual_cross_border_work,boolOptions),caseSelect('cross_city_resolved','跨市事实已经澄清（补偿参数仍需核验）',f.cross_city_resolved,[['false','尚未／不涉及'],['true','已经澄清事实']]),
        caseSelect('employment_type','用工类型',f.employment_type,[['ordinary','普通劳动关系'],['dispatch','劳务派遣'],['part_time','非全日制'],['retired','退休用工'],['other','其他']]),
        caseField('applicant','申请人姓名',f.applicant),caseField('employer_name','单位名称',f.employer_name),caseField('applicant_address','申请人地址',f.applicant_address),caseField('applicant_phone','申请人电话',f.applicant_phone),caseField('applicant_id','申请人身份证号',f.applicant_id),caseField('employer_address','单位地址',f.employer_address),caseField('employer_representative','法定代表人／负责人',f.employer_representative),caseField('employer_phone','单位电话',f.employer_phone)];
    const basic=new Set(['workplace','employer_city','dispute_date','start_date','end_date','employment_status','employment_type','actual_cross_border_work','cross_city_resolved']);
    const subject=new Set(['applicant','employer_name','applicant_address','applicant_phone','applicant_id','employer_address','employer_representative','employer_phone']);
    const nameOf=html=>html.match(/name="([^"]+)"/)?.[1];
    const group=(names,invert=false)=>renderCaseFields(fields.filter(html=>invert ? !basic.has(nameOf(html))&&!subject.has(nameOf(html)):names.has(nameOf(html))),f.termination_basis);
    const stage=data.status==='draft_ready'?3:data.status==='awaiting_confirmation'?2:data.status==='needs_information'?0:1;
    const issues=sortedReviewIssues(data.review_issues),blocking=issues.some(i=>i.severity==='critical');
    return `<article class="case-report" data-case-version="${data.case_version}">
      <div class="case-heading"><h3>案件事实与请求</h3><span class="status-label ${['review_blocked','document_blocked','failed'].includes(data.status)?'danger':data.status==='needs_information'?'warning':''}">${escapeHtml(caseStatusLabel(data.status))}</span></div>
      <div class="case-coverage"><strong>资料覆盖范围</strong><p>${escapeHtml(data.coverage?.message || '地区尚待明确，暂不确定城市专项适用。')}</p><p>本次实际检索来源见“法律依据”；覆盖资料不表示全部适用于本案。</p></div>
      <ol class="case-steps">${['补充事实','核对请求','确认金额','形成草稿'].map((label,i)=>`<li class="${i===stage?'current':i<stage?'past':''}" ${i===stage?'aria-current="step"':''}>${label}</li>`).join('')}</ol>
      <div class="case-focus"><strong>${data.status==='needs_information'?'先补充关键情况':escapeHtml(caseStatusLabel(data.status))}</strong><p>${escapeHtml((data.missing_labels || []).slice(0,2).join('；') || '核对事实、请求及其前提，再确认本次金额。')}</p></div>
      <details class="case-section review-section" data-section="issues" ${blocking?'open':''}><summary>待补信息与审查<span class="section-caption">${blocking?'有阻止确认的问题':issues.length+' 项提示'}</span></summary><div class="section-body"><p>${escapeHtml((data.missing_labels || []).join('；') || '暂无已知关键缺失')}</p><p class="field-legend">颜色表示处理优先级，不表示败诉风险。</p>${issues.map(i=>renderCaseReviewIssue(i,data.sources || [])).join('')}${renderAnalysisReviewHistory(data)}${(data.failures || []).map(x=>`<p class="failure-notice">${escapeHtml(caseTaskLabel(x.stage))}：${escapeHtml(x.reason)}</p>`).join('')}</div></details>
      <form class="case-fact-form">
        <div class="fact-editor-heading"><h4 tabindex="-1" data-fact-heading>补充和修改事实</h4><button class="text-button" type="button" data-guide-mode></button></div>
        <div class="fact-guide" data-guide-nav aria-label="事实填写步骤">${['基本情况','争议与工资','材料持有'].map((label,i)=>`<button type="button" data-guide-step="${i}">${i+1}. ${label}</button>`).join('')}</div>
        <p class="field-legend" data-guide-note>切换步骤只保留本机编辑；保存后才重新分析，不确定的项目可保留未知。</p>
        <details class="case-section" data-section="basic" data-guide-group="0" ${data.status==='needs_information'?'open':''}><summary>基本情况<span class="section-caption">地域与劳动关系</span></summary><div class="section-body"><p class="field-legend">填写内容为用户陈述，仍需材料支持。</p><div class="case-field-grid">${group(basic)}</div><details><summary>文书主体信息（可稍后补充）</summary><div class="case-field-grid">${group(subject)}</div></details></div></details>
        <details class="case-section" data-section="dispute" data-guide-group="1"><summary>争议与工资<span class="section-caption">逐期核对</span></summary><div class="section-body"><details class="field-help"><summary>不清楚法律条款时怎么填？</summary><p>按实际经历选择，无法判断可保留未知。单位欠薪等事由、非过失解除、经济性裁员和过失解除分别涉及《劳动合同法》第38、40、41、39条；选项不表示已满足法律条件，仍需核对下方事实与材料。</p></details><div class="case-field-grid">${group(null,true)}</div><h4>欠薪期间</h4><p class="field-legend">应付工资与实付工资分别填写，不从流水推定应付标准。</p><div class="case-wages">${(f.wages || []).map(wageRow).join('')}</div><button type="button" data-case-add-wage>＋ 增加工资期间</button></div></details>
        <details class="case-section" data-section="evidence" data-guide-group="2"><summary>材料持有<span class="section-caption">持有不等于验真</span></summary><div class="section-body"><div class="case-field-grid">${['劳动合同','工资流水','解除通知','考勤','聊天记录','规章制度'].map(name=>caseSelect(`evidence_${name}`,name,f.evidence?.[name] || 'unknown',[['unknown','未知'],['claimed_present','称持有（未核验）'],['missing','缺失']])).join('')}</div></div></details>
        <div class="guide-actions" data-guide-actions><button type="button" class="quiet-button" data-guide-back>上一步</button><button type="button" class="quiet-button" data-guide-next>下一步（仅保留编辑）</button></div>
        <div class="fact-save-bar"><span class="dirty-label" data-dirty-label hidden>尚未应用 · 保存后将重新分析</span><button class="case-action" type="button" data-case-save>保存事实并重新分析</button></div>
      </form>
      <details class="case-section" data-section="claims" open><summary>请求与金额<span class="section-caption">条件测算</span></summary><div class="section-body"><p class="document-invalid" data-amount-pending hidden></p>${(data.claims || []).map(c=>renderCaseClaim(c,calculations.get(c.id),data)).join('') || '<p class="panel-intro">补充事实后再分析可考虑的请求。</p>'}${(data.claims || []).some(c=>['N','2N','notice'].includes(c.id))?'<p class="legal-note">N与2N为备选；2N与代通知金不累计。</p>':''}${data.confirmation_required?'<button class="case-action" type="button" data-case-confirm>核对事实、请求和金额，生成草稿</button>':''}<p class="legal-note">确认只代表认可输入内容，不表示事实或证据真实性已核验。</p></div></details>
      <details class="case-section" data-section="process"><summary>协同处理记录<span class="section-caption">实际执行</span></summary><div class="section-body">${renderProcess(data.stages || [])}<p class="legal-note">${data.analysis?.status==='rules_only'?'本轮为规则与工具核查，未启用模型增强。':'显示已返回的节点记录与阶段产物，不表示完成专业法律复核。'}</p></div></details>
      <details class="case-section" data-section="provenance"><summary>事实来源与修订</summary><div class="section-body fact-provenance"><dl>${Object.entries(data.fact_sources || {}).map(([key,source])=>`<dt>${escapeHtml(fieldLabel(key))} · ${source.confirmed?'已确认输入':'用户陈述'}</dt><dd>${escapeHtml(source.statement || '来自用户填写')}（未验真）</dd>`).join('')}</dl>${(data.revisions || []).map(r=>`<p class="legal-note">v${r.case_version}：${escapeHtml(Object.keys(r.changes || {}).map(fieldLabel).join('、') || '创建案件')}；下游旧结果已撤销。</p>`).join('')}</div></details>
      <div class="answer-tools"><button class="text-button sources-button" type="button" data-current-sources>查看本轮检索依据</button>${data.document_status==='reviewed_draft'?'<button class="text-button sources-button" type="button" data-open-document>阅读文书草稿</button>':''}</div>
      <p class="legal-note">系统核查不能代替证据核验与专业法律复核；当前未解决的问题以上方提示为准。</p>
    </article>`;
}

function caseTaskLabel(task) {
    return ({intake:'接待与事实澄清',retrieval:'地域及法源检索',analysis:'证据与分请求分析',calculation:'确定性计算',analysis_review:'分析审查',analysis_revision:'根据审查修订引用分析',analysis_recheck:'修订后复审',confirmation:'用户确认',document:'仲裁申请书草稿',document_review:'文书一致性审查'})[task] || task;
}
function caseStatusLabel(status) {
    return ({needs_information:'需补充信息',review_blocked:'待专业复核',no_supported_claim:'当前事实无可确认请求',awaiting_confirmation:'等待用户确认',draft_ready:'草稿已通过内部一致性检查',document_blocked:'文书审查未通过',conditional:'条件成立时可考虑',not_selected:'当前情形不适用',needs_clarification:'需澄清条件',completed:'已完成',failed:'执行失败',critical:'阻止确认',warning:'待核实',info:'补充说明'})[status] || status;
}

function fieldLabel(key) {
    return ({workplace:'履行地',employer_city:'单位所在地',dispute_date:'争议日期',start_date:'入职日期',end_date:'离职日期',employment_status:'在职状态',wages:'工资期间',wage_statement:'工资及劳动履行陈述',monthly_average:'补偿工资基数',previous_month_wage:'上月工资',termination_basis:'解除情形',termination_reason:'解除理由',initiator:'解除提出方',evidence:'材料持有情况'})[key] || (key.startsWith('evidence.')?key.slice(9):'案件补充信息');
}
function renderProcess(stages) {
    if (!stages.length) return '<p class="panel-intro">尚无执行记录。</p>';
    const products={intake:'整理输入、缺失与冲突',retrieval:'按地域及时间检索来源',analysis:'逐请求分析成立条件',calculation:'条件金额、公式与缺失参数',analysis_review:'核对引用、条件及请求',confirmation:'核对当前版本确认状态',document:'依据确认对象形成草稿',document_review:'核对金额、事实与文书一致性'};
    return `<ol class="process-list">${stages.map(s=>`<li class="${escapeHtml(s.status)}"><span class="node-indicator"></span><div><strong>${escapeHtml(caseTaskLabel(s.task))} · ${s.status==='running'?'正在执行':escapeHtml(caseStatusLabel(s.status))}</strong><p>${escapeHtml(products[s.task] || '按当前案件继续核对')}</p></div><span class="process-duration">${s.seconds==null?'':escapeHtml(s.seconds)+'s'}</span></li>`).join('')}</ol>`;
}
function collectCaseFacts(form) {
    const facts={},numeric=new Set(['monthly_average','previous_month_wage']);
    const boolean=new Set(['written_notice_30','article40_conditions','agreement_reached','worker38_conditions','worker38_notice_delivered','layoff_conditions','layoff_procedure','protected_status','actual_cross_border_work','cross_city_resolved']);
    for (const el of form.querySelectorAll('.case-field-grid input,.case-field-grid select')) {
        if (el.name.startsWith('evidence_')) { (facts.evidence ||= {})[el.name.slice(9)]=el.value;continue; }
        facts[el.name]=boolean.has(el.name)?(el.value===''?null:el.value==='true'):(el.value===''?null:el.value);
        if (numeric.has(el.name) && el.value && Number(el.value)<=0) throw new Error('工资须大于零。');
    }
    facts.wages=[...form.querySelectorAll('.case-wage-row')].map(row=>Object.fromEntries(['start','end','due','paid'].map(key=>[key,row.querySelector(`[name="wage_${key}"]`).value])));
    return facts;
}
