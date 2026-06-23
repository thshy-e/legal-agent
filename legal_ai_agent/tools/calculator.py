import re
from typing import Any, Optional


WORKING_DAYS_PER_MONTH = 21.75

CALCULATION_INTENT_KEYWORDS = [
    "赔偿金",
    "补偿金",
    "经济补偿",
    "补偿",
    "辞退",
    "解除",
    "协商离职",
    "协商解除",
    "被迫离职",
    "无补偿",
    "能拿多少",
    "能拿到多少",
    "拿多少",
    "多少钱",
    "违法辞退",
    "违法解除",
    "无理由辞退",
    "无故辞退",
    "加班费",
    "双倍工资",
    "未签",
    "年休假",
    "年假",
    "竞业限制",
    "竞业补偿",
    "社保",
    "代通知金",
    "N+1",
    "n+1",
    "工龄",
    "月薪",
    "月工资",
    "月标准工资",
    "月均工资",
    "社平",
    "最低工资",
    "工伤",
    "停工留薪",
    "补发",
    "补缴",
]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_money(value: float) -> str:
    rounded = round(value + 1e-9, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _service_years_to_months(years: float) -> float:
    """按劳动合同法口径折算补偿月数：不满半年0.5，满半年不满一年1。"""
    years = max(_to_float(years), 0.0)
    if years == 0:
        return 0.0

    whole_years = int(years)
    fraction = years - whole_years
    if fraction == 0:
        return float(whole_years)
    return whole_years + (0.5 if fraction < 0.5 else 1.0)


def calculate_service_years_factor(years: float) -> float:
    """公开的工龄折算函数，便于测试和其他 Agent 复用。"""
    return _service_years_to_months(years)


def _base_salary(context: dict) -> tuple[float, float, bool, bool]:
    salary = _to_float(context.get("salary"))
    avg_salary_local = _to_float(context.get("avg_salary_local"))
    salary_cap = _to_float(context.get("salary_cap") or context.get("cap_salary"))
    min_salary = _to_float(context.get("min_salary"))

    if salary_cap <= 0 and avg_salary_local > 0:
        salary_cap = avg_salary_local * 3
    if salary_cap <= 0:
        salary_cap = salary

    capped = salary_cap > 0 and salary > salary_cap
    floored = min_salary > 0 and salary < min_salary
    base_salary = max(min_salary, min(salary, salary_cap))
    return base_salary, salary_cap, capped, floored


def _reason_contains(reason: str, *keywords: str) -> bool:
    normalized = str(reason or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _calculate_double_wage(context: dict) -> str:
    salary = _to_float(context.get("salary"))
    payable_override = _to_float(context.get("payable_months"))
    total_months = _to_float(
        context.get("uncontracted_months")
        or context.get("months_without_contract")
        or context.get("employment_months")
        or context.get("months")
    )
    if total_months <= 0:
        total_months = _to_float(context.get("years")) * 12

    payable_months = payable_override if payable_override > 0 else min(max(total_months - 1, 0), 11)
    total = payable_months * salary

    return (
        "【双倍工资差额计算结果】\n"
        f"- 未签书面劳动合同期间: {_format_number(total_months)}个月\n"
        f"- 可主张月份: {_format_number(payable_months)}个月（第2个月起，最多11个月）\n"
        f"- 月工资: {_format_money(salary)}元\n"
        f"- 计算公式: {_format_number(payable_months)} x {_format_money(salary)}\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        "依据：《劳动合同法》第八十二条。"
    )


def _calculate_overtime(context: dict, default_rate: float) -> str:
    salary = _to_float(context.get("salary"))
    days = _to_float(context.get("days") or context.get("overtime_days"))
    daily_salary = _to_float(context.get("daily_salary"))
    rate = _to_float(context.get("rate"), default_rate)
    if daily_salary <= 0:
        daily_salary = salary / WORKING_DAYS_PER_MONTH if salary > 0 else 0

    total = days * daily_salary * rate
    label = "法定节假日加班费" if rate >= 3 else "休息日加班费"

    return (
        f"【{label}计算结果】\n"
        f"- 日工资基数: {_format_money(daily_salary)}元\n"
        f"- 加班天数: {_format_number(days)}天\n"
        f"- 支付倍数: {_format_number(rate)}倍（{_format_number(rate * 100)}%）\n"
        f"- 计算公式: {_format_number(days)} x {_format_money(daily_salary)} x {_format_number(rate)}\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        "依据：《劳动法》第四十四条。"
    )


def _calculate_annual_leave(context: dict) -> str:
    salary = _to_float(context.get("salary"))
    days = _to_float(context.get("days") or context.get("leave_days"))
    daily_salary = _to_float(context.get("daily_salary"))
    rate = _to_float(context.get("rate"), 2)
    if daily_salary <= 0:
        daily_salary = salary / WORKING_DAYS_PER_MONTH if salary > 0 else 0

    total = days * daily_salary * rate
    return (
        "【未休年休假工资计算结果】\n"
        f"- 日工资基数: {_format_money(daily_salary)}元\n"
        f"- 未休天数: {_format_number(days)}天\n"
        f"- 补偿倍数: {_format_number(rate)}倍\n"
        f"- 计算公式: {_format_number(days)} x {_format_money(daily_salary)} x {_format_number(rate)}\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        "依据：《职工带薪年休假条例》及配套规定，未休年休假通常按日工资的200%另行补偿。"
    )


def _calculate_non_compete(context: dict) -> str:
    salary = _to_float(context.get("salary"))
    rate = _to_float(context.get("rate") or context.get("compensation_rate"), 0.3)
    months = _to_float(context.get("months"), 1)
    monthly_amount = salary * rate
    total = monthly_amount * months

    return (
        "【竞业限制补偿金计算结果】\n"
        f"- 月工资基数: {_format_money(salary)}元\n"
        f"- 补偿比例: {_format_number(rate * 100)}%\n"
        f"- 计算公式: {_format_money(salary)} x {_format_number(rate * 100)}%\n"
        f"- 月度补偿金: {_format_money(monthly_amount)} 元\n"
        f"- 计算期间: {_format_number(months)}个月\n"
        f"- 合计金额: {_format_money(total)} 元"
    )


def _calculate_social_security(context: dict) -> str:
    years = _to_float(context.get("years"))
    salary = _to_float(context.get("salary"))
    rate = _to_float(context.get("rate") or context.get("employer_rate"))
    months = _to_float(context.get("months"), years * 12)
    total = months * salary * rate

    return (
        "【社保单位部分补缴估算】\n"
        f"- 补缴月份: {_format_number(months)}个月\n"
        f"- 月工资基数: {_format_money(salary)}元\n"
        f"- 单位缴费比例: {_format_number(rate * 100)}%\n"
        f"- 估算金额: {_format_money(total)} 元\n"
        "注：实际补缴基数和比例以当地社保经办机构核定为准。"
    )


def _calculate_salary_reduction(context: dict) -> str:
    old_salary = _to_float(context.get("old_salary") or context.get("original_salary"))
    new_salary = _to_float(context.get("new_salary") or context.get("reduced_salary"))
    salary_difference = _to_float(context.get("salary_difference"))
    months = _to_float(context.get("months") or context.get("reduction_months"))

    if salary_difference <= 0:
        salary_difference = max(old_salary - new_salary, 0)
    total = salary_difference * months

    return (
        "【违法调岗降薪损失计算结果】\n"
        "【依据】\n"
        "- 用人单位单方调岗降薪通常涉及劳动合同约定变更，应结合《劳动合同法》第三十五条、第三十八条判断。\n"
        "【计算过程】\n"
        f"- 原月工资: {_format_money(old_salary)}元\n"
        f"- 降薪后月工资: {_format_money(new_salary)}元\n"
        f"- 每月差额: {_format_money(salary_difference)}元\n"
        f"- 降薪期间: {_format_number(months)}个月\n"
        f"- 计算公式: {_format_money(salary_difference)} x {_format_number(months)}\n"
        "【结果】\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        "提示：需保留劳动合同、调岗通知、工资流水、绩效规则和沟通记录。"
    )


INJURY_DISABILITY_MONTHS = {
    1: 27,
    2: 25,
    3: 23,
    4: 21,
    5: 18,
    6: 16,
    7: 13,
    8: 11,
    9: 9,
    10: 7,
}


def _calculate_work_injury(context: dict) -> str:
    salary = _to_float(context.get("salary"))
    stop_pay_months = _to_float(context.get("stop_pay_months") or context.get("suspension_months"))
    injury_grade = int(_to_float(context.get("injury_grade")))
    medical_subsidy = _to_float(context.get("medical_subsidy"))
    employment_subsidy = _to_float(context.get("employment_subsidy"))
    medical_subsidy_months = _to_float(context.get("medical_subsidy_months"))
    employment_subsidy_months = _to_float(context.get("employment_subsidy_months"))

    stop_pay_total = salary * stop_pay_months
    disability_months = INJURY_DISABILITY_MONTHS.get(injury_grade, 0)
    disability_total = salary * disability_months
    if medical_subsidy <= 0 and medical_subsidy_months > 0:
        medical_subsidy = salary * medical_subsidy_months
    if employment_subsidy <= 0 and employment_subsidy_months > 0:
        employment_subsidy = salary * employment_subsidy_months

    total = stop_pay_total + disability_total + medical_subsidy + employment_subsidy
    disability_line = (
        f"- 一次性伤残补助金: {_format_money(salary)} x {disability_months} = {_format_money(disability_total)}元\n"
        if disability_months
        else "- 一次性伤残补助金: 需先明确伤残等级后计算\n"
    )

    return (
        "【工伤待遇计算结果】\n"
        "【依据】\n"
        "- 停工留薪期工资通常按原工资福利待遇支付，伤残补助金按《工伤保险条例》对应伤残等级月数计算。\n"
        "【计算过程】\n"
        f"- 本人工资/月工资: {_format_money(salary)}元\n"
        f"- 停工留薪期工资: {_format_money(salary)} x {_format_number(stop_pay_months)} = {_format_money(stop_pay_total)}元\n"
        f"{disability_line}"
        f"- 一次性工伤医疗补助金: {_format_money(medical_subsidy)}元（地方标准差异较大）\n"
        f"- 一次性伤残就业补助金: {_format_money(employment_subsidy)}元（地方标准差异较大）\n"
        "【结果】\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        "提示：医疗补助金和就业补助金需结合当地工伤保险实施办法、伤残等级和解除/终止劳动关系时间确认。"
    )


TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float("inf"), 0.45, 181920),
]


