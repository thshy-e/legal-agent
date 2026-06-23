import csv
import json
import statistics
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent / "current_results"

SOURCE_FILES = [
    "docx_evaluation_results_20260606_034108.json",  # calculation + sandbox-blocked rag
    "docx_evaluation_results_20260606_034257.json",  # successful online rag
    "docx_evaluation_results_20260606_040600.json",  # memory/risk/judge/doc
    "docx_evaluation_results_20260606_040754.json",  # qa
    "docx_evaluation_results_20260606_041456.json",  # comparison
]

DOCUMENT_ORDER = [
    "劳动法智能问答系统测试用例集",
    "四、多轮记忆测试（MemorySaver）",
    "RAG检索测试用例（30组）",
    "五、风险评估测试（RiskAgent）",
    "七、文书生成测试（DocAgent）",
    "九、对比实验测试（核心验证模块）",
    "六、案件预判测试（JudgeAgent）",
    "赔偿计算引擎测试及统计",
]


def load_final_results() -> list[dict]:
    all_rows = []
    for name in SOURCE_FILES:
        rows = json.loads((BASE / name).read_text(encoding="utf-8"))
        if name == "docx_evaluation_results_20260606_034108.json":
            rows = [r for r in rows if r["document"] == "赔偿计算引擎测试及统计"]
        all_rows.extend(rows)

    order = {name: idx for idx, name in enumerate(DOCUMENT_ORDER)}
    all_rows.sort(key=lambda r: (order.get(r["document"], 99), r["case_id"]))
    return all_rows


def escape(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def grouped(rows: list[dict]) -> dict[str, list[dict]]:
    data = {}
    for row in rows:
        data.setdefault(row["document"], []).append(row)
    return data


def render_markdown(rows: list[dict]) -> str:
    lines = [
        "# 八份 Docx 功能测试结果（当前实测）",
        "",
        f"- 测试时间：2026-06-06 03:41-04:14（Asia/Shanghai）",
        "- 测试对象：D:\\BaiduNetdiskDownload\\legal_ai_agent",
        "- 执行方式：真实调用当前项目 Agent / RAG / 赔偿计算引擎；RAG 与 Agent 在线调用 DashScope。",
        f"- 用例总数：{len(rows)}",
        "",
        "## 总览",
        "",
        "| 文档 | 用例数 | 通过 | 部分通过 | 失败 | 错误 | 通过率 | 平均耗时(s) | 主要问题 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for doc in DOCUMENT_ORDER:
        doc_rows = grouped(rows).get(doc, [])
        total = len(doc_rows)
        passed = sum(1 for r in doc_rows if r["status"] == "PASS")
        partial = sum(1 for r in doc_rows if r["status"] == "PARTIAL")
        failed = sum(1 for r in doc_rows if r["status"] == "FAIL")
        errors = sum(1 for r in doc_rows if r["status"] == "ERROR")
        pass_rate = (passed + partial * 0.5) / total * 100 if total else 0
        avg = statistics.mean(r["elapsed_sec"] for r in doc_rows) if doc_rows else 0
        problem = summarize_problem(doc, doc_rows)
        lines.append(f"| {doc} | {total} | {passed} | {partial} | {failed} | {errors} | {pass_rate:.1f}% | {avg:.2f} | {escape(problem)} |")

    lines.extend(["", "## 明细表", ""])
    for doc in DOCUMENT_ORDER:
        doc_rows = grouped(rows).get(doc, [])
        lines.extend([
            f"### {doc}",
            "",
            "| 用例ID | 判定/得分 | 耗时(s) | 输入摘要 | 期望要点 | 实际输出摘要 | 备注 |",
            "|---|---:|---:|---|---|---|---|",
        ])
        for r in doc_rows:
            lines.append(
                f"| {r['case_id']} | {r['status']} / {r['score']} | {r['elapsed_sec']} | "
                f"{escape(r['input'])} | {escape(r['expected'])} | {escape(r['actual'])} | {escape(r['note'])} |"
            )
        lines.append("")
    return "\n".join(lines)


def summarize_problem(doc: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    if doc == "赔偿计算引擎测试及统计":
        return "20 条均未触发 calculate_from_query 的确定性计算，实际输出 NO_DETERMINISTIC_RESULT。"
    if doc == "四、多轮记忆测试（MemorySaver）":
        return "结构化 case_profile 仅识别少量中文事实，跨轮提取和动态更新大量未命中。"
    if doc == "七、文书生成测试（DocAgent）":
        return "部分文书缺少检查清单中的请求金额、法律依据或格式要素。"
    if doc == "九、对比实验测试（核心验证模块）":
        return "问答/计算较好，预判与文书类关键词覆盖不足。"
    failed = [r for r in rows if r["status"] in {"FAIL", "ERROR"}]
    if not failed:
        return "未发现失败项。"
    return "；".join(f"{r['case_id']} {r['status']}" for r in failed[:5])


def main():
    rows = load_final_results()
    out_json = BASE / "final_docx_evaluation_results.json"
    out_csv = BASE / "final_docx_evaluation_results.csv"
    out_md = BASE / "final_docx_evaluation_results.md"

    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    out_md.write_text(render_markdown(rows), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "csv": str(out_csv), "md": str(out_md)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
