# -*- coding: utf-8 -*-
"""风险评级"""
import hashlib
import json
import logging
from pathlib import Path

from llm_client import LLMClient, extract_json

logger = logging.getLogger(__name__)


RISK_PROMPT = """你是一名资深的房地产投资风险分析师，服务于房地产合作项目投资方。
请根据以下三方面信息，对【{project_name}】进行风险评级与分析。

================ 一、房地产开发商（交易对手）外部风险情况 ================
{developer_info}

================ 二、合作项目层面风险信息 ================
{project_info}

================ 三、财务报表情况（OCR 识别，可能有少量误差） ================
{financial_info}

分析要求：
1. 先识别每份报表的报告期间；只有年份时，按该年 12 月 31 日作为分析时点，并明确标注该假设。
2. 外部风险按发生日或信息生效日与财报时点逐年对齐。时点之后才发生或生效的信息，严禁用于解释或评级更早年度；只能从发生/生效年度起影响后续年度。
3. 最新信用评级、当前状态或当前舆情不能倒推为历史年度事实。没有日期/有效期的外部信息必须标为“时间未注明”，不得据此断言其在历史报告期已经存在或仍然有效。
4. 多个报告年度应分别分析，并说明外部事件与财务变化的先后关系；不得用最新一年的外部风险覆盖全部历史年度。晚于最后一份财报的信息只能单独标注为报告期后信息，不纳入历史财报期评级。
5. 结合报表年份判断财务变化趋势（资产负债率、货币资金、有息负债、营业收入与利润、经营性现金流等），并与同一时点之前已发生的外部风险及项目风险综合判断。
6. 输出风险等级：只能是「高」「中」「低」三档之一；风险评分 0-100，分数越高风险越大。
7. summary：一句话风险摘要，30 字以内；analysis：分析明细（400 字以内）；key_risks：3-6 条关键风险点。
8. 只输出 JSON，不要输出任何解释文字，不要使用 markdown 代码块。

输出 JSON 结构：
{{
  "project_name": "{project_name}",
  "risk_level": "高",
  "risk_score": 75,
  "summary": "一句话风险摘要（30 字以内）",
  "financial_trend": "财务状况趋势的简要描述",
  "developer_risk": "开发商外部风险判断",
  "project_risk": "合作项目风险判断",
  "analysis": "详细分析明细",
  "key_risks": ["关键风险点1", "关键风险点2", "关键风险点3"],
  "suggestions": ["建议1", "建议2"]
}}
"""


def load_risk_inputs(path) -> dict:
    p = Path(path)
    if not p.exists():
        logger.warning("未找到风险信息文件 %s，将使用空数据", p)
        return {"developers": {}, "projects": {}}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.error("风险信息文件解析失败：%s", e)
        return {"developers": {}, "projects": {}}


def _match_project(project_name: str, table: dict):
    if project_name in table:
        return table[project_name]
    for k, v in table.items():
        if k and (k in project_name or project_name in k):
            return v
    return None


def _risk_context(project_name: str, risk_inputs: dict) -> dict:
    developers = risk_inputs.get("developers", {}) or {}
    project = _match_project(project_name, risk_inputs.get("projects", {}) or {}) or {}
    developer_names = project.get("developers") or list(developers.keys())
    selected_developers = {
        name: developers[name]
        for name in developer_names
        if name in developers
    }
    return {"project": project, "developers": selected_developers}


def risk_context_fingerprint(project_name: str, risk_inputs: dict) -> str:
    context = json.dumps(
        _risk_context(project_name, risk_inputs),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def build_developer_info(project_name: str, risk_inputs: dict) -> str:
    developers = risk_inputs.get("developers", {}) or {}
    proj = _match_project(project_name, risk_inputs.get("projects", {}) or {}) or {}
    names = proj.get("developers") or list(developers.keys())

    lines = []
    for name in names:
        d = developers.get(name)
        if not d:
            lines.append(f"- {name}: （未提供外部风险信息）")
            continue
        lines.append(
            f"- {name}："
            f"信用评级={d.get('credit_rating', '未知')}；"
            f"外部风险={d.get('external_risk', '无')}；"
            f"舆情/诉讼/违约={d.get('news', '无')}"
        )
        events = d.get("risk_events") or d.get("events") or []
        if events:
            lines.append(
                "  有日期的风险事件（逐项按发生日期判断）："
                + json.dumps(events, ensure_ascii=False)
            )
    return "\n".join(lines) if lines else "（未提供开发商外部风险信息）"


def build_project_info(project_name: str, risk_inputs: dict) -> str:
    proj = _match_project(project_name, risk_inputs.get("projects", {}) or {})
    if not proj:
        return "（未提供合作项目风险信息）"
    return json.dumps(proj, ensure_ascii=False, indent=2)


def statements_to_text(statements, max_rows_per_stmt: int = 150) -> str:
    lines = []
    for st in statements:
        lines.append(
            f"### 项目：{st.get('project')} | 公司：{st.get('company')} | "
            f"年份：{st.get('year')} | 报表：{st.get('statement_type')} | 单位：{st.get('unit')}"
        )
        rows = st.get("rows", [])
        for r in rows[:max_rows_per_stmt]:
            lines.append(f"  - {r.get('item')} [{r.get('column')}]: {r.get('value')}")
        if len(rows) > max_rows_per_stmt:
            lines.append(f"  ...（其余 {len(rows) - max_rows_per_stmt} 行已省略）")
        lines.append("")
    return "\n".join(lines) if lines else "（未提取到财务数据）"


def _extract_sort_text(item) -> str:
    if isinstance(item, dict):
        return " ".join(
            str(item.get(key) or "")
            for key in ("risk", "description", "title", "note", "summary", "suggestion", "action")
        )
    return str(item or "")


def _risk_priority(item) -> int:
    text = _extract_sort_text(item).lower()
    if not text:
        return 2
    if any(term in text for term in (
        "违约", "逾期", "诉讼", "冻结", "被执行", "现金短债比", "流动性", "偿债", "到期",
        "债务", "负债率", "亏损", "经营现金流", "现金流", "缺口", "高风险", "暂缓新增",
        "暂停", "退出", "限制性准入", "提高首付比例", "强化增信"
    )):
        return 0
    if any(term in text for term in (
        "收入下降", "存货", "毛利率", "收窄", "筹资", "监测", "补充数据", "项目缺失",
        "补充项目", "整改", "审慎", "预售资金", "受托支付"
    )):
        return 1
    return 2


def _sort_risk_items(items):
    if not isinstance(items, list):
        return items
    return sorted(items, key=_risk_priority)


def analyze_project_risk(llm: LLMClient, project_name: str, statements, risk_inputs: dict) -> dict:
    report_years = sorted({
        str(st.get("year")).strip()
        for st in statements
        if st.get("year") is not None and str(st.get("year")).strip()
    })
    prompt = RISK_PROMPT.format(
        project_name=project_name,
        developer_info=build_developer_info(project_name, risk_inputs),
        project_info=build_project_info(project_name, risk_inputs),
        financial_info=statements_to_text(statements),
    ) + "\n财报涉及的报告年份：" + ("、".join(report_years) if report_years else "未能识别")
    raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
    try:
        result = extract_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.error("风险分析结果解析失败：%s", e)
        result = {"project_name": project_name, "risk_level": "未知", "_parse_error": str(e)}
    if isinstance(result, dict):
        result["key_risks"] = _sort_risk_items(result.get("key_risks") or [])
        result["suggestions"] = _sort_risk_items(result.get("suggestions") or [])
    result["_raw"] = raw
    return result