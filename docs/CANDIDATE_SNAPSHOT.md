# 工程交付包与重建验收

2026-10-27 按用户要求以 v17 完成前端重设计工程交付；后端沿用v16。完整范围及限制见[工程交付说明](PROJECT_HANDOFF.md)。本包为可审查工程快照，不表示全部法律验收完成或比赛最终提交版。

```powershell
.\venv\Scripts\python.exe scripts/package_contest_candidate.py create output/releases/labor-casework-handoff-20261027-v17.zip
.\venv\Scripts\python.exe scripts/package_contest_candidate.py verify output/releases/labor-casework-handoff-20261027-v17.zip
```

创建拒绝覆盖已有压缩包；create 命令仅在尚未生成交付包时使用。包内 CANDIDATE_MANIFEST.json 记录逐文件大小、SHA256、基础 Git 提交、依赖与验证摘要及未完成项。工作目录包含未提交修改，以逐文件哈希识别内容。整包哈希位于包外 .zip.sha256，解压验收位于包外同名 .verification.json；实际通过情况以该外部记录为准，不能移用历史包结果。

显式选择源码、前端、测试、脚本、公开法源及数据、交付文档、逐案实验和复核产物、合成输入录屏。排除 .env、私有 JSON 会话、生成索引、虚拟环境、Git 目录及未选择的旧文档；创建时检查所选文件是否含当前配置密钥。教学资料不因此成为现行法源，检索仍以版本清单为入口。

当前版本 frontend-20261027-v17，后端 casework-20261026-v16 / conversation-20261026-v16，知识摘要 b9b3767d4c14。146 项Python回归、6项Node回归及公开工程集 60 案通过；自然咨询13个公开合成场景预设工程检查通过（10次真实Qwen调用），另保留浏览器中一次解释失败记录。历史v15的真实混合模型欠薪四阶段单次通过，十场景九项满足严格工程预期，一项审查超时。广深补偿封顶参数、专家复核、独立盲测仍未完成。学校申报书及新增配音视频按用户要求暂缓。

解压验收在独立目录执行导入路径检查、build_db.py --activate、回归及公开工程集。复用本机解释器，解压目录不含密钥，默认规则模式。此方法检验源码遗漏及对原目录索引/会话的依赖，不能证明全新环境安装或跨平台兼容。

requirements-win-py312.snapshot.txt 是本机 Windows、CPython 3.12.6 环境快照，不替代 requirements.txt。历史 v4/v6/v9/v14 候选及 v15/v16 交付包和验收记录保留原字节，不包含当前 v17 全部修改。v15 真实实验目录里的 executed_source_v15.zip 只是部分执行源码存证，不替代本次完整工程包。

v17独立解压还运行Node行为回归。真人六人测试与实体手机键盘未完成，见evaluation/frontend_v17/USABILITY_TEST.md；本机解释器复用不代表全新系统安装验证。