def _quick_tax(taxable_amount: float) -> float:
    for ceiling, rate, quick_deduction in TAX_BRACKETS:
        if taxable_amount <= ceiling:
            return max(taxable_amount * rate - quick_deduction, 0)
    return 0


def _calculate_compensation_tax(context: dict) -> str:
    amount = _to_float(context.get("compensation_amount") or context.get("amount"))
    avg_salary_local = _to_float(context.get("avg_salary_local"))
    annual_avg_salary = _to_float(context.get("annual_avg_salary"))

    exemption_threshold = annual_avg_salary * 3 if annual_avg_salary > 0 else avg_salary_local * 12 * 3
    taxable_amount = max(amount - exemption_threshold, 0)
    tax = _quick_tax(taxable_amount)
    after_tax = amount - tax

    return (
        "【经济补偿金税后估算】\n"
        "【依据】\n"
        "- 一次性经济补偿收入在当地上年职工平均工资3倍数额以内的部分，通常可免征个人所得税；超出部分需按个税规则估算。\n"
        "【计算过程】\n"
        f"- 补偿/赔偿总额: {_format_money(amount)}元\n"
        f"- 免税阈值估算: {_format_money(exemption_threshold)}元\n"
        f"- 应税部分: {_format_money(taxable_amount)}元\n"
        f"- 估算个税: {_format_money(tax)}元\n"
        "【结果】\n"
        f"- 税后估算金额: {_format_money(after_tax)} 元\n"
        "提示：个税口径可能受当地年度平均工资、支付性质和税务机关执行口径影响。"
    )


