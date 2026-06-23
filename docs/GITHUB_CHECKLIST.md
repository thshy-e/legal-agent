# GitHub 上传前检查清单

## 必须保留

- `legal_ai_agent/`：核心后端包。
- `frontend/`：Web 单页应用。
- `tests/`：回归测试。
- `data/law/`、`data/case/`、`data/raw/`：演示数据和知识库源文件。
- `docs/`：架构、API、项目文档和评估材料。
- `requirements.txt`、`.env.example`、`.gitignore`、`.gitattributes`。
- `app.py`、`start_server.py`、`build_db.py`：清晰运行入口。

## 不应上传

- `.env`
- `venv/` 或 `.venv/`
- `.idea/`、`.vscode/`
- `chroma_db/`
- `db/conversation_state.json`
- `__pycache__/`
- `*.pyc`
- 临时日志、调试输出、个人本地测试产物

## 上传前命令

```powershell
.\venv\Scripts\python.exe -m unittest discover
git status --short --untracked-files=all
```

如果看到 `.idea/`、`venv/`、`chroma_db/`、`db/conversation_state.json` 准备被提交，请先确认 `.gitignore` 是否生效。

## 推荐提交顺序

```powershell
git add .gitignore .gitattributes README.md requirements.txt .env.example
git add app.py start_server.py build_db.py frontend legal_ai_agent data docs tests db/.gitkeep
git status --short
git commit -m "Prepare legal AI agent project for GitHub"
```

## 面试展示建议

建议在 README 顶部重点讲三件事：

1. 这是劳动法垂直领域的多 Agent 系统，不是通用聊天壳。
2. 有确定性赔偿计算和多轮上下文协同，解决真实业务链路问题。
3. 有完整回归测试，尤其覆盖同一会话内跨功能混跑和上下文隔离。

