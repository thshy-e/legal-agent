"""Document role consumes confirmed structured case state only."""

class DocAgent:
    def draft_case(self, case, runner=None):
        from legal_ai_agent.casework.roles import draft_case
        return draft_case(case, runner)

    def run(self, info):
        # Text-only legacy callers cannot provide versioned confirmation.
        return "请进入案件协同，补充并确认当前版本的事实、请求和金额后生成仲裁申请书草稿。"