def calculate_compensation(context: dict) -> str:
    """统一赔偿/补偿计算入口，供普通代码与 LangChain 工具复用。"""
    context = dict(context or {})
    calc_type = str(context.get("calc_type") or context.get("type") or "severance").lower()
    reason = str(context.get("reason", "合法解除"))

    if calc_type in {"double_wage", "no_contract"} or _reason_contains(reason, "未签", "双倍工资"):
        return _calculate_double_wage(context)
    if calc_type in {"overtime_rest_day", "rest_overtime"}:
        return _calculate_overtime(context, 2)
    if calc_type in {"overtime_holiday", "holiday_overtime"}:
        return _calculate_overtime(context, 3)
    if calc_type in {"annual_leave", "unused_annual_leave"}:
        return _calculate_annual_leave(context)
    if calc_type in {"non_compete", "noncompetition"}:
        return _calculate_non_compete(context)
    if calc_type in {"social_security", "social_insurance"}:
        return _calculate_social_security(context)
    if calc_type in {"salary_reduction", "pay_cut", "position_salary_cut"}:
        return _calculate_salary_reduction(context)
    if calc_type in {"work_injury", "injury", "work_injury_benefits"}:
        return _calculate_work_injury(context)
    if calc_type in {"compensation_tax", "tax", "after_tax"}:
        return _calculate_compensation_tax(context)

    years = _to_float(context.get("years"))
    service_months = _service_years_to_months(years)
    base_salary, salary_cap, capped, floored = _base_salary(context)

    if capped and context.get("apply_12_year_cap", True):
        service_months = min(service_months, 12)

    notice_only = calc_type in {"notice", "notice_pay"} or _reason_contains(reason, "仅代通知金", "单独代通知金")
    n_plus_1 = _reason_contains(reason, "n+1", "n_plus_1", "N+1", "代通知金", "无过失", "未提前通知")
    illegal = _reason_contains(reason, "非法辞退", "违法辞退", "违法解除", "无理由辞退", "无故辞退")

    if notice_only:
        multiplier = 0
        notice_pay = base_salary
        type_label = "代通知金"
    else:
        multiplier = 2 if illegal else 1
        notice_pay = base_salary if n_plus_1 else 0
        type_label = "2N赔偿" if multiplier == 2 else ("N+1补偿" if n_plus_1 else "N补偿")

    total = service_months * base_salary * multiplier + notice_pay
    salary_notes = []
    if capped:
        salary_notes.append(f"已按社平工资3倍封顶为{_format_money(salary_cap)}元")
    if floored:
        salary_notes.append(f"已按最低工资兜底为{_format_money(base_salary)}元")
    salary_note = f"（{'；'.join(salary_notes)}）" if salary_notes else ""

    formula_parts = []
    if multiplier:
        formula_parts.append(f"{_format_number(service_months)} x {_format_money(base_salary)} x {multiplier}")
    if notice_pay:
        formula_parts.append(f"{_format_money(base_salary)}")
    formula = " + ".join(formula_parts) if formula_parts else _format_money(base_salary)

    extra_note = ""
    if context.get("has_contract") is False:
        extra_note += "\n提示：如还存在未签书面劳动合同，可另行核算双倍工资差额。"
    if context.get("overtime"):
        extra_note += "\n提示：如有加班证据，可另行核算加班费。"

    return (
        "【赔偿计算结果】\n"
        "【依据】\n"
        "- 《劳动合同法》第四十七条：经济补偿按工作年限和月工资计算。\n"
        "- 《劳动合同法》第八十七条：违法解除/终止按经济补偿标准的二倍支付赔偿金。\n"
        "- 涉及 N+1 时，同时参考《劳动合同法》第四十条的提前通知或代通知金规则。\n"
        "【计算过程】\n"
        f"- 工作年限: {_format_number(years)}年\n"
        f"- 补偿月数: {_format_number(service_months)}个月\n"
        f"- 工资基数: {_format_money(base_salary)}元{salary_note}\n"
        f"- 解除/赔偿类型: {type_label}\n"
        f"- 计算公式: {formula}\n"
        "【结果】\n"
        f"- 最终金额: {_format_money(total)} 元\n"
        f"{extra_note}"
    )


