from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from pydantic import ValidationError
from .models import CaseFacts, empty_case
from .facts import extract, LABELS
from .fact_checks import employment_statement, date_checks, consistency_issues
from .knowledge import KnowledgeRegistry, coverage, CITIES
from .calculation import calculate, RULE_VERSION
from .roles import ReviewAgent, model_analysis
from .model_policy import profile_digest
from .review_revision import citation_feedback, facts_digest, guard_snapshot, restore_if_mutated

class CaseConflict(Exception):
    def __init__(self,current_version):
        self.current_version=current_version
        super().__init__('案件版本已变化，请查看新金额并重新确认。')

class CaseInputError(ValueError): pass

WORKFLOW_VERSION='casework-20261026-v16'

class GraphState(TypedDict):
    case: dict
    req: dict

class CaseWorkflow:
    def __init__(self,registry=None,qa=None,judge=None,doc=None,review=None,model_runner=None):
        from legal_ai_agent.agents.qa_agent import QAAgent
        from legal_ai_agent.agents.judge_agent import JudgeAgent
        from legal_ai_agent.agents.doc_agent import DocAgent
        self.registry=registry or KnowledgeRegistry(); self.qa=qa or QAAgent(); self.judge=judge or JudgeAgent();self.doc=doc or DocAgent()
        self.review=review or ReviewAgent();self.model_runner=model_runner;self.emit=lambda *args:None

    def run(self,req,case,emit=None):
        self.emit=emit or (lambda *args:None)
        for key in ('stages','failures','model_calls'): case[key]=[]
        case['analysis_repair']={'attempts':0,'status':'not_requested','feedback':[]}
        graph=StateGraph(GraphState)
        nodes=[('intake',self.intake),('retrieval',self.retrieval),('analysis',self.analysis),('calculation',self.calculation),('analysis_review',self.analysis_review),('confirmation',self.confirmation),('document',self.document),('document_review',self.document_review),('analysis_revision',self.analysis_revision),('analysis_recheck',self.analysis_recheck)]
        for name,fn in nodes:
            graph.add_node(name,self.wrap(name,fn))
        graph.add_edge(START,'intake')
        for (name,_),(next_name,_) in zip(nodes[:4],nodes[1:5]): graph.add_edge(name,next_name)
        graph.add_conditional_edges('analysis_review',lambda s:'analysis_revision' if s['case']['analysis_repair']['status']=='pending' else 'confirmation',['analysis_revision','confirmation'])
        graph.add_conditional_edges('analysis_revision',lambda s:'analysis_recheck' if s['case']['analysis_repair']['status']=='revised' else 'confirmation',['analysis_recheck','confirmation'])
        graph.add_edge('analysis_recheck','confirmation')
        graph.add_conditional_edges('confirmation',lambda s:'document' if s['case'].get('status')=='confirmed' else END,['document',END])
        graph.add_conditional_edges('document',lambda s:'document_review' if s['case'].get('document') else END,['document_review',END])
        graph.add_edge('document_review',END)
        result=graph.compile().invoke({'case':case,'req':req})
        return self.payload(result['case'])

    def wrap(self,name,fn):
        def invoke(state):
            case=state['case']; start=time.monotonic()
            self.emit('task_started',{'task':name,'case_version':case['case_version']})
            try:
                failures_before=len(case['failures'])
                fn(case,state['req'])
                status='failed' if len(case['failures'])>failures_before else 'completed'
            except (CaseConflict,CaseInputError,ValidationError): raise
            except Exception as exc:
                reason=type(exc).__name__+': '+str(exc)[:180]
                case['failures'].append({'stage':name,'reason':reason}); case['status']='failed'
                case['review_issues'].append({'code':'stage_failed','severity':'critical','message':name+'执行失败，已保留阶段产物。'})
                case['confirmation']=None
                if name=='document_review' and case.get('document'):
                    case['document']['status']='blocked';case['document_status']='review_blocked'
                else:
                    case['document']=None;case['document_status']='invalidated'
                status='failed'
            entry={'task':name,'status':status,'seconds':round(time.monotonic()-start,3),'case_version':case['case_version']}
            case['stages'].append(entry);self.emit('task_completed',entry)
            return {'case':case}
        return invoke

    def intake(self,case,req):
        action=req.get('action','analyze')
        if action not in ('analyze','confirm','generate_document'): raise CaseInputError('action必须为analyze、confirm或generate_document')
        explicit=req.get('facts') or {}
        if not isinstance(explicit,dict): raise CaseInputError('facts必须为对象')
        patch,extraction_conflicts=extract(req.get('query',''),with_conflicts=True)
        from legal_ai_agent.conversation import wage_revision
        revised_wages = wage_revision(str(req.get('query','')),case)
        if revised_wages is not None:
            patch['wages'] = revised_wages
        statement_source=None
        if 'wage_statement' in explicit:
            stated,quote,conflict=employment_statement(explicit['wage_statement'])
            if conflict:extraction_conflicts.append({'field':'employment_status','message':'工资陈述同时包含在职和已离职，请明确本轮劳动期间。'})
            if 'employment_status' not in explicit:
                query_status=patch.get('employment_status')
                if query_status in ('active','terminated') and stated in ('active','terminated') and query_status!=stated:
                    stated='unknown';extraction_conflicts.append({'field':'employment_status','message':'本轮文字与工资陈述的在职状态不一致，请澄清。'})
                if stated is not None:
                    patch['employment_status']=stated
                    statement_source={'source':'user_statement_extraction','input_field':'wage_statement','statement':quote[:500]}
                elif case.get('fact_sources',{}).get('employment_status',{}).get('input_field')=='wage_statement':
                    patch['employment_status']='unknown'
                    statement_source={'source':'user_statement_extraction','input_field':'wage_statement','statement':'修改后无明确在职状态陈述，不沿用旧提取值。'}
        extracted_evidence=patch.get('evidence',{})
        if 'evidence' in explicit and not isinstance(explicit['evidence'],dict): raise CaseInputError('evidence必须为按材料名记录持有状态的对象。')
        patch.update(explicit)
        if 'evidence' in explicit:patch['evidence']={**extracted_evidence,**explicit['evidence']}
        if action in ('confirm','generate_document'):
            expected=req.get('expected_case_version')
            if not isinstance(expected,int) or isinstance(expected,bool): raise CaseInputError('确认必须提供整数expected_case_version')
            if expected!=case['case_version']: raise CaseConflict(case['case_version'])
            if patch: raise CaseInputError('确认动作不能同时修改事实，请先分析新版本。')
        dependencies={'knowledge_digest':self.registry.data['digest'],'rule_version':RULE_VERSION,'workflow_version':WORKFLOW_VERSION,'model_profile_sha256':profile_digest()}
        dependencies_changed=case['case_version']>0 and (case.get('dependencies')!=dependencies or case.get('knowledge_digest')!=self.registry.data['digest'])
        old=deepcopy(case['facts']); merged={**old,**patch}
        if 'evidence' in patch: merged['evidence']={**old.get('evidence',{}),**patch['evidence']}
        validated=CaseFacts.model_validate(merged).model_dump(mode='json')
        changes={k:{'old':old.get(k),'new':v} for k,v in validated.items() if old.get(k)!=v}
        if changes or case['case_version']==0 or dependencies_changed:
            case['case_version']+=1
            case['revisions'].append({'case_version':case['case_version'],'changes':changes,'dependencies_changed':dependencies_changed,'time':datetime.now(timezone.utc).isoformat(),'invalidated':['analysis','calculations','confirmation','document']})
            case['revisions']=case['revisions'][-30:]
            case.update(facts=validated,claims=[],sources=[],calculations=[],confirmation=None,document=None,document_status='invalidated',review_issues=[],missing_info=[],status='intake',analysis={})
            for key in patch:
                case['fact_sources'][key]={'source':'user_structured' if key in explicit else 'user_text_extraction','statement':req.get('query','')[:500], 'confirmed':False,'case_version':case['case_version'],'evidence_verified':False}
            if statement_source:
                case['fact_sources']['employment_status'].update(statement_source)
            for name in patch.get('evidence',{}):
                case['fact_sources']['evidence.'+name]={'source':'user_structured' if name in explicit.get('evidence',{}) else 'user_text_extraction','statement':req.get('query','')[:500],'confirmed':False,'case_version':case['case_version'],'evidence_verified':False}
            for source in case['fact_sources'].values(): source['confirmed']=False
            case['dependencies']=dependencies
            if dependencies_changed and action!='analyze': raise CaseConflict(case['case_version'])
        if 'employment_status' in patch and 'employment_status' not in explicit:
            provenance=statement_source or {'source':'user_text_extraction','input_field':'query','statement':req.get('query','')[:500]}
            case['fact_sources']['employment_status']={**provenance,'confirmed':False,'case_version':case['case_version'],'evidence_verified':False}
        # A retry rechecks all previous failures, not previous conclusions.
        case['review_issues']=[];case['missing_info']=[]
        conflicts={c['field']:c for c in case.get('fact_conflicts',[])}
        for field in list(conflicts):
            if field.startswith('evidence.'):
                resolved=patch.get('evidence',{}).get(field.split('.',1)[1]) in ('claimed_present','missing')
            elif field=='employment_status':resolved=patch.get(field) in ('active','terminated')
            else: resolved=field in patch and patch[field] is not None
            if resolved:conflicts.pop(field)
        for conflict in extraction_conflicts:
            field=conflict['field']
            resolved=(field in explicit and explicit[field] is not None) or (field.startswith('evidence.') and explicit.get('evidence',{}).get(field.split('.',1)[1]) in ('claimed_present','missing'))
            if not resolved:conflicts[field]=conflict
        case['fact_conflicts']=list(conflicts.values())
        for conflict in case['fact_conflicts']:
            case['review_issues'].append(dict(code='fact_conflict',severity='critical',message=conflict['message']))
        f=case['facts']
        case['date_checks']=date_checks(f)
        case['review_issues']+=consistency_issues(f)
        for key in ('workplace','employer_city','dispute_date'):
            if not f.get(key): case['missing_info'].append(key)
        if f.get('workplace') and f.get('employer_city') and f['workplace']!=f['employer_city'] and not f['cross_city_resolved']:
            case['missing_info'].append('cross_city_resolved')
        if f.get('workplace') in ('香港','澳门') or f.get('actual_cross_border_work') is True:
            case['review_issues'].append(dict(code='cross_border',severity='critical',message='实际跨境履行或港澳履行须专业判断适用法律，首期停止内地自动测算。'))
        if f.get('workplace') and f['workplace'] not in CITIES and f['workplace'] not in ('香港','澳门'):
            case['review_issues'].append(dict(code='region_unsupported',severity='critical',message='当前案件协同仅适配大湾区内地九市。'))
        if f['employment_type']!='ordinary': case['review_issues'].append(dict(code='special_employment',severity='critical',message='特殊用工须专业复核。'))
        if f.get('start_date') and f['start_date']<'2008-01-01':case['review_issues'].append(dict(code='pre2008',severity='critical',message='涉及2008年前工龄，需分段专业复核，停止简化补偿计算。'))

    def retrieval(self,case,req):
        case['sources']=[]
        case['sources']=self.qa.retrieve_case_sources(case,self.registry)
        case['knowledge_version']=self.registry.data['version'];case['knowledge_digest']=self.registry.data['digest']

    def analysis(self,case,req):
        # Judge uses the same state and the same calculation eligibility contract.
        claims,_,_,_=calculate(case['facts'],self.registry,case['case_version'])
        case['claims']=claims
        case['analysis']=self.judge.analyze_case(case,runner=self.model_runner)

    def calculation(self,case,req):
        claims,results,missing,issues=calculate(case['facts'],self.registry,case['case_version'])
        case['claims']=claims;case['calculations']=results
        case['missing_info']=list(dict.fromkeys(case['missing_info']+missing))
        case['review_issues']+=issues
        if any(i['code'] in ('cross_border','region_unsupported','special_employment') for i in case['review_issues']):
            for result in case['calculations']: result.update(amount=None,status='professional_review_required')
        case['artifacts_version']=case['case_version']

    def analysis_review(self,case,req):
        issues=self.review.review_analysis(case,runner=self.model_runner)
        self.record_analysis_review(case,'initial',issues)
        feedback=citation_feedback(case,issues)
        if feedback:
            case['analysis_repair'].update(status='pending',feedback=feedback,preserved_rule_issues=deepcopy(case['review_issues']))
        case['review_issues']+=issues
        for issue in case['review_issues']: self.emit('review_issue',issue)

    def record_analysis_review(self,case,phase,issues):
        ids={key for issue in issues for key in issue.get('source_ids',[])}
        history=case.setdefault('analysis_review_history',[])
        history.append({'case_version':case['case_version'],'phase':phase,'time':datetime.now(timezone.utc).isoformat(),
                        'facts_sha256':facts_digest(case),'analysis':deepcopy(case['analysis']),
                        'model_review':deepcopy(case.get('model_review')),'issues':deepcopy(issues),
                        'source_refs':[{k:d.get(k) for k in ('id','title','article','url','version')}
                                       for d in case['sources'] if d['id'] in ids]})
        case['analysis_review_history']=history[-20:]

    def analysis_revision(self,case,req):
        repair=case['analysis_repair'];repair.update(attempts=1,status='running')
        protected=guard_snapshot(case)
        try:
            candidate=self.judge.analyze_case(case,runner=self.model_runner)
        except Exception:
            repair['status']='failed'
            raise
        finally:
            changed=restore_if_mutated(case,protected)
            if changed:
                repair.update(status='blocked',changed_fields=changed)
                raise ValueError('分析修订试图改变受保护状态，已恢复：'+','.join(changed))
        if candidate.get('status')!='model_augmented':
            repair['status']='failed';return
        case['analysis']=candidate;repair['status']='revised'

    def analysis_recheck(self,case,req):
        issues=self.review.review_analysis(case,runner=self.model_runner)
        self.record_analysis_review(case,'after_revision',issues)
        case['review_issues']=deepcopy(case['analysis_repair']['preserved_rule_issues'])+issues
        case['analysis_repair']['status']='review_blocked' if any(i['severity']=='critical' for i in case['review_issues']) or case['failures'] else 'review_passed'
        for issue in case['review_issues']:self.emit('review_issue',issue)

    def confirmation(self,case,req):
        action=req.get('action','analyze');critical=any(i['severity']=='critical' for i in case['review_issues'])
        if case['missing_info'] or critical or case['failures']:
            case['confirmation']=None;case['document']=None;case['document_status']='invalidated'
            case['status']='needs_information' if case['missing_info'] else 'review_blocked'
            if action!='analyze': case['review_issues'].append(dict(code='confirmation_blocked',severity='critical',message='尚有关键缺失或审查问题，不能确认。'))
            return
        eligible=[c for c in case['claims'] if c['status']=='conditional']
        if not eligible:
            case.update(status='no_supported_claim',confirmation=None,document=None,document_status='not_generated')
            if action!='analyze': raise CaseInputError('当前事实没有满足首期条件的请求，请先澄清解除争议或补充欠薪信息。')
            return
        if action=='analyze':
            case['status']='awaiting_confirmation';case['confirmation']=None;case['document']=None;case['document_status']='invalidated'
            self.emit('confirmation_required',{'case_version':case['case_version'],'claims':case['claims'],'calculations':case['calculations']});return
        selected=req.get('selected_claims') or []
        if not isinstance(selected,list) or not selected or not all(isinstance(s,str) for s in selected): raise CaseInputError('请选择本次主张的请求selected_claims')
        selected=set(selected);known={c['id']:c for c in case['claims']};calc={r['claim_id']:r for r in case['calculations']}
        if not selected<=known.keys(): raise CaseInputError('未知请求编号')
        if {'N','2N'}<=selected or {'2N','notice'}<=selected: raise CaseInputError('N、2N及代通知金存在互斥或备选关系，不能累计选择。')
        if any(known[s]['status']!='conditional' or calc.get(s,{}).get('amount') is None for s in selected): raise CaseInputError('所选请求的条件或金额尚未满足确认要求。')
        snapshot={'facts':case['facts'],'calculations':case['calculations'],'selected_claims':sorted(selected),'knowledge_digest':case['knowledge_digest']}
        case['confirmation']={'case_version':case['case_version'],'selected_claims':sorted(selected),'snapshot_hash':hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'time':datetime.now(timezone.utc).isoformat(),'evidence_verified':False}
        for source in case['fact_sources'].values(): source['confirmed']=True
        case['status']='confirmed';case['document_status']='not_generated'

    def document(self,case,req):
        case['document']=self.doc.draft_case(case,runner=self.model_runner)

    def document_review(self,case,req):
        issues=self.review.review_document(case)
        if issues:
            case['document']=self.doc.draft_case(case,runner=self.model_runner);case['document']['revision_count']=1
            issues=self.review.review_document(case)
        case['review_issues']+=issues
        for issue in issues: self.emit('review_issue',issue)
        case['document_status']='review_blocked' if issues else 'reviewed_draft'
        case['status']='document_blocked' if issues else 'draft_ready'
        if issues: case['document']['status']='blocked'

    def payload(self,case):
        f=case['facts']; missing=[LABELS.get(k,k) for k in case['missing_info']]
        lines=[f"案件版本 {case['case_version']}："+{'no_supported_claim':'\u5f53\u524d\u4e8b\u5b9e\u6ca1\u6709\u6ee1\u8db3\u9996\u671f\u6761\u4ef6\u7684\u8bf7\u6c42','needs_information':'需要补充事实或参数','review_blocked':'待专业复核','awaiting_confirmation':'请确认事实、请求与金额','draft_ready':'仲裁申请书草稿已完成一致性审查','document_blocked':'文书审查未通过'}.get(case['status'],case['status']),coverage(f.get('workplace'))['message']]
        if missing: lines+=['待补信息：'+ '；'.join(missing)]
        for result in case['calculations']:
            title=next((c['title'] for c in case['claims'] if c['id']==result['claim_id']),result['claim_id'])
            lines.append(f"{title}：{result['amount']+' 元（条件测算）' if result['amount'] is not None else '保留公式，待核验参数'}；{result['formula']}")
        lines += [i['message'] for i in case['review_issues']]
        materials=[name for name in ('劳动合同','工资流水','解除通知','考勤','聊天记录') if f.get('evidence',{}).get(name)!='claimed_present']
        subjects=[key for key in ('applicant','applicant_id','applicant_address','applicant_phone','employer_name','employer_address','employer_representative') if not f.get(key)]
        if case.get('document') and case['document_status']=='reviewed_draft':
            lines.append(case['document']['markdown']);lines.append('待补材料：'+('、'.join(materials) or '无已知缺项')+'。主体信息占位：'+('、'.join(LABELS.get(key,key) for key in subjects) or '已填写，待核验'))
        answer='\n\n'.join(lines)
        return {'reply':answer,'answer':answer,'route':'case','structured':{'workflow':'case',**deepcopy(case),'coverage':coverage(f.get('workplace')),'confirmation_required':case['status']=='awaiting_confirmation','missing_labels':missing,'materials_needed':materials,'subject_fields_needed':subjects,'legal_review':'internal_check_not_expert_review'}}
