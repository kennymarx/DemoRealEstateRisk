# -*- coding: utf-8 -*-
"""将项目风险报告数据渲染为可读 Markdown。"""
from pathlib import Path


FIELD_LABELS = {
    "project_name": "合作项目",
    "fingerprint": "数据指纹",
    "developers": "开发商",
    "report_years": "财报年份",
    "statement_count": "报表数量",
    "risk_result": "风险分析结果",
    "risk_level": "风险等级",
    "risk_score": "风险评分",
    "summary": "风险摘要",
    "financial_trend": "财务趋势",
    "developer_risk": "开发商外部风险",
    "project_risk": "合作项目风险",
    "analysis": "综合分析",
    "key_risks": "主要风险",
    "suggestions": "风险建议",
    "report_date": "授信报告日期",
    "project_total_scale": "项目总规模",
    "project_investment_amount": "项目总投入",
    "invested_amount": "已投入金额",
    "remaining_investment": "尚未投入金额",
    "project_status": "项目状态",
    "construction_progress": "建设进度",
    "unsold_units": "待销售数量",
    "unsold_ratio": "待销售占比",
    "tail_end": "是否尾盘",
    "follow_on_funding_sufficiency": "后续资金充足性",
    "funding_assessment": "后续资金分析",
    "credit_disclosed_risks": "授信报告已披露风险",
    "financial_risks_not_reflected": "授信报告未反映的财务风险",
    "cross_checks": "交叉核对",
    "limitations": "资料局限",
    "credit_source_dirs": "授信报告来源目录",
    "credit_facts": "授信报告提取信息",
    "financial_source": "财务报表来源",
    "image_index": "图片序号",
    "company": "公司",
    "year": "年份",
    "statement_type": "报表类型",
    "unit": "金额单位",
    "item": "科目",
    "column": "列名",
    "value": "金额",
    "type": "类型",
    "date": "日期",
    "description": "说明",
    "evidence": "原文依据",
    "key_conditions": "授信关键条件",
    "funding_sources": "资金来源",
    "risks_disclosed": "报告披露风险",
}


def _label(key) -> str:
    return FIELD_LABELS.get(str(key), str(key).replace("_", " "))


def _render_value(value, depth: int = 0) -> list:
    if value is None:
        return ["未提供"]
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label = _label(key)
            if isinstance(item, (dict, list)):
                lines.extend([f"{'#' * min(depth + 3, 6)} {label}", ""])
                lines.extend(_render_value(item, depth + 1))
                lines.append("")
            else:
                lines.append(f"- **{label}：** {item if item is not None else '未提供'}")
        return lines
    if isinstance(value, list):
        if not value:
            return ["- 无"]
        lines = []
        for index, item in enumerate(value, 1):
            if isinstance(item, dict):
                lines.append(f"#### 第 {index} 项")
                lines.extend(_render_value(item, depth + 1))
            elif isinstance(item, list):
                lines.append(f"- 第 {index} 项：")
                lines.extend(f"  {line}" for line in _render_value(item, depth + 1))
            else:
                lines.append(f"- {item if item is not None else '未提供'}")
        return lines
    return [str(value)]


def write_markdown_report(data: dict, markdown_path, title: str) -> Path:
    path = Path(markdown_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    lines.extend(_render_value(data))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path