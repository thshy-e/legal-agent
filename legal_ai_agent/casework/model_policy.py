"""Bounded production model profiles, separate from frozen ablation settings."""
import hashlib
import json
import os


def role_profile(role):
    model = os.getenv('CASE_REVIEW_MODEL', 'qwen-plus').strip() if role == 'Review' else 'qwen-plus'
    if model not in ('qwen-plus', 'qwen3.8-max'):
        raise ValueError('Unsupported CASE_REVIEW_MODEL; use qwen-plus or qwen3.8-max')
    thinking = model == 'qwen3.8-max'
    return {'requested_model': model, 'temperature': 0.1,
            'timeout': 90 if thinking else 60, 'max_retries': 0,
            'max_tokens': 4096 if thinking else 2400,
            'response_format': {'type': 'json_object'},
            'enable_thinking': thinking,
            'reasoning_effort': 'low' if thinking else None}


def profile_digest():
    from legal_ai_agent.config.settings import QWEN_API_KEY
    policy = {'enabled': os.getenv('CASE_MODEL_ENABLED', '1' if QWEN_API_KEY else '0') == '1',
              'roles': {role: role_profile(role) for role in ('Judge', 'Review', 'Doc')}}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
