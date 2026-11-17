"""Observe successful and rejected completions without inventing usage."""
import json
from pydantic import ValidationError


def _mapping(value):
    if isinstance(value,dict):return value
    if hasattr(value,'model_dump'):return value.model_dump()
    return {}


def _output(record,content):
    text=str(content)
    record.update(output=text[:12000],output_log_truncated=len(text)>12000)


def observe_response(record,response):
    metadata=getattr(response,'response_metadata',None) or {}
    record.update(actual_model=metadata.get('model_name') or 'unknown',
                  finish_reason=metadata.get('finish_reason'),
                  usage=getattr(response,'usage_metadata',None),metadata_source='model_response')
    content=response.content if hasattr(response,'content') else response
    _output(record,content)
    if record['finish_reason']=='length':raise ValueError('output_truncated: 输出达到长度上限，不能视为完整结构化结果。')
    return content


def observe_exception(record,exc):
    """OpenAI parse can raise before LangChain constructs an AIMessage."""
    completion=_mapping(getattr(exc,'completion',None))
    if not completion:return
    usage=_mapping(completion.get('usage'))
    counts={key:usage.get(raw) for key,raw in
            (('input_tokens','prompt_tokens'),('output_tokens','completion_tokens'),('total_tokens','total_tokens'))}
    complete=all(isinstance(value,int) and not isinstance(value,bool) and value>=0 for value in counts.values())
    normalized=None
    if complete:
        inputs=_mapping(usage.get('prompt_tokens_details'));outputs=_mapping(usage.get('completion_tokens_details'))
        normalized={**counts,
            'input_token_details':{k:inputs[v] for k,v in (('cache_read','cached_tokens'),('audio','audio_tokens')) if inputs.get(v) is not None},
            'output_token_details':{k:outputs[v] for k,v in (('reasoning','reasoning_tokens'),('audio','audio_tokens')) if outputs.get(v) is not None}}
    choices=completion.get('choices') or []
    choice=_mapping(choices[0]) if choices else {}
    record.update(actual_model=completion.get('model') or 'unknown',finish_reason=choice.get('finish_reason'),
                  usage=normalized,raw_usage=usage or None,metadata_source='sdk_exception_completion')
    content=_mapping(choice.get('message')).get('content')
    if content is not None:_output(record,content)


def correction_error(exc):
    if isinstance(exc,ValidationError):
        fields=[{'path':'.'.join(map(str,e['loc'])),'type':e['type'],'message':e['msg'][:160]}
                for e in exc.errors(include_input=False,include_url=False)[:12]]
        return json.dumps({'error_type':type(exc).__name__,'invalid_fields':fields},ensure_ascii=False)
    if type(exc).__name__=='LengthFinishReasonError':
        return 'output_truncated: 上次输出达到长度上限。请缩短问题说明，只保留必需字段和直接相关的短片段，不省略source_ids或关键事实锚点。'
    return type(exc).__name__+': '+str(exc)[:320]