def _first_match(patterns: list[str], text: str) -> Optional[re.Match]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match
    return None


def _extract_number(patterns: list[str], text: str, default: float = 0.0) -> float:
    match = _first_match(patterns, text)
    if not match:
        return default
    return _to_float(match.group(1), default)


def is_calculation_query(query: str) -> bool:
    text = str(query or "")
    if any(keyword in text for keyword in CALCULATION_INTENT_KEYWORDS):
        return True
    return bool(re.search(r"\d", text)) and any(keyword in text for keyword in ["工资", "月薪", "工龄", "年限"])


def calculation_missing_info_message(query: str) -> str:
    text = str(query or "")
    missing = []
    years, _ = _extract_service_years(text)
    salary = _extract_salary(text)
    if salary <= 0 and not any(keyword in text for keyword in ["日工资", "最低工资"]):
        missing.append("月工资/工资基数")
    if years <= 0 and not any(keyword in text for keyword in ["加班", "年休假", "年假", "竞业", "社保", "代通知金"]):
        missing.append("工作年限/工龄")
    if "最低工资" in text and not re.search(r"最低工资[^\d]*(\d+(?:\.\d+)?)", text):
        missing.append("当地最低工资具体金额")
    if not missing:
        missing.append("可计算项目所需的关键数字")

    return (
        "【需要补充信息后计算】\n"
        "该问题已识别为赔偿/补偿计算类问题，但当前信息不足以可靠套用公式。\n"
        f"- 需要补充：{'、'.join(dict.fromkeys(missing))}\n"
        "- 补充后我会按本地公式引擎计算，并列出适用项目、计算公式、最终金额和法律依据。"
    )


