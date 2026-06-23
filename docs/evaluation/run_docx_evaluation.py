import argparse
import csv
import json
import re
import statistics
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVAL_DIR = ROOT / "docs" / "evaluation"
OUT_DIR = EVAL_DIR / "current_results"

DOCS = {
    "qa": EVAL_DIR / "劳动法智能问答系统测试用例集.docx",
    "memory": EVAL_DIR / "四、多轮记忆测试（MemorySaver）.docx",
    "rag": EVAL_DIR / "RAG检索测试用例（30组）.docx",
    "risk": EVAL_DIR / "五、风险评估测试（RiskAgent）.docx",
    "doc": EVAL_DIR / "七、文书生成测试（DocAgent）.docx",
    "comparison": EVAL_DIR / "九、对比实验测试（核心验证模块）.docx",
    "judge": EVAL_DIR / "六、案件预判测试（JudgeAgent）.docx",
    "calculation": EVAL_DIR / "赔偿计算引擎测试及统计.docx",
}

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

DOMAIN_TERMS = [
    "劳动合同", "劳动合同法", "劳动法", "社会保险法", "工资支付暂行规定", "工伤保险条例",
    "司法解释", "指导案例", "仲裁", "劳动仲裁", "劳动监察", "起诉", "诉讼",
    "违法解除", "无理由", "辞退", "解除", "经济补偿", "赔偿金", "补偿金",
    "2N", "N+1", "代通知金", "双倍工资", "加班费", "休息日", "法定节假日",
    "未签", "未缴社保", "补缴", "滞纳金", "罚款", "最低工资", "社平工资",
    "工伤", "工伤认定", "停工留薪", "伤残", "医疗费", "劳动能力鉴定",
    "竞业限制", "保密", "补偿", "拖欠工资", "催收", "工资流水",
    "劳动合同", "考勤", "聊天记录", "微信", "邮件", "诊断证明", "病历",
    "工作证", "同事证言", "辞退通知", "证据", "证据清单", "维权路径",
    "申请书", "仲裁申请书", "投诉书", "起诉状", "和解协议", "答辩状",
    "高风险", "中风险", "低风险", "合规", "法律依据", "法律后果", "整改建议",
    "胜诉率", "案件性质", "赔偿范围", "时效", "一年", "关键证据",
]

STOP_WORDS = {
    "公司", "员工", "用户", "输入", "输出", "要求", "需要", "明确", "完整",
    "格式", "事实", "理由", "标准", "结果", "金额", "清晰", "建议", "相关",
    "核心", "用例", "模块", "测试", "验证", "根据", "包含", "引用", "说明",
}


