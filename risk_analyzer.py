# -*- coding: utf-8 -*-
"""风险评级"""
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
1. 结合报表年份，判断开发商财务状况的变化趋势（资产负债率、货币资金、有息负债、营业收入与利润、经营性现金流等）。
2. 结合开发商外部风险（信用评级、诉讼、债务违约、舆情等）与项目合作情况综合判断。
3. 输出风险等级：只能是「高」「中」「低」三档之一。
4. 输出风险评分 0-100，分数越高风险越大。
5. summary：一句话风险摘要，30 字以内，用于汇总表。
6. analysis：分析明细（400 字以内）；key_risks：3-6 条关键风险点。
7. 只输出 JSON，不要输出任何解释文字，不要使用 markdown 代码块。

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


def analyze_project_risk(llm: LLMClient, project_name: str, statements, risk_inputs: dict) -> dict:
    prompt = RISK_PROMPT.format(
        project_name=project_name,
        developer_info=build_developer_info(project_name, risk_inputs),
        project_info=build_project_info(project_name, risk_inputs),
        financial_info=statements_to_text(statements),
    )
    raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
    try:
        result = extract_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.error("风险分析结果解析失败：%s", e)
        result = {"project_name": project_name, "risk_level": "未知", "_parse_error": str(e)}
    result["_raw"] = raw
    return result