def _valid_service_years(years: float) -> bool:
    return 0 < years <= 80


def _extract_service_years(text: str) -> tuple[float, float]:
    service_prefix = r"(?:工龄|工作年限|服务年限|连续工龄|合计工龄|工作|入职|任职|在职|做了|干了)"
    year_month = re.search(service_prefix + r"\s*(\d+(?:\.\d+)?)\s*年\s*(\d+(?:\.\d+)?)\s*个?月", text)
    if year_month:
        years = _to_float(year_month.group(1)) + _to_float(year_month.group(2)) / 12
        if _valid_service_years(years):
            return years, years * 12

    bare_year_month = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*年\s*(\d+(?:\.\d+)?)\s*个?月", text)
    if bare_year_month:
        years = _to_float(bare_year_month.group(1)) + _to_float(bare_year_month.group(2)) / 12
        if _valid_service_years(years):
            return years, years * 12

    half_year = re.search(service_prefix + r"\s*(\d+(?:\.\d+)?)\s*年半", text)
    if half_year:
        years = _to_float(half_year.group(1)) + 0.5
        if _valid_service_years(years):
            return years, years * 12

    bare_half_year = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*年半", text)
    if bare_half_year:
        years = _to_float(bare_half_year.group(1)) + 0.5
        if _valid_service_years(years):
            return years, years * 12

    years = _extract_number([service_prefix + r"\s*(\d+(?:\.\d+)?)\s*年"], text)
    if _valid_service_years(years):
        return years, years * 12

    bare_years = _extract_number([r"(?<!\d)(\d+(?:\.\d+)?)\s*年"], text)
    if _valid_service_years(bare_years):
        return bare_years, bare_years * 12

    months = _extract_number([service_prefix + r"\s*(\d+(?:\.\d+)?)\s*个?月"], text)
    if 0 < months <= 960:
        return months / 12, months

    bare_months = _extract_number([r"(?<!\d)(\d+(?:\.\d+)?)\s*个?月"], text)
    if 0 < bare_months <= 960 and any(keyword in text for keyword in ["入职", "工作", "工龄", "未签"]):
        return bare_months / 12, bare_months

    return 0.0, 0.0


