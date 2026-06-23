from typing import Any, Optional

from legal_ai_agent.tools.calculator import calculate_compensation, extract_case_facts


class CaseProfileStore:
    """轻量结构化案件状态，按 session_id 保存可复用事实。"""

    def __init__(self):
        self._profiles: dict[str, dict[str, Any]] = {}

    def update(self, session_id: str, query: str) -> dict[str, Any]:
        profile = self._profiles.setdefault(session_id, {})
        facts = extract_case_facts(query)
        for key, value in facts.items():
            if value not in (None, "", 0):
                profile[key] = value
        return dict(profile)

    def get(self, session_id: str) -> dict[str, Any]:
        return dict(self._profiles.get(session_id, {}))

    def maybe_contextual_calculation(self, session_id: str, query: str) -> Optional[str]:
        profile = self.get(session_id)
        if not {"salary", "years", "termination_reason"}.issubset(profile):
            return None

        current_facts = extract_case_facts(query)
        just_completed_profile = bool({"salary", "years"} & current_facts.keys())
        if not just_completed_profile:
            return None

        reason = profile.get("termination_reason")
        if reason == "待判断辞退":
            n_result = calculate_compensation(
                {
                    "years": profile["years"],
                    "salary": profile["salary"],
                    "reason": "合法解除",
                }
            )
            two_n_result = calculate_compensation(
                {
                    "years": profile["years"],
                    "salary": profile["salary"],
                    "reason": "非法辞退",
                }
            )
            return (
                "已根据前文案件状态补全：你提到被辞退，本轮补充了工资/年限。\n"
                "目前辞退是否合法还需结合证据判断，因此先给两个口径：\n\n"
                "【合法解除/N口径】\n"
                f"{n_result}\n\n"
                "【违法解除/2N口径】\n"
                f"{two_n_result}\n\n"
                "下一步建议补充：辞退理由、是否有书面通知、规章制度依据、考核/违纪证据。"
            )

        return (
            "已根据前文案件状态补全工资、年限和解除性质：\n\n"
            + calculate_compensation(
                {
                    "years": profile["years"],
                    "salary": profile["salary"],
                    "reason": reason,
                }
            )
        )
