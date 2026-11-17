/* v18: UI projections never change case facts or tool-owned amounts. */
'use strict';
const STORAGE_KEY='laborhub_sessions_v2', LEGACY_STORAGE_KEY='laborhub_sessions';
const ACTIVE_KEY='laborhub_active_session_v17';
let sessions=[], currentSessionId=null, returnFocus=null, sidebarFocus=null, toastTimer;
const pending=new Map();
const $=id=>document.getElementById(id);
const currentSession=()=>sessions.find(s=>s.id===currentSessionId);
const generateId=()=>Date.now()+'-'+Math.random().toString(36).slice(2,9);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
function icon(name) {
    const paths={chat:'<path d="M21 11a8 8 0 0 1-8 8H6l-4 3V11a9 9 0 0 1 18-3"/><path d="M7 10h9M7 14h6"/>',folder:'<path d="M3 7V5h6l2 2h10v13H3z"/><path d="M3 11h18"/>',panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',arrow:'<path d="m5 12 7-7 7 7M12 5v15"/>',book:'<path d="M12 5v15M12 5C9 3 5 3 2 5v14c4-2 7-2 10 1 3-3 7-3 10-1V5c-3-2-7-2-10 0z"/>',money:'<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M5 8h1M18 16h1"/>',document:'<path d="M14 2H5v20h14V7zM14 2v6h5M8 12h8M8 16h6"/>',copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',external:'<path d="M13 3h8v8M21 3l-11 11M10 3H3v18h18v-7"/>'};
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.chat}</svg>`;
}
function renderMarkdownSafe(text) {
    if (!text) return '';
    // If a local renderer is unavailable, use escaped text, never partially sanitized HTML.
    if (!window.marked || !window.DOMPurify) return `<p style="white-space:pre-wrap">${escapeHtml(text)}</p>`;
    const html=DOMPurify.sanitize(marked.parse(String(text)),{USE_PROFILES:{html:true},FORBID_TAGS:['form','input','button','textarea','select','style']});
    const template=document.createElement('template');template.innerHTML=html;
    template.content.querySelectorAll('a').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer';});
    return template.innerHTML;
}
function persistSessions() {
    try { localStorage.setItem(STORAGE_KEY,JSON.stringify(sessions));localStorage.setItem(ACTIVE_KEY,currentSessionId); }
    catch { toast('浏览器存储空间不足，本轮内容暂保留在页面中，请及时复制。'); }
}
function latestCaseMessage(session=currentSession()) { return [...(session?.messages||[])].reverse().find(m=>m.structured?.workflow==='case'); }
function ui(session=currentSession()) { return session.ui ||= {}; }
function loadSessions() {
    try {
        const raw=JSON.parse(localStorage.getItem(STORAGE_KEY)||localStorage.getItem(LEGACY_STORAGE_KEY)||'[]');
        sessions=(Array.isArray(raw)?raw:[]).filter(s=>s&&typeof s==='object').map(s=>({...s,id:String(s.id||generateId()),title:String(s.title||'新会话'),workspace:s.workspace==='case'?'case':'auto',ui:s.ui&&typeof s.ui==='object'?s.ui:{},messages:(Array.isArray(s.messages)?s.messages:[]).filter(m=>m&&typeof m==='object').map(m=>({...m,id:m.id||generateId(),role:m.role==='user'?'user':'ai',content:String(m.content||''),runtimeStatus:['thinking','streaming'].includes(m.runtimeStatus)?'interrupted':m.runtimeStatus||'complete'}))}));
    } catch { sessions=[];toast('历史记录无法读取，已创建空白对话；原存储未主动清除。'); }
    if (!sessions.length) sessions=[makeSession()];
    // A refresh can leave the server executing after the browser lost its stream.
    // Keep all artifacts, but require an explicit sync before further case actions.
    for(const s of sessions)if(s.messages.at(-1)?.runtimeStatus==='interrupted'&&latestCaseMessage(s))ui(s).uncertain=true;
    currentSessionId=sessions.find(s=>s.id===localStorage.getItem(ACTIVE_KEY))?.id||sessions[0].id;
    persistSessions();
}
function makeSession(){return {id:generateId(),title:'新会话',workspace:'auto',messages:[],ui:{},createdAt:Date.now()};}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4000);}
function announce(text){$('announcement').textContent=text;}
function inferTitle(text){return text.replace(/\s+/g,' ').slice(0,22)||'新会话';}
function renderHistoryList(){
    $('historyCount').textContent=sessions.length;
    $('historyList').innerHTML=sessions.map(s=>`<div class="history-item ${s.id===currentSessionId?'active':''}"><button class="history-open" type="button" data-session="${escapeHtml(s.id)}" ${s.id===currentSessionId?'aria-current="page"':''}>${icon('chat')}<span class="history-title">${escapeHtml(s.title)}</span>${pending.has(s.id)?'<span class="history-meta">处理中</span>':''}</button><button type="button" class="delete-session" data-delete-session="${escapeHtml(s.id)}" aria-label="删除${escapeHtml(s.title)}">×</button></div>`).join('');
}
const EXAMPLES=[['money','欠薪怎么办','理清工资期间与支付情况','公司拖欠工资，我应该先准备什么？'],['folder','解除与补偿','了解条件，再核对请求','N、2N和N+1有什么区别？'],['book','读懂法条','原文、版本与通俗解释','劳动合同法第47条是什么'],['document','准备仲裁材料','先核对事实与金额','请帮我准备欠薪仲裁材料。']];
function welcome(){return `<div class="welcome"><p class="welcome-label"><span></span>广州、深圳重点适配 · 劳动争议辅助</p><h2>把劳动问题说清楚，<br>把下一步准备好。</h2><p class="welcome-description">不必先懂法律术语。说说你的情况，我们一起梳理事实、查找依据；需要核算或准备材料时，再逐项核对。</p><p class="welcome-promise">重要法律判断提供可查依据；金额展示计算前提；生成草稿前由你核对。</p><div class="journey-line"><b>一个问题</b><i></i><span>理清事实</span><i></i><span>核对依据</span><i></i><span>准备材料</span></div><div class="task-list">${EXAMPLES.map(([name,title,description,prompt],i)=>`<button class="task-example" type="button" data-example="${i}"><span class="task-icon">${icon(name)}</span><span><strong>${title}</strong><small>${description}</small></span><span class="task-chevron">›</span></button>`).join('')}</div><p class="welcome-note">全国与广东规则为基础，广州、深圳提供城市专项资料；其余大湾区内地七市的城市专项资料待完善。港澳不纳入首期内地自动测算。</p></div>`;}
function answerHeader(){return '<div class="answer-heading"><span class="answer-mark" aria-hidden="true">法</span><span>劳法智枢</span></div>';}
function draftUsable(data,session=currentSession()) {
    return !!data&&latestCaseMessage(session)?.structured===data&&data.document_status==='reviewed_draft'
        &&data.status==='draft_ready'&&data.confirmation?.case_version===data.case_version
        &&data.document?.case_version===data.case_version&&!!data.document.markdown
        &&!(data.review_issues||[]).some(i=>i.severity==='critical')&&!(data.failures||[]).length
        &&!session.ui?.uncertain&&!session.ui?.factDraft&&!pending.get(session.id)?.caseOperation;
}
function preparationSummary(data,session) {
    if(!draftUsable(data,session))return '';
    const selected=new Set(data.confirmation.selected_claims),rows=(data.calculations||[]).filter(r=>selected.has(r.claim_id));
    const subjects={applicant:'申请人姓名',applicant_id:'申请人身份证号',applicant_address:'申请人地址',applicant_phone:'申请人电话',employer_name:'单位名称',employer_address:'单位地址',employer_representative:'法定代表人／负责人'};
    return `<section class="preparation-summary" aria-label="材料准备摘要"><h3>本次材料准备结果</h3><p>案件 v${escapeHtml(data.case_version)} · 内部一致性检查通过</p>${rows.map(r=>`<p class="summary-amount">${escapeHtml(data.claims?.find(c=>c.id===r.claim_id)?.title||r.claim_id)} ${escapeHtml(r.amount)} 元</p><p class="summary-formula">${escapeHtml(r.formula||'')} · 按当前输入进行规则测算</p>`).join('')}<dl><dt>待补材料</dt><dd>${escapeHtml((data.materials_needed||[]).join('、')||'暂无已知缺项，仍需核验材料')}</dd><dt>主体信息占位</dt><dd>${escapeHtml((data.subject_fields_needed||[]).map(k=>subjects[k]||k).join('、')||'已填写，仍需核对')}</dd></dl><p>下一步：补齐信息与材料，核对草稿，并请法律援助人员或律师专业复核；草稿尚未提交仲裁。</p><p class="legal-note">一致性检查不代表法律结论或证据真实性已获确认。</p><div class="answer-tools"><button type="button" class="text-button" data-open-document>阅读草稿</button><button type="button" class="text-button" data-case-copy>复制 Markdown</button></div></section>`;
}
function caseProgressHtml(message) {
    const stages=message.caseProgress||[];if(!stages.length)return '';
    const interrupted=['error','interrupted'].includes(message.runtimeStatus),running=stages.find(s=>s.status==='running');
    const completed=stages.filter(s=>s.status==='completed'),failed=stages.find(s=>s.status==='failed');
    const title=interrupted?'本轮处理已中断，已有阶段结果已保留':failed?'有阶段未完成，请查看问题并重试':message.awaitingCaseConfirmation?'等待你核对事实、请求和金额':running?'正在'+caseTaskLabel(running.task):'已收到阶段结果，等待后续返回';
    return `<section class="live-case-progress" aria-label="本轮案件真实进度"><strong>${escapeHtml(title)}</strong><p>${completed.length?'已完成：'+escapeHtml(completed.map(s=>caseTaskLabel(s.task)).join('、')):'服务端已开始处理本轮案件。'}</p>${failed?`<p class="failure-notice">未完成：${escapeHtml(caseTaskLabel(failed.task))}</p>`:''}${(message.reviewEvents||[]).length?`<p>已返回 ${message.reviewEvents.length} 项审查提示，完成后请先处理阻断项。</p>`:''}<small>仅显示已收到的实际执行事件，不预估完成比例。</small></section>`;
}
function renderMessage(m,index,session){
    if(m.role==='user') return `<article class="message message-user" data-message-id="${escapeHtml(m.id)}"><div class="user-bubble">${escapeHtml(m.content)}</div></article>`;
    const d=m.structured,isCase=d?.workflow==='case',busy=['thinking','streaming'].includes(m.runtimeStatus),failed=m.runtimeStatus==='error'||m.runtimeStatus==='interrupted'||['model_failed','retrieval_failed','invalid_output'].includes(d?.status);
    let content;
    if(isCase){
        const latest=latestCaseMessage(session)===m,amounts=(d.calculations||[]).filter(c=>c.amount!=null);
        const usable=draftUsable(d,session),draftLabel=d.document_status==='reviewed_draft'?(latest?(usable?'草稿可供核对':'草稿暂不可使用，请保存修改或同步案件'):'历史草稿记录（只读）'):caseStatusLabel(d.status);
        content=`<div class="case-summary"><div class="summary-heading"><strong>${escapeHtml(draftLabel)}</strong><span class="version-label">v${d.case_version}${latest?' · 当前':' · 历史'}</span></div><p>${escapeHtml((d.missing_labels||[]).slice(0,2).join('；')||'事实、请求与金额已整理，可打开详情核对。')}</p>${!usable?amounts.map(c=>`<p class="summary-amount">${escapeHtml(d.claims?.find(x=>x.id===c.claim_id)?.title||'条件测算')} ${escapeHtml(c.amount)} 元</p>`).join(''):''}<div class="answer-tools"><button type="button" class="text-button sources-button" data-case-message="${escapeHtml(m.id)}">${latest?'查看当前案件':'查看历史结果（只读）'}</button></div>${latest?preparationSummary(d,session):''}</div>`;
    } else {
        const waiting=busy&&!m.content;
        const progress=caseProgressHtml(m);
        content=`<div class="conversation-answer">${progress}${waiting?(progress?'':`<p class="conversation-wait"><span class="wait-dot"></span>${escapeHtml(m.waitLabel||'正在查看本轮问题…')}</p>`):`<div class="markdown ${failed?'failure-notice':''}">${renderMarkdownSafe(m.content||'上次请求中断，尚未收到完整结果。')}${busy?'<span class="stream-caret"></span>':''}</div>`}${!busy?`<div class="answer-tools">${d?.sources?.length?`<button class="text-button sources-button" type="button" data-sources-message="${escapeHtml(m.id)}">${icon('book')}查看本轮检索依据 · ${d.sources.length} 条</button>`:''}<button class="text-button" type="button" data-copy-message="${escapeHtml(m.id)}">${icon('copy')}复制</button>${failed?`<button class="text-button" type="button" data-retry-message="${escapeHtml(m.id)}">${m.conflict?'重新同步案件':'重试本轮'}</button>`:''}</div>`:''}</div>`;
    }
    return `<article class="message message-ai" data-message-id="${escapeHtml(m.id)}">${answerHeader()}${isCase&&busy?caseProgressHtml(m):''}${content}</article>`;
}
function attachCitations(container,session){
    container.querySelectorAll(':scope > .message-ai').forEach(article=>{
        const m=session.messages.find(x=>x.id===article.dataset.messageId),sources=m?.structured?.sources||[];
        if(!sources.length||m.structured.workflow==='case')return;
        const body=article.querySelector('.markdown');if(!body)return;
        const walker=document.createTreeWalker(body,NodeFilter.SHOW_TEXT);const nodes=[];
        while(walker.nextNode())if(!walker.currentNode.parentElement.closest('a,pre,code,button'))nodes.push(walker.currentNode);
        const markers=new Map();sources.forEach((s,i)=>{markers.set(`[${s.id}]`,i);markers.set(`〔${i+1}〕`,i);});
        const pattern=new RegExp([...markers.keys()].sort((a,b)=>b.length-a.length).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'),'g');
        let occurrence=0;
        nodes.forEach(node=>{const text=node.textContent;let match,last=0;const fragment=document.createDocumentFragment();while((match=pattern.exec(text))){fragment.append(text.slice(last,match.index));const b=document.createElement('button');b.type='button';b.className='citation';b.textContent=String(markers.get(match[0])+1);b.dataset.sourcesMessage=m.id;b.dataset.sourceIndex=markers.get(match[0]);b.dataset.citationLocation=String(occurrence++);b.setAttribute('aria-label','查看依据'+b.textContent);fragment.append(b);last=pattern.lastIndex;}if(last){fragment.append(text.slice(last));node.replaceWith(fragment);}});
    });
}
function citationLocations(messageId,sourceIndex) {
    return [...$('chatInner').querySelectorAll('button.citation')].filter(b=>b.dataset.sourcesMessage===messageId&&Number(b.dataset.sourceIndex)===Number(sourceIndex)).map(b=>({location:b.dataset.citationLocation,preview:(b.closest('p,li,blockquote,td,h1,h2,h3,h4')||b.parentElement).textContent.trim().slice(0,120)}));
}
function returnToCitation(messageId,location) {
    const target=[...$('chatInner').querySelectorAll('button.citation')].find(b=>b.dataset.sourcesMessage===messageId&&b.dataset.citationLocation===String(location));
    if(!target){toast('原回答中没有找到该引用位置，请查看对应历史消息。');return;}
    const block=target.closest('p,li,blockquote,td,h1,h2,h3,h4')||target.parentElement;
    if(innerWidth<1280)closeDetail();
    $('chatInner').querySelectorAll('.citation-highlight').forEach(el=>el.classList.remove('citation-highlight'));
    block.classList.add('citation-highlight');target.focus({preventScroll:true});
    block.scrollIntoView({block:'center',behavior:'instant'});ui().scroll=$('chatBox').scrollTop;persistSessions();announce('已返回原回答的引用位置');
}
function renderMessages(follow=false){
    const s=currentSession(),box=$('chatBox'),previous=box.scrollTop,near=box.scrollHeight-box.scrollTop-box.clientHeight<110;
    $('chatInner').innerHTML=s.messages.length?s.messages.map((m,i)=>renderMessage(m,i,s)).join(''):welcome();
    attachCitations($('chatInner'),s);
    if(follow||near)box.scrollTop=box.scrollHeight;else box.scrollTop=previous;
    $('streamFollowBtn').hidden=!s.messages.length||box.scrollHeight-box.scrollTop-box.clientHeight<110;
}
function renderChrome(){
    const s=currentSession(),d=latestCaseMessage(s)?.structured,busy=pending.has(s.id);
    document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===(s.workspace||'auto'));b.setAttribute('aria-pressed',b.dataset.mode===(s.workspace||'auto'));});
    $('currentModeTitle').textContent=s.workspace==='case'?'案件工作区':'法律咨询';$('sessionSubtitle').textContent=s.messages.length?s.title:'从问题开始，逐步理清';
    $('caseDot').hidden=!d;$('sendMsgBtn').disabled=busy;$('composerHint').textContent=busy?'本轮处理中，可切换其他对话':'Enter 发送 · Shift + Enter 换行';
    const ribbon=$('caseWorkspace');ribbon.hidden=!d;
    ribbon.innerHTML=d?`<div><strong>当前案件 v${d.case_version} · ${escapeHtml(ui(s).uncertain?'结果需同步':ui(s).factDraft?'有尚未应用的修改':caseStatusLabel(d.status))}</strong><span class="coverage-line">资料覆盖${d.coverage?.city?'（'+escapeHtml(d.coverage.city)+'）':''}：${escapeHtml(d.coverage?.message||'地区待明确，暂不确定城市专项适用。')}</span><button type="button" class="text-button" data-latest-sources>查看本次实际检索来源</button></div><button type="button" class="quiet-button" data-show-case>核对案件</button>`:'';
    renderHistoryList();syncModalState();
}
function renderCurrentChat(){
    const s=currentSession();$('messageInput').value=ui(s).composer||'';autoResize();renderChrome();renderMessages(false);$('chatBox').scrollTop=ui(s).scroll||0;renderDetail();
}
function sourceMessage(s=currentSession()){
    const explicit=s.messages.find(m=>m.id===ui(s).sourceMessageId);
    return explicit||latestCaseMessage(s)||[...s.messages].reverse().find(m=>m.structured?.sources?.length);
}
function sourcesHtml(m,selected){
    if(!m?.structured?.sources?.length)return emptyPanel('book','尚无可查看的依据','先提出一个法律问题；回答检索到的依据会显示在这里。');
    return `<p class="panel-intro">${m.structured.workflow==='case'?'本案件版本':'这条回答'}的检索依据。来源存在不代表支持每一项结论，请结合原文与适用条件核对。</p>${m.structured.sources.map((d,i)=>{const locations=citationLocations(m.id,i);return `<section class="source-record ${selected!=null&&i===Number(selected)?'selected-source':''}" data-source-record="${i}"><span class="source-number">依据 ${i+1}${d.type==='case'?' · 案例参考':''}</span><h3>${escapeHtml(d.title)}${d.article?' 第'+escapeHtml(d.article)+'条':''}</h3><div class="citation-context">${locations.length?`<p>回答中的引用位置（请自行核对是否支持该表述）</p>${locations.map((loc,n)=>`<button class="citation-return" type="button" data-return-citation="${escapeHtml(loc.location)}" data-citation-message="${escapeHtml(m.id)}"><strong>返回引用位置 ${n+1}</strong><span>${escapeHtml(loc.preview)}</span></button>`).join('')}`:'<p>本轮检索依据，未建立具体引用位置。</p>'}</div><dl class="source-meta"><dt>版本</dt><dd>${escapeHtml(d.version||'未提供')}</dd><dt>适用地域</dt><dd>${escapeHtml((d.jurisdictions||[]).join('、')||'以原文为准')}</dd><dt>有效期间</dt><dd>${escapeHtml(d.effective_from||'未提供')} 至 ${escapeHtml(d.effective_to||'未列明截止日期')}${d.effective_to?'（截止日不含）':''}</dd><dt>核验日期</dt><dd>${escapeHtml(d.verified_on||'未提供')}</dd></dl><div class="law-text">${escapeHtml(d.original_text||d.key_facts||'当前记录未提供原文，请查看官方出处。')}</div>${d.limits?`<p class="source-limits">适用限制：${escapeHtml(d.limits)}</p>`:''}${/^https?:\/\//.test(d.url||'')?`<a class="source-link" href="${escapeHtml(d.url)}" target="_blank" rel="noopener noreferrer">查看官方原文 ${icon('external')}</a>`:''}</section>`;}).join('')}`;
}
function emptyPanel(name,title,description,button=''){return `<div class="panel-empty">${icon(name)}<h3>${title}</h3><p>${description}</p>${button}</div>`;}
function renderDetail(){
    const s=currentSession(),state=ui(s),panel=$('detailPanel');panel.hidden=!state.panel;
    if(!state.panel){syncModalState();return;}
    const m=state.historyMessageId?s.messages.find(x=>x.id===state.historyMessageId):latestCaseMessage(s),d=m?.structured;
    const historical=!!state.historyMessageId&&m!==latestCaseMessage(s);
    $('detailTitle').textContent={case:historical?'历史案件结果':'当前案件',sources:'法律依据',document:'文书草稿'}[state.panel]||'当前案件';
    $('detailEyebrow').textContent=state.panel==='sources'?'来源属于所选回答':d?`案件 v${d.case_version}${historical?' · 只读':''}`:'工作资料';
    document.querySelectorAll('[data-panel]').forEach(b=>{b.classList.toggle('active',b.dataset.panel===state.panel);b.setAttribute('aria-pressed',b.dataset.panel===state.panel);});
    let html='';
    if(state.panel==='sources')html=sourcesHtml(sourceMessage(s),state.sourceIndex);
    else if(state.panel==='document'){
        const latest=latestCaseMessage(s)?.structured;
        if(historical)html='<p class="history-banner">历史版本仅供查看，不能复制为当前草稿。</p>';
        if(!d)html+=emptyPanel('document','还没有文书草稿','先整理案件事实、请求和金额，再确认生成草稿。','<button class="primary-button" type="button" data-show-case>整理案件</button>');
        else if(historical&&d.document?.markdown)html+=`<div class="document-paper markdown">${renderMarkdownSafe(d.document.markdown)}</div>`;
        else if(draftUsable(d,s)){html+=`<div class="document-toolbar"><p>当前案件 v${d.case_version} · 内部一致性检查通过</p><button type="button" class="quiet-button" data-case-copy>${icon('copy')}复制 Markdown</button></div><p class="panel-intro">仅依据已确认输入整理，证据真实性未经核验。主体信息缺失处保留占位，请补齐后专业复核。</p><div class="document-paper markdown">${renderMarkdownSafe(d.document.markdown)}</div>${preparationSummary(d,s)}`;}
        else html+=`<div class="document-invalid">${state.uncertain?'当前案件操作结果尚未同步，旧草稿暂不可使用。':state.factDraft?'有尚未应用的事实修改，旧草稿暂不可使用。请保存并重新核对。':pending.get(s.id)?.caseOperation?'案件正在重新核对，旧草稿暂不可使用。':d.document_status==='invalidated'?'旧草稿已失效。请核对新事实与金额，并再次确认。':'草稿尚未形成，或版本、确认状态及审查问题仍需核对。'}</div>${renderAmounts(d)}<button type="button" class="primary-button" data-show-case>返回案件核对</button>`;
    } else if(!d)html=pending.get(s.id)?.caseOperation?emptyPanel('folder','正在整理案件','请查看聊天中的真实处理进度，收到阶段结果后再核对事实。'):emptyPanel('folder','先把情况说清楚','可以继续聊天；明确需要核算或准备材料时，再进入案件核对。','<button class="primary-button" type="button" data-start-case>开始整理案件</button>');
    else {
        html=`${historical?'<p class="history-banner">历史版本只读，请以当前案件为准。<button type="button" class="text-button" data-show-case>返回当前案件</button></p>':''}${state.uncertain?'<div class="document-invalid">上次案件操作结果需同步，暂时停止确认与草稿复制。<button type="button" class="text-button" data-sync-case>重新分析并同步</button></div>':''}${pending.get(s.id)?.caseOperation?`<section class="case-section"><div class="section-body" style="padding-top:12px"><p class="conversation-wait"><span class="wait-dot"></span>正在核对当前案件</p><div id="liveProcess">${renderProcess(pending.get(s.id).events||[])}</div></div></section>`:''}${buildCaseReport(d,m.content,m.runtimeStatus)}`;
    }
    const content=$('detailContent'),scroll=content.scrollTop;content.innerHTML=html;
    if(state.panel==='case'&&d){
        if(!historical)restoreDraft(s,d);
        content.querySelectorAll('details[data-section]').forEach(el=>{if(state.sections&&el.dataset.section in state.sections)el.open=state.sections[el.dataset.section];});
        const disabled=historical||pending.has(s.id)||state.uncertain;
        if(disabled)content.querySelectorAll('.case-report input,.case-report select,.case-report [data-case-save],.case-report [data-case-confirm],.case-report [data-case-add-wage],.case-report [data-case-remove-wage],.case-report [data-edit-facts]').forEach(el=>el.disabled=true);
        if(!historical&&state.selection?.version===d.case_version)content.querySelectorAll('[name="selected_claim"]').forEach(el=>el.checked=state.selection.ids.includes(el.value));
        if(state.factDraft)content.querySelectorAll('[data-case-confirm]').forEach(el=>el.disabled=true);
        const label=content.querySelector('[data-dirty-label]');if(label)label.hidden=!state.factDraft;
        applyFactGuide(s,d,historical);
        syncCaseAvailability(s,d,historical);
    }
    content.scrollTop=scroll;syncModalState();
}
function renderAmounts(d){return `<div class="panel-intro">${(d.calculations||[]).map(r=>`<p>${escapeHtml(d.claims?.find(c=>c.id===r.claim_id)?.title||'条件测算')}：${r.amount==null?'待核验':escapeHtml(r.amount)+'元'}<br>${escapeHtml(r.formula||'')}</p>`).join('')}</div>`;}
function factGuideState(data,state={}) {
    const saved=state.factGuide;
    return saved?.version===data.case_version?{mode:saved.mode==='full'?'full':'guide',step:Math.max(0,Math.min(2,Math.trunc(Number(saved.step))||0))}:{mode:data.status==='needs_information'?'guide':'full',step:0};
}
function syncCaseAvailability(session,data,historical=false) {
    const content=$('detailContent'),state=ui(session);
    const reason=historical?'':state.uncertain?'结果需同步，以下为上次保存的测算；同步前不能确认或复制草稿。':state.factDraft?'以下金额仍基于上次保存的输入，尚未应用的修改没有参与计算；请保存并重新分析。':pending.get(session.id)?.caseOperation?'正在核对案件，以下仍为上次保存的测算，请等待本轮结果。':'';
    const note=content.querySelector('[data-amount-pending]');if(note){note.hidden=!reason;note.textContent=reason;}
    content.querySelectorAll('.calculation-label').forEach(el=>el.textContent=reason?'上次保存输入的测算（待核对）':'按当前输入进行规则测算');
    if(data.document_status==='reviewed_draft'&&!draftUsable(data,session))content.querySelector('.case-heading .status-label').textContent=historical?'历史草稿记录（只读）':'草稿暂不可使用';
}
function applyFactGuide(session,data,historical=false) {
    const form=$('detailContent').querySelector('.case-fact-form');if(!form)return;
    const guide=factGuideState(data,ui(session)),guided=!historical&&guide.mode==='guide';
    form.classList.toggle('guided-facts',guided);
    form.querySelector('[data-guide-mode]').textContent=guided?'查看全部字段':'分步填写';
    form.querySelector('[data-guide-mode]').disabled=historical||pending.has(session.id)||!!ui(session).uncertain;
    form.querySelector('[data-guide-nav]').hidden=!guided;
    form.querySelector('[data-guide-actions]').hidden=!guided;
    form.querySelector('[data-guide-note]').hidden=historical;
    form.querySelectorAll('[data-guide-group]').forEach(el=>{el.hidden=guided&&Number(el.dataset.guideGroup)!==guide.step;if(guided&&!el.hidden)el.open=true;});
    form.querySelectorAll('[data-guide-step]').forEach(b=>{const selected=Number(b.dataset.guideStep)===guide.step;b.classList.toggle('active',selected);if(selected)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');b.disabled=pending.has(session.id)||!!ui(session).uncertain;});
    form.querySelector('[data-guide-back]').disabled=guide.step===0||pending.has(session.id)||!!ui(session).uncertain;
    form.querySelector('[data-guide-next]').hidden=guide.step===2;
    form.querySelector('[data-guide-next]').disabled=pending.has(session.id)||!!ui(session).uncertain;
    form.querySelector('[data-case-save]').hidden=guided&&guide.step!==2;
}
function changeFactGuide({mode,step,edit=false}={}) {
    const session=currentSession(),data=latestCaseMessage(session)?.structured;
    if(!data||ui(session).historyMessageId||pending.has(session.id)||ui(session).uncertain)return;
    captureDraft(session,false);
    const old=factGuideState(data,ui(session));
    ui(session).factGuide={version:data.case_version,mode:mode||(edit?'guide':old.mode),step:Math.max(0,Math.min(2,step??old.step))};
    applyFactGuide(session,data);
    const form=$('detailContent').querySelector('.case-fact-form');
    if(ui(session).factGuide.mode==='full')form.querySelectorAll('[data-guide-group]').forEach(el=>el.open=true);
    const heading=form.querySelector('[data-fact-heading]');heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:'instant'});
    persistSessions();announce('已切换填写方式，尚未提交或重新分析');
}
function openDetail(kind='case',options={}){
    const s=currentSession();if(!s)return;
    if($('detailPanel').hidden)returnFocus=document.activeElement;
    captureDraft(s,false);Object.assign(ui(s),{panel:kind},options);
    if(kind==='case'||kind==='document')ui(s).sourceMessageId=ui(s).historyMessageId||latestCaseMessage(s)?.id||null;
    renderDetail();persistSessions();
    if(options.sourceIndex!=null)requestAnimationFrame(()=>$('detailContent').querySelector(`[data-source-record="${Number(options.sourceIndex)}"]`)?.scrollIntoView({block:'start'}));
    else $('detailContent').scrollTop=0;
    if(innerWidth<1280)$('closeDetailBtn').focus();
}
function closeDetail(){captureDraft(currentSession(),false);ui().panel=null;renderDetail();persistSessions();if(returnFocus?.isConnected)returnFocus.focus();else $('openCaseBtn').focus();}
function syncModalState(){
    const detailOpen=!$('detailPanel').hidden&&innerWidth<1280,navOpen=$('sidebar').classList.contains('open')&&innerWidth<1280;
    $('detailOverlay').hidden=!detailOpen;$('mainWorkspace').inert=detailOpen||navOpen;
    $('sidebar').inert=detailOpen||(!navOpen&&innerWidth<1280);
    if(detailOpen){$('detailPanel').setAttribute('role','dialog');$('detailPanel').setAttribute('aria-modal','true');}else{$('detailPanel').removeAttribute('role');$('detailPanel').removeAttribute('aria-modal');}
}
function captureDraft(s=currentSession(),mark=true){
    if(!s||s.id!==currentSessionId||ui(s).panel!=='case'||ui(s).historyMessageId)return;
    const form=$('detailContent').querySelector('.case-fact-form'),d=latestCaseMessage(s)?.structured;if(!form||!d)return;
    ui(s).sections=Object.fromEntries([...$('detailContent').querySelectorAll('details[data-section]')].map(el=>[el.dataset.section,el.open]));
    if(!mark){if(ui(s).factDraft)ui(s).factDraft={...ui(s).factDraft,values:[...form.querySelectorAll('input,select')].map(el=>[el.name,el.value])};return;}
    ui(s).factDraft={baseVersion:d.case_version,values:[...form.querySelectorAll('input,select')].map(el=>[el.name,el.value]),wageRows:form.querySelectorAll('.case-wage-row').length};
    form.querySelector('[data-dirty-label]').hidden=false;$('detailContent').querySelectorAll('[data-case-confirm]').forEach(b=>b.disabled=true);
    syncCaseAvailability(s,d);
    persistSessions();renderChrome();renderMessages();
}
function restoreDraft(s,d){
    const draft=ui(s).factDraft,form=$('detailContent').querySelector('.case-fact-form');if(!draft||!form)return;
    if(draft.baseVersion!==d.case_version){delete ui(s).factDraft;toast('案件版本已变化，未应用的旧编辑已移除，请基于新版本重新填写。');return;}
    const rows=form.querySelector('.case-wages');rows.innerHTML=Array.from({length:draft.wageRows||0},()=>wageRow()).join('');
    const counts=new Map();for(const [name,value]of draft.values){const all=[...form.querySelectorAll('[name]')].filter(x=>x.name===name),i=counts.get(name)||0;if(all[i])all[i].value=value;counts.set(name,i+1);}
    form.querySelector('[name="termination_basis"]')?.dispatchEvent(new Event('change',{bubbles:true}));
}
async function guardUnsaved(){
    const s=currentSession();captureDraft(s,false);if(!ui(s).factDraft)return true;
    const dialog=$('unsavedDialog');dialog.showModal();
    const choice=await new Promise(resolve=>{const onClick=e=>{const b=e.target.closest('[data-unsaved]');if(b){cleanup();resolve(b.dataset.unsaved);}},onCancel=e=>{e.preventDefault();cleanup();resolve('cancel');};function cleanup(){dialog.removeEventListener('click',onClick);dialog.removeEventListener('cancel',onCancel);dialog.close();}dialog.addEventListener('click',onClick);dialog.addEventListener('cancel',onCancel);});
    if(choice==='cancel')return false;
    if(choice==='discard'){delete ui(s).factDraft;persistSessions();return true;}
    if(choice==='save'){if(pending.has(s.id)){toast('请等待本轮完成后再保存。');return false;}if(ui(s).panel!=='case'||ui(s).historyMessageId)openDetail('case',{historyMessageId:null});return saveCaseFacts();}
    return false;
}
async function switchSession(id){if(id===currentSessionId)return;if(!await guardUnsaved())return;const previous=currentSession();ui(previous).scroll=$('chatBox').scrollTop;ui(previous).composer=$('messageInput').value;currentSessionId=id;closeSidebar(false);persistSessions();renderCurrentChat();}
async function createNewSession(){if(!await guardUnsaved())return;const old=currentSession();ui(old).scroll=$('chatBox').scrollTop;ui(old).composer=$('messageInput').value;const s=makeSession();sessions.unshift(s);currentSessionId=s.id;closeSidebar(false);persistSessions();renderCurrentChat();$('messageInput').focus();}
async function deleteSession(id){if(pending.has(id)){toast('该对话仍在处理中，请完成后再删除。');return;}if(id===currentSessionId&&!await guardUnsaved())return;sessions=sessions.filter(s=>s.id!==id);if(!sessions.length)sessions=[makeSession()];if(currentSessionId===id)currentSessionId=sessions[0].id;persistSessions();renderCurrentChat();}
function createSseParser(onEvent){let buffer='';return chunk=>{buffer+=chunk;const blocks=buffer.split(/\r?\n\r?\n/);buffer=blocks.pop()||'';for(const block of blocks){let event='message';const lines=[];for(const line of block.split(/\r?\n/)){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))lines.push(line.slice(5).trimStart());}if(lines.length){let data;try{data=JSON.parse(lines.join('\n'));}catch{throw new Error('收到无法解析的服务响应，本轮未完成。');}onEvent(event,data);}}};}
async function readStreamingResponse(response,onEvent){const reader=response.body?.getReader();if(!reader)throw new Error('浏览器无法读取流式响应。');const decoder=new TextDecoder(),parse=createSseParser(onEvent);while(true){const {value,done}=await reader.read();if(done)break;parse(decoder.decode(value,{stream:true}));}parse(decoder.decode());}
async function sendMessage(options={}){
    const s=currentSession(),sid=s.id;if(pending.has(sid))return false;
    const text=String(options.query??$('messageInput').value).trim();if(!text)return false;
    if(!options.fromFactSave&&ui(s).factDraft&&!await guardUnsaved())return false;
    if(currentSessionId!==sid)return false;
    const req={query:text,session_id:sid,workflow:'consultation',...(options.request||{})};
    if(s.messages.length===0)s.title=inferTitle(text);
    s.messages.push({id:generateId(),role:'user',content:text,timestamp:Date.now()});
    const m={id:generateId(),role:'ai',content:'',structured:null,runtimeStatus:'thinking',timestamp:Date.now()};s.messages.push(m);
    const operation={caseOperation:req.workflow==='case',events:[],req};pending.set(sid,operation);
    ui(s).composer='';$('messageInput').value='';autoResize();let completed=false,result=null;
    if(operation.caseOperation){s.workspace='case';ui(s).panel='case';ui(s).historyMessageId=null;}
    persistSessions();renderChrome();renderMessages(true);if(operation.caseOperation)renderDetail();
    let frame=0;
    const update=(detail=false)=>{persistSessions();if(currentSessionId!==sid)return;if(detail){renderChrome();renderDetail();}if(!frame)frame=requestAnimationFrame(()=>{frame=0;if(currentSessionId===sid)renderMessages();});};
    try{
        const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
        if(!response.ok){const p=await response.json().catch(()=>({}));m.conflict=response.status===409;throw new Error(response.status===409?'案件版本已变化。请重新同步案件，核对后再次确认。':typeof p.detail==='string'?p.detail:`本轮请求未完成（HTTP ${response.status}），已有结果已保留。`);}
        await readStreamingResponse(response,(event,data)=>{
            if(event==='task_started'||event==='task_completed'){
                const first=!operation.caseOperation;operation.caseOperation=true;s.workspace='case';
                const index=operation.events.findIndex(x=>x.task===data.task);const item={...data,status:event==='task_started'?'running':data.status};if(index<0)operation.events.push(item);else operation.events[index]=item;
                m.caseProgress=operation.events;
                if(event==='task_started'&&data.task!=='confirmation')m.awaitingCaseConfirmation=false;
                m.waitLabel=caseTaskLabel(data.task)+' · '+(event==='task_started'?'正在执行':'阶段已返回');
                if(first&&currentSessionId===sid){ui(s).panel='case';ui(s).historyMessageId=null;renderDetail();}
                if(currentSessionId===sid){const live=$('liveProcess');if(live)live.innerHTML=renderProcess(operation.events);renderChrome();}
                if(currentSessionId===sid&&event==='task_started')announce('正在'+caseTaskLabel(data.task));
            }
            if(event==='review_issue'){(m.reviewEvents ||= []).push(data);}
            if(event==='confirmation_required'){m.waitLabel='当前请求与金额已返回，等待核对';m.awaitingCaseConfirmation=true;}
            if(event==='thinking')m.waitLabel=data.message||'正在查看本轮问题…';
            if(event==='route')m.route=data.route;
            if(event==='structured'){m.structured=data.structured||null;m.runtimeStatus='streaming';}
            if(event==='token'){m.content+=(data.delta||'');m.runtimeStatus='streaming';}
            if(event==='error'){m.runtimeStatus='error';m.content=data.message||'本轮未完成，已有案件结果已保留。';m.conflict=data.code===409;}
            if(event==='done'){
                m.content=data.answer??m.content;m.structured=data.structured||m.structured;m.route=data.route||m.route;m.runtimeStatus='complete';completed=true;result=data;
                if(m.structured?.workflow==='case'){s.workspace='case';delete ui(s).factDraft;delete ui(s).selection;delete ui(s).uncertain;ui(s).historyMessageId=null;ui(s).sections={};if(currentSessionId===sid)ui(s).panel='case';}
            }
            update();
        });
        if(!completed&&m.runtimeStatus!=='error')throw new Error('连接已中断，未收到完整结果；请核对后重试。');
    }catch(error){m.content=error.message||'本轮请求未完成。';m.runtimeStatus='error';}
    finally{
        pending.delete(sid);
        if(operation.caseOperation&&!completed)ui(s).uncertain=true;
        if(frame)cancelAnimationFrame(frame);persistSessions();
        if(currentSessionId===sid){renderChrome();renderMessages();renderDetail();announce(completed?'本轮回答已完成':'本轮未完成，已有结果已保留');}
        else renderHistoryList();
    }
    return completed&&!!result;
}
async function saveCaseFacts(){
    const s=currentSession(),form=$('detailContent').querySelector('.case-fact-form'),d=latestCaseMessage(s)?.structured;if(!form||!d)return false;
    if(ui(s).historyMessageId||pending.has(s.id)||ui(s).uncertain){toast('请先返回并同步当前案件。');return false;}
    try{const facts=collectCaseFacts(form);return await sendMessage({query:'修正案件事实并重新分析',fromFactSave:true,request:{workflow:'case',action:'analyze',expected_case_version:d.case_version,facts}});}catch(e){toast(e.message);return false;}
}
async function confirmCase(){
    const s=currentSession(),d=latestCaseMessage(s)?.structured;if(!d||ui(s).factDraft||ui(s).uncertain||pending.has(s.id)||ui(s).historyMessageId)return;
    const selected=[...$('detailContent').querySelectorAll('input[name="selected_claim"]:checked:not(:disabled)')].map(el=>el.value);
    if(!selected.length){toast('请先选择本次主张的请求。');return;}
    await sendMessage({query:'确认当前版本的事实、请求与金额',request:{workflow:'case',action:'confirm',expected_case_version:d.case_version,selected_claims:selected}});
}
async function copyText(text){try{await navigator.clipboard.writeText(text);toast('已复制');}catch{toast('浏览器未允许复制，请选择正文手动复制。');}}
function openSidebar(){sidebarFocus=document.activeElement;$('sidebar').classList.add('open');$('sidebarOverlay').hidden=false;syncModalState();$('closeSidebarBtn').focus();}
function closeSidebar(focus=true){$('sidebar').classList.remove('open');$('sidebarOverlay').hidden=true;syncModalState();if(focus&&sidebarFocus?.isConnected)sidebarFocus.focus();}
function autoResize(){const el=$('messageInput');el.style.height='auto';el.style.height=Math.min(el.scrollHeight,innerWidth<768?110:144)+'px';}
document.addEventListener('click',async event=>{
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.session)return switchSession(b.dataset.session);
    if(b.dataset.deleteSession)return deleteSession(b.dataset.deleteSession);
    if(b.dataset.example!=null){$('messageInput').value=EXAMPLES[Number(b.dataset.example)][3];ui().composer=$('messageInput').value;persistSessions();autoResize();$('messageInput').focus();return;}
    if(b.dataset.mode){const s=currentSession();s.workspace=b.dataset.mode;closeSidebar(false);renderChrome();if(b.dataset.mode==='case')openDetail('case',{historyMessageId:null});else closeDetail();persistSessions();return;}
    if(b.dataset.panel){openDetail(b.dataset.panel);return;}
    if(b.hasAttribute('data-show-case')||b.id==='openCaseBtn'){openDetail('case',{historyMessageId:null});return;}
    if(b.hasAttribute('data-start-case')){await sendMessage({query:'开始整理我的劳动争议案件',request:{workflow:'case',action:'analyze'}});return;}
    if(b.dataset.caseMessage){openDetail('case',{historyMessageId:b.dataset.caseMessage===latestCaseMessage()?.id?null:b.dataset.caseMessage});return;}
    if(b.dataset.sourcesMessage){openDetail('sources',{sourceMessageId:b.dataset.sourcesMessage,sourceIndex:b.dataset.sourceIndex??null});return;}
    if(b.hasAttribute('data-return-citation')){returnToCitation(b.dataset.citationMessage,b.dataset.returnCitation);return;}
    if(b.hasAttribute('data-latest-sources')){openDetail('sources',{sourceMessageId:latestCaseMessage()?.id,sourceIndex:null});return;}
    if(b.hasAttribute('data-current-sources')){openDetail('sources',{sourceMessageId:(ui().historyMessageId||latestCaseMessage()?.id),sourceIndex:null});return;}
    if(b.hasAttribute('data-open-document')){openDetail('document',{historyMessageId:null});return;}
    if(b.dataset.copyMessage){const m=currentSession().messages.find(x=>x.id===b.dataset.copyMessage);if(m)await copyText(m.content);return;}
    if(b.hasAttribute('data-case-copy')){const d=latestCaseMessage()?.structured;if(draftUsable(d)&&!ui().historyMessageId)await copyText(d.document.markdown);else toast('请返回并核对当前有效草稿后再复制。');return;}
    if(b.hasAttribute('data-edit-facts')){changeFactGuide({edit:true,step:0});return;}
    if(b.hasAttribute('data-guide-mode')){const d=latestCaseMessage()?.structured;changeFactGuide({mode:factGuideState(d,ui()).mode==='guide'?'full':'guide'});return;}
    if(b.dataset.guideStep!=null){changeFactGuide({step:Number(b.dataset.guideStep)});return;}
    if(b.hasAttribute('data-guide-next')||b.hasAttribute('data-guide-back')){const d=latestCaseMessage()?.structured;changeFactGuide({step:factGuideState(d,ui()).step+(b.hasAttribute('data-guide-next')?1:-1)});return;}
    if(b.hasAttribute('data-case-add-wage')){b.previousElementSibling.insertAdjacentHTML('beforeend',wageRow());captureDraft();return;}
    if(b.hasAttribute('data-case-remove-wage')){b.closest('.case-wage-row').remove();captureDraft();return;}
    if(b.hasAttribute('data-case-save')){await saveCaseFacts();return;}
    if(b.hasAttribute('data-case-confirm')){await confirmCase();return;}
    if(b.hasAttribute('data-sync-case')){await sendMessage({query:'重新核对当前案件，不确认或生成文书',fromFactSave:true,request:{workflow:'case',action:'analyze'}});return;}
    if(b.dataset.retryMessage){const s=currentSession(),i=s.messages.findIndex(m=>m.id===b.dataset.retryMessage),m=s.messages[i];if(m?.conflict){await sendMessage({query:'重新核对当前案件，不确认或生成文书',request:{workflow:'case',action:'analyze'}});}else{const previous=[...s.messages.slice(0,i)].reverse().find(x=>x.role==='user');if(previous)await sendMessage({query:previous.content});}return;}
});
$('sendMsgBtn').addEventListener('click',()=>sendMessage());$('newChatBtn').addEventListener('click',createNewSession);
$('mobileMenuBtn').addEventListener('click',openSidebar);$('closeSidebarBtn').addEventListener('click',()=>closeSidebar());$('sidebarOverlay').addEventListener('click',()=>closeSidebar());
$('closeDetailBtn').addEventListener('click',closeDetail);$('detailOverlay').addEventListener('click',closeDetail);
$('messageInput').addEventListener('input',()=>{ui().composer=$('messageInput').value;autoResize();persistSessions();});
$('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendMessage();}});
$('detailContent').addEventListener('input',e=>{if(e.target.closest('.case-fact-form'))captureDraft();});
$('detailContent').addEventListener('submit',e=>{if(e.target.matches('.case-fact-form'))e.preventDefault();});
$('detailContent').addEventListener('change',e=>{if(e.isTrusted&&e.target.closest('.case-fact-form'))captureDraft();if(e.target.name==='selected_claim'){ui().selection={version:latestCaseMessage()?.structured.case_version,ids:[...$('detailContent').querySelectorAll('[name="selected_claim"]:checked')].map(el=>el.value)};persistSessions();}});
$('detailContent').addEventListener('toggle',e=>{if(e.target.matches('details[data-section]')){(ui().sections ||= {})[e.target.dataset.section]=e.target.open;persistSessions();}},true);
$('chatBox').addEventListener('scroll',()=>{ui().scroll=$('chatBox').scrollTop;$('streamFollowBtn').hidden=$('chatBox').scrollHeight-$('chatBox').scrollTop-$('chatBox').clientHeight<110;},{passive:true});
$('streamFollowBtn').addEventListener('click',()=>{$('chatBox').scrollTop=$('chatBox').scrollHeight;});
document.addEventListener('keydown',e=>{
    if($('unsavedDialog').open)return;
    const modal=!$('detailPanel').hidden&&innerWidth<1280?$('detailPanel'):$('sidebar').classList.contains('open')?$('sidebar'):null;
    if(e.key==='Escape'){if(!$('detailPanel').hidden)closeDetail();else closeSidebar();}
    if(e.key==='Tab'&&modal){const all=[...modal.querySelectorAll('button,a,input,select,textarea,summary,[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length);if(!all.length)return;const first=all[0],last=all.at(-1);if(e.shiftKey&&(document.activeElement===first||!modal.contains(document.activeElement))){e.preventDefault();last.focus();}else if(!e.shiftKey&&(document.activeElement===last||!modal.contains(document.activeElement))){e.preventDefault();first.focus();}}
});
window.addEventListener('resize',()=>{syncModalState();autoResize();$('streamFollowBtn').hidden=!currentSession().messages.length||$('chatBox').scrollHeight-$('chatBox').scrollTop-$('chatBox').clientHeight<110;});
if(window.visualViewport)visualViewport.addEventListener('resize',()=>{document.querySelector('.app-shell').style.height=visualViewport.height+'px';});
window.addEventListener('beforeunload',e=>{if(sessions.some(s=>s.ui?.factDraft)||pending.size){e.preventDefault();e.returnValue='';}persistSessions();});
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
loadSessions();renderCurrentChat();