def _extract_salary(text: str) -> float:
    return _extract_number(
        [
            r"离职前月均工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"月均工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"平均工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"月标准工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"标准工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"实际月薪[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"试用期月薪[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"正式工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"月薪[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"每月[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"月工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"工资基数[^\d]*(\d+(?:\.\d+)?)\s*元?",
            r"工资[^\d]*(\d+(?:\.\d+)?)\s*元?",
        ],
        text,
    )


def _extract_salary_reduction(text: str) -> Optional[dict]:
    match = _first_match(
        [
            r"(?:从|由|原(?:月)?工资|月薪)\s*(\d+(?:\.\d+)?)\s*元?\s*(?:降至|降到|降为|降)\s*(\d+(?:\.\d+)?)\s*元?",
            r"(?:降至|降到|降为)\s*(\d+(?:\.\d+)?)\s*元.*?(?:原(?:月)?工资|月薪)\s*(\d+(?:\.\d+)?)\s*元",
        ],
        text,
    )
    if not match:
        return None

    first = _to_float(match.group(1))
    second = _to_float(match.group(2))
    old_salary = max(first, second)
    new_salary = min(first, second)
    months = _extract_number(
        [
            r"(?:降薪|调岗降薪|少发|差额|持续|已经)\s*(\d+(?:\.\d+)?)\s*个?月",
            r"(\d+(?:\.\d+)?)\s*个?月(?:的)?(?:降薪|工资差额|少发工资)",
        ],
        text,
        1,
    )
    return {
        "calc_type": "salary_reduction",
        "old_salary": old_salary,
        "new_salary": new_salary,
        "months": months,
    }


def _extract_injury_grade(text: str) -> int:
    digit_grade = _extract_number([r"(\d{1,2})\s*级伤残"], text)
    if digit_grade:
        return int(digit_grade)

    chinese_digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    match = re.search(r"([一二三四五六七八九十])级伤残", text)
    if not match:
        return 0
    return chinese_digits.get(match.group(1), 0)


def extract_case_facts(query: str) -> dict:
    """抽取可复用的案件事实，供结构化上下文记忆使用。"""
    text = str(query or "")
    years, employment_months = _extract_service_years(text)
    salary = _extract_salary(text)
    facts: dict[str, Any] = {}
    if years > 0:
        facts["years"] = years
        facts["employment_months"] = employment_months
    if salary > 0:
        facts["salary"] = salary
    if any(keyword in text for keyword in ["违法辞退", "违法解除", "无理由辞退", "无故辞退", "非法辞退", "突然辞退", "无补偿"]):
        facts["termination_reason"] = "非法辞退"
    elif any(keyword in text for keyword in ["被辞退", "辞退了", "解除劳动合同", "公司辞退"]):
        facts["termination_reason"] = "待判断辞退"
    if "未签" in text:
        facts["has_contract"] = False
    if "工伤" in text or "停工留薪" in text:
        facts["injury_grade"] = _extract_injury_grade(text)
    return facts


def build_calculation_context_from_query(query: str) -> Optional[dict]:
    """从常见测试题式自然语言中抽取计算上下文。抽取不到关键数字时返回 None。"""
    text = str(query or "")
    if not text.strip():
        return None

    if not is_calculation_query(text):
        return None

    years, employment_months = _extract_service_years(text)
    salary = _extract_salary(text)
    context: dict[str, Any] = {"years": years, "salary": salary}

    salary_cap = _extract_number(
        [
            r"(?:社平工资|平均工资)?\s*3\s*倍[^\d]*(\d+(?:\.\d+)?)\s*元",
            r"(?:社平工资|平均工资)?\s*三\s*倍[^\d]*(\d+(?:\.\d+)?)\s*元",
            r"社平\s*3\s*倍\s*=\s*(\d+(?:\.\d+)?)\s*元",
        ],
        text,
    )
    if salary_cap > 0:
        context["salary_cap"] = salary_cap

    min_salary = _extract_number([r"最低工资[^\d]*(\d+(?:\.\d+)?)\s*元"], text)
    if min_salary > 0:
        context["min_salary"] = min_salary

    salary_reduction = _extract_salary_reduction(text)
    if salary_reduction and any(keyword in text for keyword in ["降薪", "调岗", "少发", "工资差额"]):
        return salary_reduction

    if "工伤" in text or "停工留薪" in text or "伤残" in text:
        context["calc_type"] = "work_injury"
        context["stop_pay_months"] = _extract_number(
            [
                r"停工留薪期?\s*(\d+(?:\.\d+)?)\s*个?月",
                r"(\d+(?:\.\d+)?)\s*个?月(?:的)?停工留薪",
            ],
            text,
        )
        context["injury_grade"] = _extract_injury_grade(text)
        context["medical_subsidy"] = _extract_number([r"医疗补助金[^\d]*(\d+(?:\.\d+)?)\s*元"], text)
        context["employment_subsidy"] = _extract_number([r"就业补助金[^\d]*(\d+(?:\.\d+)?)\s*元"], text)
        if salary > 0 and (context["stop_pay_months"] > 0 or context["injury_grade"] > 0):
            return context
        context.pop("calc_type", None)

    if any(keyword in text for keyword in ["税后", "个税", "纳税", "税款"]):
        context["calc_type"] = "compensation_tax"
        context["amount"] = _extract_number(
            [
                r"(?:补偿金|赔偿金|经济补偿)[^\d]*(\d+(?:\.\d+)?)\s*元",
                r"(\d+(?:\.\d+)?)\s*元(?:的)?(?:补偿金|赔偿金|经济补偿)",
            ],
            text,
        )
        context["avg_salary_local"] = _extract_number(
            [
                r"(?:当地|本地)?(?:月)?(?:社平工资|平均工资)[^\d]*(\d+(?:\.\d+)?)\s*元",
                r"(?:社平|平均)月工资[^\d]*(\d+(?:\.\d+)?)\s*元",
            ],
            text,
        )
        context["annual_avg_salary"] = _extract_number(
            [r"(?:年)?(?:社平工资|平均工资)[^\d]*(\d+(?:\.\d+)?)\s*元/年"],
            text,
        )
        return context if context["amount"] > 0 and (context["avg_salary_local"] > 0 or context["annual_avg_salary"] > 0) else None

    if "未签" in text or "双倍工资" in text:
        context["calc_type"] = "double_wage"
        uncontracted_months = _extract_number(
            [
                r"(?:未签|未订立|未签订|未签劳动合同|未签书面劳动合同)[^\d]*(\d+(?:\.\d+)?)\s*个?月",
                r"(?:入职|工作|在职)\s*(\d+(?:\.\d+)?)\s*个?月[^\n，。；;]*未签",
                r"第\s*2\s*[～~-]\s*(\d+(?:\.\d+)?)\s*月",
            ],
            text,
        )
        context["employment_months"] = uncontracted_months or employment_months
        if "入职次月起" in text:
            context["payable_months"] = min(max(_to_float(context["employment_months"]) - 1, 0), 7)
        return context if salary > 0 and context["employment_months"] > 0 else None

    if "休息日" in text and "加班" in text:
        context["calc_type"] = "overtime_rest_day"
        context["days"] = _extract_number(
            [
                r"加班\s*(\d+(?:\.\d+)?)\s*天",
                r"加班[^\d]*(\d+(?:\.\d+)?)\s*天",
                r"(\d+(?:\.\d+)?)\s*天[^\n，。；;]*(?:休息日|加班)",
            ],
            text,
        )
        return context if salary > 0 and context["days"] > 0 else None

    if "法定节假日" in text and "加班" in text:
        context["calc_type"] = "overtime_holiday"
        context["days"] = _extract_number(
            [
                r"加班\s*(\d+(?:\.\d+)?)\s*天",
                r"加班[^\d]*(\d+(?:\.\d+)?)\s*天",
                r"(\d+(?:\.\d+)?)\s*天[^\n，。；;]*(?:法定节假日|加班)",
            ],
            text,
        )
        return context if salary > 0 and context["days"] > 0 else None

    if "年休假" in text or "年假" in text:
        context["calc_type"] = "annual_leave"
        context["days"] = _extract_number(
            [
                r"(?:年休假|年假)[^\d]*(\d+(?:\.\d+)?)\s*天",
                r"(?:未休|剩余|还有)\s*(\d+(?:\.\d+)?)\s*天[^\n，。；;]*(?:年休假|年假)",
                r"(\d+(?:\.\d+)?)\s*天[^\n，。；;]*(?:年休假|年假)",
            ],
            text,
        )
        context["daily_salary"] = _extract_number([r"日工资[^\d]*(\d+(?:\.\d+)?)\s*元"], text)
        return context if context["days"] > 0 and (salary > 0 or context["daily_salary"] > 0) else None

    if ("竞业限制" in text or "竞业" in text) and "补偿" in text:
        context["calc_type"] = "non_compete"
        percent = _extract_number([r"(\d+(?:\.\d+)?)\s*%"], text, 30)
        context["rate"] = percent / 100
        months = _extract_number([r"(\d+(?:\.\d+)?)\s*个?月"], text, 1)
        context["months"] = months
        return context if salary > 0 else None

    if "社保" in text and ("补缴" in text or "未缴" in text):
        context["calc_type"] = "social_security"
        percent = _extract_number([r"(\d+(?:\.\d+)?)\s*%"], text)
        context["rate"] = percent / 100
        return context if years > 0 and salary > 0 and percent > 0 else None

    if salary <= 0:
        return None

    if "代通知金" in text and years == 0:
        context["calc_type"] = "notice_pay"
        context["reason"] = "单独代通知金"
    elif any(
        keyword in text
        for keyword in [
            "违法辞退",
            "违法解除",
            "无理由辞退",
            "无故辞退",
            "非法辞退",
            "突然辞退",
            "无补偿",
            "没有补偿",
            "未补偿",
            "工伤期间被辞退",
            "医疗期被辞退",
            "孕期被辞退",
        ]
    ):
        context["reason"] = "非法辞退"
    elif any(keyword in text for keyword in ["n+1", "N+1", "无过失", "代通知金", "未提前通知"]):
        context["reason"] = "n_plus_1"
    else:
        context["reason"] = "合法解除"

    if years <= 0 and context.get("calc_type") != "notice_pay":
        return None
    return context


def calculate_from_query(query: str) -> Optional[str]:
    context = build_calculation_context_from_query(query)
    if context is None:
        return calculation_missing_info_message(query) if is_calculation_query(query) else None
    return calculate_compensation(context)
