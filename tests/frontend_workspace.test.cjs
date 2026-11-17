// Behavior checks for the browser controller without adding a frontend framework.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('frontend/workspace.js','utf8').split("document.addEventListener('click',async event=>{")[0];
function harness(){
  const elements=new Map();
  const context=vm.createContext({console,TextDecoder,ReadableStream,Map,Set,Date,Math,JSON,Number,String,Array,Object,RegExp,Error,Promise,setTimeout,clearTimeout,caseTaskLabel:task=>task,renderProcess:stages=>JSON.stringify(stages),document:{getElementById(id){if(!elements.has(id))elements.set(id,{value:'',textContent:'',style:{},scrollTop:0});return elements.get(id);}},localStorage:{setItem(){}},requestAnimationFrame:()=>1,cancelAnimationFrame(){}});
  vm.runInContext(source,context);
  vm.runInContext(`renderChrome=()=>{};renderMessages=()=>{};renderDetail=()=>{};renderHistoryList=()=>{};persistSessions=()=>{};autoResize=()=>{};announce=()=>{};`,context);
  return {context,elements,run:code=>vm.runInContext(code,context)};
}
function response(events){const raw=events.map(([event,data])=>`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');return {ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(raw));c.close();}})};}
test('SSE handles split blocks, CRLF and multiline data without swallowing handler errors',()=>{
  const h=harness();h.run('var seen=[];var parse=createSseParser((event,data)=>seen.push([event,data]));');
  for(const chunk of ['event: token\r\nda','ta: {"delta":"工"}\r\n\r','\nevent: done\ndata: {"answer":\ndata: "完成"}\n\n']){h.context.chunk=chunk;h.run('parse(chunk)');}
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(seen)')),[['token',{delta:'工'}],['done',{answer:'完成'}]]);
  assert.throws(()=>h.run('createSseParser(()=>{throw Error("handler")})(\'data: {}\\n\\n\')'),/handler/);
  assert.throws(()=>h.run('parse(\'data: {oops}\\n\\n\')'),/无法解析/);
});
test('explicit historical source selection remains attached to its answer',()=>{
  const h=harness();h.run(`sessions=[{id:'a',ui:{sourceMessageId:'first'},messages:[{id:'first',structured:{sources:[{id:'labor47'}]}},{id:'latest',structured:{workflow:'case',sources:[{id:'contract47'}]}}]}];currentSessionId='a';`);
  assert.equal(h.run('sourceMessage().structured.sources[0].id'),'labor47');
});
test('late case response updates its originating conversation while another conversation stays untouched',async()=>{
  const h=harness();let resolveFetch,request;
  h.context.fetch=async(_url,args)=>{request=JSON.parse(args.body);return new Promise(resolve=>resolveFetch=resolve);};
  h.run(`sessions=[{id:'a',messages:[],ui:{},workspace:'auto'},{id:'b',messages:[],ui:{panel:'sources',sourceMessageId:'b-source'},workspace:'auto'}];currentSessionId='a';`);
  const work=h.run(`sendMessage({query:'整理案件',request:{workflow:'case',action:'analyze'}})`);
  h.run(`currentSessionId='b';`);
  resolveFetch(response([['task_started',{task:'intake',case_version:0}],['done',{answer:'已分析',route:'case',structured:{workflow:'case',case_version:1,status:'needs_information'}}]]));
  assert.equal(await work,true);assert.equal(request.session_id,'a');
  assert.equal(h.run(`sessions[0].messages.at(-1).structured.case_version`),1);
  assert.equal(h.run(`sessions[1].messages.length`),0);
  assert.equal(h.run(`sessions[1].ui.panel`),'sources');
  assert.equal(h.run(`sessions[1].ui.sourceMessageId`),'b-source');
  assert.equal(h.run(`sessions[1].workspace`),'auto');assert.equal(h.run('pending.size'),0);
});
test('failed case write marks only that case uncertain and never retries confirmation',async()=>{
  const h=harness();let calls=0;
  h.context.fetch=async()=>{calls++;return {ok:false,status:409,json:async()=>({detail:{case_version:3}})};};
  h.run(`sessions=[{id:'a',messages:[],ui:{},workspace:'case'}];currentSessionId='a';`);
  assert.equal(await h.run(`sendMessage({query:'确认',request:{workflow:'case',action:'confirm',expected_case_version:2,selected_claims:['arrears']}})`),false);
  assert.equal(calls,1);assert.equal(h.run('ui().uncertain'),true);assert.equal(h.run('currentSession().messages.at(-1).conflict'),true);
});
test('failed ordinary consultation preserves existing case validity',async()=>{
  const h=harness();h.context.fetch=async()=>{throw Error('offline');};
  h.run(`sessions=[{id:'a',messages:[{id:'old',structured:{workflow:'case',case_version:2,document_status:'reviewed_draft'}}],ui:{},workspace:'auto'}];currentSessionId='a';`);
  assert.equal(await h.run(`sendMessage({query:'为什么需要工资流水？'})`),false);
  assert.equal(h.run('latestCaseMessage().structured.document_status'),'reviewed_draft');
  assert.equal(h.run('!!ui().uncertain'),false);assert.equal(h.run('pending.size'),0);
});
test('reload during an unfinished stream preserves artifacts and requires case sync',()=>{
  const h=harness();
  const stored=[{id:'a',messages:[{id:'old',role:'ai',content:'draft',structured:{workflow:'case',case_version:2,document_status:'reviewed_draft'}},{id:'pending',role:'ai',content:'',runtimeStatus:'thinking'}],ui:{panel:'document'}}];
  h.context.localStorage.getItem=key=>key==='laborhub_active_session_v17'?'a':JSON.stringify(stored);
  h.run('loadSessions()');
  assert.equal(h.run('latestCaseMessage().structured.document_status'),'reviewed_draft');
  assert.equal(h.run('ui().uncertain'),true);
  assert.equal(h.run('currentSession().messages.at(-1).runtimeStatus'),'interrupted');
});

function validDraft(h){
  h.run(`sessions=[{id:'a',ui:{},messages:[{id:'case',role:'ai',structured:{workflow:'case',case_version:4,status:'draft_ready',document_status:'reviewed_draft',confirmation:{case_version:4,selected_claims:['arrears']},document:{case_version:4,markdown:'# 仲裁申请书\\n8000.10元'},claims:[{id:'arrears',title:'欠薪'},{id:'N',title:'补偿金'}],calculations:[{claim_id:'arrears',amount:'8000.10',formula:'9000.10 - 1000.00'},{claim_id:'N',amount:'99999.00'}],materials_needed:['工资流水'],subject_fields_needed:['applicant']}}]}];currentSessionId='a';`);
}
test('draft availability requires matching current confirmation and document, and pauses on local edits',()=>{
  const h=harness();validDraft(h);
  assert.equal(h.run('draftUsable(latestCaseMessage().structured)'),true);
  for(const change of ['ui().factDraft={baseVersion:4}','ui().uncertain=true',"pending.set('a',{caseOperation:true})",'latestCaseMessage().structured.confirmation.case_version=3','latestCaseMessage().structured.document.case_version=3','latestCaseMessage().structured.document.markdown=""',"latestCaseMessage().structured.review_issues=[{severity:'critical'}]","latestCaseMessage().structured.failures=[{stage:'document_review'}]"]){
    validDraft(h);h.run('pending.clear()');h.run(change);assert.equal(h.run('draftUsable(latestCaseMessage().structured)'),false,change);
  }
  validDraft(h);h.run("pending.clear();pending.set('a',{caseOperation:false})");
  assert.equal(h.run('draftUsable(latestCaseMessage().structured)'),true,'ordinary explanations preserve the draft');
  h.run("currentSession().messages.push({structured:{workflow:'case',case_version:5}})");
  assert.equal(h.run('draftUsable(currentSession().messages[0].structured)'),false,'old snapshots cannot be current drafts');
});
test('preparation summary uses only confirmed requests and disappears without discarding stored draft',()=>{
  const h=harness();validDraft(h);
  const html=h.run('preparationSummary(latestCaseMessage().structured,currentSession())');
  assert.match(html,/8000\.10/);assert.doesNotMatch(html,/99999/);assert.match(html,/工资流水/);assert.match(html,/申请人姓名/);assert.match(html,/尚未提交仲裁/);
  h.run('ui().factDraft={baseVersion:4}');assert.equal(h.run('preparationSummary(latestCaseMessage().structured,currentSession())'),'');
  assert.match(h.run('latestCaseMessage().structured.document.markdown'),/8000\.10/);
});
test('received progress persists real stages only and preserves interruption rather than implying completion',async()=>{
  const h=harness();h.context.fetch=async()=>response([
    ['task_started',{task:'intake',case_version:1}],['task_completed',{task:'intake',status:'completed',seconds:0.1}],
    ['task_started',{task:'retrieval',case_version:1}],['error',{message:'连接中断'}]
  ]);
  h.run("sessions=[{id:'a',ui:{},messages:[]}];currentSessionId='a';");
  assert.equal(await h.run("sendMessage({query:'核算欠薪',request:{workflow:'case'}})"),false);
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(currentSession().messages.at(-1).caseProgress.map(s=>s.task))')),['intake','retrieval']);
  const html=h.run('caseProgressHtml(currentSession().messages.at(-1))');
  assert.match(html,/已中断/);assert.match(html,/intake/);assert.doesNotMatch(html,/analysis|document|100%/);
  assert.equal(h.run('ui().uncertain'),true);
});
test('ordinary consultation reports retrieved sources without claiming internal or expert review',()=>{
  const h=harness();h.run('renderMarkdownSafe=text=>escapeHtml(text)');
  const html=h.run(`renderMessage({id:'ask',role:'ai',content:'法条解释',runtimeStatus:'complete',structured:{presentation:{kind:'conversation'},sources:[{id:'law'}]}},0,{id:'a',messages:[]})`);
  assert.match(html,/本轮检索依据/);assert.doesNotMatch(html,/审查通过|专家审核|内部一致性|case-summary/);
});
test('citation context is bound to the originating answer and source, not the newest case',()=>{
  const h=harness();
  const button=(message,index,location,text)=>({dataset:{sourcesMessage:message,sourceIndex:String(index),citationLocation:String(location)},closest:()=>({textContent:text})});
  h.elements.set('chatInner',{querySelectorAll:()=>[button('old',0,0,'旧回答中的引用'),button('new',0,0,'新案件同编号'),button('old',1,1,'旧回答另一法条')]});
  const locations=JSON.parse(h.run("JSON.stringify(citationLocations('old',0))"));
  assert.deepEqual(locations,[{location:'0',preview:'旧回答中的引用'}]);
});
test('blocking reviews sort first and open by default; facts retain all existing condition fields',()=>{
  const h=harness();h.context.document.addEventListener=()=>{};
  vm.runInContext(fs.readFileSync('frontend/casework.js','utf8'),h.context);
  h.run(`var data={case_version:1,status:'needs_information',facts:{article40_conditions:false},review_issues:[{severity:'info',message:'说明'},{severity:'critical',message:'不能确认<script>'},{severity:'warning',message:'等待核实'}],claims:[]};`);
  const html=h.run('buildCaseReport(data)');
  assert.ok(html.indexOf('review-critical')<html.indexOf('review-warning'));assert.ok(html.indexOf('review-warning')<html.indexOf('review-info'));
  assert.match(html,/data-section="issues" open/);assert.match(html,/&lt;script&gt;/);assert.match(html,/不表示败诉风险/);
  for(const field of ['worker38_conditions','article40_conditions','protected_status','layoff_procedure'])assert.match(html,new RegExp(`name="${field}"`));
  assert.match(html,/value="false" selected/);assert.match(html,/data-guide-group="2"/);
});
test('guide defaults and saved position remain UI-only and do not advance versions',()=>{
  const h=harness();
  h.run("var data={case_version:7,status:'needs_information',facts:{monthly_average:'9000.00'}};var state={factGuide:{version:7,mode:'guide',step:2}};");
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(factGuideState(data,state))')),{mode:'guide',step:2});
  assert.deepEqual(JSON.parse(h.run("JSON.stringify(factGuideState({...data,case_version:8},state))")),{mode:'guide',step:0});
  assert.equal(h.run("factGuideState({...data,status:'awaiting_confirmation'},{}).mode"),'full');
  assert.equal(h.run('data.case_version'),7);assert.equal(h.run('data.facts.monthly_average'),'9000.00');
});