def extract_tables(path: Path) -> list[list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    tables = []
    for tbl in root.findall(".//w:tbl", NS):
        rows = []
        for tr in tbl.findall(".//w:tr", NS):
            cells = []
            for tc in tr.findall("./w:tc", NS):
                text = "".join(t.text or "" for t in tc.findall(".//w:t", NS)).strip()
                cells.append(re.sub(r"\s+", " ", text))
            if any(cells):
                rows.append(cells)
        tables.append(rows)
    return tables


def rows_as_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    if not table:
        return []
    header = table[0]
    rows = []
    for row in table[1:]:
        item = {}
        for idx, key in enumerate(header):
            item[key] = row[idx] if idx < len(row) else ""
        rows.append(item)
    return rows


def short(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", str(text or ""))


def extract_expected_amounts(text: str) -> list[str]:
    amounts = []
    for match in re.finditer(r"=\s*(\d+(?:\.\d+)?)\s*元", text):
        amounts.append(match.group(1))
    if amounts:
        return amounts
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*元", text):
        amounts.append(match.group(1))
    return amounts[-1:] if amounts else []


def extract_tokens(expected: str) -> list[str]:
    expected = str(expected or "")
    tokens = []
    tokens.extend(re.findall(r"《[^》]+》", expected))
    tokens.extend(re.findall(r"第[一二三四五六七八九十百千万\d]+条(?:第\s*\d+\s*项)?", expected))
    tokens.extend(re.findall(r"\d+(?:\.\d+)?%?", expected))
    for term in DOMAIN_TERMS:
        if term in expected:
            tokens.append(term)
    for part in re.split(r"[，。；;、（）()：:\s/]+", expected):
        part = part.strip()
        if 2 <= len(part) <= 8 and part not in STOP_WORDS:
            if re.search(r"[\u4e00-\u9fff]", part):
                tokens.append(part)
    deduped = []
    for token in tokens:
        if token and token not in deduped:
            deduped.append(token)
    return deduped[:40]


def token_hits(output: str, expected: str) -> tuple[int, int, float, list[str], list[str]]:
    out = normalize(output)
    tokens = extract_tokens(expected)
    if not tokens:
        return 0, 0, 0.0, [], []
    hits, misses = [], []
    for token in tokens:
        target = normalize(token)
        if target and target in out:
            hits.append(token)
        else:
            misses.append(token)
    return len(hits), len(tokens), len(hits) / len(tokens), hits, misses


def split_checklist(text: str) -> list[str]:
    parts = re.split(r"\s*\d+[.、]\s*", str(text or ""))
    parts = [p.strip(" ;；") for p in parts if p.strip(" ;；")]
    if len(parts) <= 1:
        parts = [p.strip(" ;；") for p in re.split(r"[;；]", str(text or "")) if p.strip(" ;；")]
    return parts or [str(text or "")]


def make_result(doc: str, case_id: str, input_text: str, expected: str, output: str,
                status: str, score: float, elapsed: float, note: str) -> dict:
    return {
        "document": doc,
        "case_id": case_id,
        "input": short(input_text, 180),
        "expected": short(expected, 180),
        "actual": short(output, 220),
        "status": status,
        "score": round(float(score), 2),
        "elapsed_sec": round(float(elapsed), 2),
        "note": short(note, 220),
    }


class Runner:
    def __init__(self, include_online: bool):
        self.include_online = include_online
        self.results = []
        self._qa = None
        self._risk = None
        self._judge = None
        self._doc = None
        self._law_db = None
        self._case_db = None

    def add(self, result: dict):
        self.results.append(result)
        print(f"{result['document']} {result['case_id']} {result['status']} {result['score']} {result['elapsed_sec']}s", flush=True)

    def qa(self):
        if self._qa is None:
            from legal_ai_agent.agents.qa_agent import QAAgent
            self._qa = QAAgent()
        return self._qa

    def risk(self):
        if self._risk is None:
            from legal_ai_agent.agents.risk_agent import RiskAgent
            self._risk = RiskAgent()
        return self._risk

    def judge(self):
        if self._judge is None:
            from legal_ai_agent.agents.judge_agent import JudgeAgent
            self._judge = JudgeAgent()
        return self._judge

    def doc(self):
        if self._doc is None:
            from legal_ai_agent.agents.doc_agent import DocAgent
            self._doc = DocAgent()
        return self._doc

    def init_rag(self):
        if self._law_db is None or self._case_db is None:
            from legal_ai_agent.rag.vector_store import load_vector_store
            from legal_ai_agent.tools.labor_tools import init_tools_db
            self._law_db = load_vector_store("labor_law")
            self._case_db = load_vector_store("labor_cases")
            init_tools_db(self._law_db, self._case_db)

    def run_calculation(self):
        from legal_ai_agent.tools.calculator import calculate_from_query
        rows = rows_as_dicts(extract_tables(DOCS["calculation"])[0])
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入（工龄 / 月薪 / 场景）"]
            expected = row["预期输出 / 判定标准"]
            start = time.perf_counter()
            try:
                output = calculate_from_query(input_text)
                if output is None:
                    output = "NO_DETERMINISTIC_RESULT"
                elapsed = time.perf_counter() - start
                amounts = extract_expected_amounts(expected)
                amount_hit = bool(amounts) and any(a in output.replace(",", "") for a in amounts)
                hits, total, ratio, _, misses = token_hits(output, expected)
                score = 1.0 if amount_hit else ratio
                status = "PASS" if (amount_hit or ratio >= 0.55) else "FAIL"
                note = "amount hit" if amount_hit else f"token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, score, note = "ERROR", 0.0, str(exc)
            self.add(make_result("赔偿计算引擎测试及统计", case_id, input_text, expected, output, status, score, elapsed, note))

    def run_rag(self):
        from legal_ai_agent.rag.vector_store import retrieve_docs
        rows = rows_as_dicts(extract_tables(DOCS["rag"])[0])
        self.init_rag()
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入问题"]
            expected = row["期望召回（Top-3 内必须包含）"]
            start = time.perf_counter()
            try:
                law_output = retrieve_docs(self._law_db, input_text, k=3)
                case_output = retrieve_docs(self._case_db, input_text, k=3)
                output = f"[law]\n{law_output}\n\n[case]\n{case_output}"
                elapsed = time.perf_counter() - start
                hits, total, ratio, _, misses = token_hits(output, expected)
                status = "PASS" if ratio >= 0.25 or hits >= 2 else "FAIL"
                score = ratio
                note = f"expected token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, score, note = "ERROR", 0.0, str(exc)
            self.add(make_result("RAG检索测试用例（30组）", case_id, input_text, expected, output, status, score, elapsed, note))

    def run_memory(self):
        rows = rows_as_dicts(extract_tables(DOCS["memory"])[0])
        agent = self.qa()
        for row in rows:
            case_id = row["用例 ID"]
            group = "-".join(case_id.split("-")[:2])
            input_text = row["输入内容"]
            expected = row["预期记忆内容"]
            start = time.perf_counter()
            try:
                output = agent.run(input_text, session_id=f"eval_{group}")
                profile = agent.case_profiles.get(f"eval_{group}")
                combined = f"{json.dumps(profile, ensure_ascii=False)}\n{output}"
                elapsed = time.perf_counter() - start
                hits, total, ratio, _, misses = token_hits(combined, expected)
                status = "PASS" if ratio >= 0.45 else "FAIL"
                note = f"profile={profile}; token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, ratio, note = "ERROR", 0.0, str(exc)
            self.add(make_result("四、多轮记忆测试（MemorySaver）", case_id, input_text, expected, output, status, ratio, elapsed, note))

    def run_qa_cases(self):
        rows = rows_as_dicts(extract_tables(DOCS["qa"])[1])
        agent = self.qa()
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入"]
            expected = row["预期输出 / 判定标准"]
            start = time.perf_counter()
            try:
                output = agent.run(input_text, session_id=f"eval_qa_{case_id}")
                elapsed = time.perf_counter() - start
                hits, total, ratio, _, misses = token_hits(output, expected)
                status = "PASS" if ratio >= 0.35 or hits >= 3 else "FAIL"
                note = f"token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, ratio, note = "ERROR", 0.0, str(exc)
            self.add(make_result("劳动法智能问答系统测试用例集", case_id, input_text, expected, output, status, ratio, elapsed, note))

    def run_risk(self):
        rows = rows_as_dicts(extract_tables(DOCS["risk"])[0])
        agent = self.risk()
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入内容"]
            expected = row["预期风险等级"] + "；" + row["预期输出要点（法律依据 + 后果 + 建议）"]
            start = time.perf_counter()
            try:
                output = agent.run(input_text)
                elapsed = time.perf_counter() - start
                level_hit = row["预期风险等级"] in output
                hits, total, ratio, _, misses = token_hits(output, expected)
                score = (0.35 if level_hit else 0.0) + min(ratio, 1.0) * 0.65
                status = "PASS" if level_hit and ratio >= 0.35 else "FAIL"
                note = f"level_hit={level_hit}; token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, score, note = "ERROR", 0.0, str(exc)
            self.add(make_result("五、风险评估测试（RiskAgent）", case_id, input_text, expected, output, status, score, elapsed, note))

    def run_judge(self):
        rows = rows_as_dicts(extract_tables(DOCS["judge"])[0])
        agent = self.judge()
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入案情（用户陈述）"]
            expected = row["预判期望（核心维度）"]
            start = time.perf_counter()
            try:
                output = agent.run(input_text)
                elapsed = time.perf_counter() - start
                hits, total, ratio, _, misses = token_hits(output, expected)
                percent_score = self._judge_percent_score(output, expected)
                score_10 = round(min(10.0, ratio * 8 + percent_score * 2), 1)
                status = "PASS" if score_10 >= 7 else "FAIL"
                note = f"10-point score={score_10}; token hits {hits}/{total}; percent_score={percent_score}; missing: {', '.join(misses[:5])}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, score_10, note = "ERROR", 0.0, str(exc)
            self.add(make_result("六、案件预判测试（JudgeAgent）", case_id, input_text, expected, output, status, score_10, elapsed, note))

    def _judge_percent_score(self, output: str, expected: str) -> float:
        exp_nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*%", expected)]
        out_nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*%", output)]
        if len(exp_nums) >= 2:
            mid = (exp_nums[0] + exp_nums[1]) / 2
        elif exp_nums:
            mid = exp_nums[0]
        else:
            return 0.0
        if not out_nums:
            return 0.0
        diff = min(abs(n - mid) for n in out_nums)
        if diff <= 10:
            return 1.0
        if diff <= 20:
            return 0.5
        return 0.0

    def run_doc_agent(self):
        rows = rows_as_dicts(extract_tables(DOCS["doc"])[0])
        agent = self.doc()
        for row in rows:
            case_id = row["用例 ID"]
            input_text = row["输入需求（用户陈述）"]
            expected = row["检查清单（核心判定项）"]
            start = time.perf_counter()
            try:
                output = agent.run(input_text)
                elapsed = time.perf_counter() - start
                checklist = split_checklist(expected)
                item_scores = []
                for item in checklist:
                    hits, total, ratio, _, _ = token_hits(output, item)
                    item_scores.append(1.0 if ratio >= 0.35 or hits >= 2 else 0.0)
                score = sum(item_scores) / len(item_scores) if item_scores else 0.0
                if score >= 0.9:
                    status = "PASS"
                    submit = "可直接提交"
                elif score >= 0.7:
                    status = "PARTIAL"
                    submit = "需轻微修改"
                else:
                    status = "FAIL"
                    submit = "不可直接提交"
                note = f"{submit}; checklist pass {sum(item_scores):.0f}/{len(item_scores)}"
            except Exception as exc:
                elapsed = time.perf_counter() - start
                output = f"ERROR: {exc}"
                status, score, note = "ERROR", 0.0, str(exc)
            self.add(make_result("七、文书生成测试（DocAgent）", case_id, input_text, expected, output, status, score, elapsed, note))

    def run_comparison(self):
        tables = extract_tables(DOCS["comparison"])
        groups = [
            ("问答类", tables[0], "问题 ID", "问题内容", "核心考点", self.qa),
            ("计算类", tables[1], "问题 ID", "问题内容", "正确答案要点", self.qa),
            ("预判类", tables[2], "问题 ID", "案件描述（用户陈述）", "预判核心要求", self.judge),
            ("文书类", tables[3], "问题 ID", "用户需求", "文书生成核心要求", self.doc),
        ]
        for group_name, table, id_key, input_key, expected_key, agent_factory in groups:
            rows = rows_as_dicts(table)
            agent = agent_factory()
            for row in rows:
                case_id = row[id_key]
                input_text = row[input_key]
                expected = row[expected_key]
                start = time.perf_counter()
                try:
                    output = agent.run(input_text, session_id=f"eval_comp_{case_id}") if group_name in {"问答类", "计算类"} else agent.run(input_text)
                    elapsed = time.perf_counter() - start
                    hits, total, ratio, _, misses = token_hits(output, expected)
                    status = "PASS" if ratio >= 0.35 or hits >= 2 else "FAIL"
                    score = ratio
                    note = f"{group_name}; token hits {hits}/{total}; missing: {', '.join(misses[:5])}"
                except Exception as exc:
                    elapsed = time.perf_counter() - start
                    output = f"ERROR: {exc}"
                    status, score, note = "ERROR", 0.0, f"{group_name}; {exc}"
                self.add(make_result("九、对比实验测试（核心验证模块）", case_id, input_text, expected, output, status, score, elapsed, note))

    def run(self, modules: list[str]):
        if "calculation" in modules:
            self.run_calculation()
        if "rag" in modules:
            self.run_rag()
        if self.include_online:
            if "memory" in modules:
                self.run_memory()
            if "risk" in modules:
                self.run_risk()
            if "judge" in modules:
                self.run_judge()
            if "doc" in modules:
                self.run_doc_agent()
            if "qa" in modules:
                self.run_qa_cases()
            if "comparison" in modules:
                self.run_comparison()

    def write_outputs(self):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = OUT_DIR / f"docx_evaluation_results_{timestamp}.json"
        csv_path = OUT_DIR / f"docx_evaluation_results_{timestamp}.csv"
        md_path = OUT_DIR / f"docx_evaluation_results_{timestamp}.md"
        json_path.write_text(json.dumps(self.results, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(self.results[0].keys()) if self.results else [])
            writer.writeheader()
            writer.writerows(self.results)
        md_path.write_text(self.render_markdown(), encoding="utf-8")
        print(json.dumps({"json": str(json_path), "csv": str(csv_path), "md": str(md_path)}, ensure_ascii=False), flush=True)
        return json_path, csv_path, md_path

    def render_markdown(self) -> str:
        lines = [
            "# 八份 Docx 功能测试结果",
            "",
            f"- 测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 测试对象：{ROOT}",
            f"- 用例总数：{len(self.results)}",
            "",
            "## 汇总",
            "",
            "| 文档 | 用例数 | 通过 | 部分通过 | 失败 | 错误 | 通过率 | 平均耗时(s) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for doc, rows in self.grouped().items():
            total = len(rows)
            passed = sum(1 for r in rows if r["status"] == "PASS")
            partial = sum(1 for r in rows if r["status"] == "PARTIAL")
            failed = sum(1 for r in rows if r["status"] == "FAIL")
            errors = sum(1 for r in rows if r["status"] == "ERROR")
            pass_rate = (passed + partial * 0.5) / total * 100 if total else 0
            avg = statistics.mean(r["elapsed_sec"] for r in rows) if rows else 0
            lines.append(f"| {doc} | {total} | {passed} | {partial} | {failed} | {errors} | {pass_rate:.1f}% | {avg:.2f} |")
        lines.extend(["", "## 明细", ""])
        for doc, rows in self.grouped().items():
            lines.extend([f"### {doc}", "", "| 用例ID | 判定/得分 | 耗时(s) | 输入摘要 | 期望要点 | 实际输出摘要 | 备注 |", "|---|---:|---:|---|---|---|---|"])
            for r in rows:
                lines.append(
                    f"| {r['case_id']} | {r['status']} / {r['score']} | {r['elapsed_sec']} | "
                    f"{self.escape(r['input'])} | {self.escape(r['expected'])} | {self.escape(r['actual'])} | {self.escape(r['note'])} |"
                )
            lines.append("")
        return "\n".join(lines)

    def grouped(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for result in self.results:
            grouped.setdefault(result["document"], []).append(result)
        return grouped

    @staticmethod
    def escape(text: str) -> str:
        return str(text or "").replace("|", "\\|").replace("\n", " ")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--modules", default="calculation,rag,memory,risk,judge,doc,qa,comparison")
    return parser.parse_args()


def main():
    args = parse_args()
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    runner = Runner(include_online=not args.offline_only)
    runner.run(modules)
    runner.write_outputs()


if __name__ == "__main__":
    main()
