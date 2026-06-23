# API 说明

## `POST /api/chat`

同步聊天接口。

### 请求体

```json
{
  "query": "月薪10000，工作3年，被公司突然辞退且无补偿，能拿多少？",
  "session_id": "demo-session",
  "preferred_mode": "qa",
  "ui_mode": "qa",
  "mode": "qa",
  "force_mode": false
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `query` | 是 | 用户本轮问题 |
| `session_id` | 否 | 会话 ID，缺省为 `user_web` |
| `preferred_mode` | 否 | UI 模式偏好，支持 `qa/doc/risk/judge` |
| `ui_mode` | 否 | 前端展示模式偏好，语义同 `preferred_mode` |
| `mode` | 否 | 兼容旧字段；默认也按偏好处理 |
| `force_mode` | 否 | 只有为 `true` 时才硬强制 `mode` |

### 响应体

```json
{
  "reply": "当前争议核心不在测算数字本身...",
  "answer": "当前争议核心不在测算数字本身...",
  "route": "qa",
  "structured": {
    "route": "qa",
    "calculation": {
      "show": true,
      "status": "complete",
      "amount": "60000",
      "formula": "3 x 10000 x 2",
      "wage": "10000",
      "years": "3",
      "months": "3",
      "compensation_type": "2N赔偿"
    },
    "metrics": [],
    "risk": {},
    "evidence": [],
    "timeline": [],
    "actions": [],
    "issues": [],
    "conversation": {
      "session_id": "demo-session",
      "is_continuation": false,
      "turn_count": 1,
      "last_route": "qa",
      "known_facts": {
        "salary": 10000,
        "years": 3,
        "termination_reason": "非法辞退"
      },
      "used_previous_calculation": false,
      "route_reason": "explicit_calculation_intent"
    }
  }
}
```

## `POST /api/chat/stream`

SSE 流式聊天接口。请求体同 `/api/chat`。

事件顺序：

| event | data |
| --- | --- |
| `route` | `{ "route": "qa" }` |
| `thinking` | `{ "status": "thinking", "message": "..." }` |
| `structured` | `{ "structured": { ... } }` |
| `token` | `{ "delta": "..." }`，可多次 |
| `done` | `{ "answer": "...", "route": "...", "structured": { ... } }` |
| `error` | `{ "message": "...", "route": "error" }` |

## 路由取值

| route | 说明 |
| --- | --- |
| `qa` | 法律问答或赔偿计算快路径 |
| `doc` | 仲裁申请书、投诉书、和解协议等文书生成 |
| `risk` | 企业规章制度或用工行为风险评估 |
| `judge` | 案件预判、胜诉率、证据强弱和维权策略 |

## 常见请求示例

### 赔偿计算

```json
{
  "session_id": "case-001",
  "query": "月薪10000，工作3年，被公司突然辞退且无补偿，能拿多少？",
  "preferred_mode": "judge"
}
```

期望：虽然偏好是 `judge`，但明确计算意图会进入 `qa` 计算快路径。

### 普通法条问答

```json
{
  "session_id": "case-001",
  "query": "劳动法第68条是什么"
}
```

期望：走 `qa`，且不注入上轮案件计算上下文。

### 案件连续追问

```json
{
  "session_id": "case-001",
  "query": "结合我上面的情况，劳动合同法第47条怎么适用？"
}
```

期望：走 `qa`，允许注入前文工资、年限、解除性质和计算金额。

### 文书生成

```json
{
  "session_id": "case-001",
  "query": "用以上内容生成仲裁申请书",
  "preferred_mode": "judge"
}
```

期望：走 `doc`，文书中引用前文金额或计算摘要。

