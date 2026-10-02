# -*- coding: utf-8 -*-
"""全局配置"""
import os
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "gpt-4o")
    temperature: float = 0.1
    max_tokens: int = 8192
    timeout: int = 300
    max_retries: int = 3

    # 限流
    rate_limit_qps: float = 6.0
    rate_limit_burst: float = None
    rate_limit_timeout: float = None


@dataclass
class AppConfig:
    # ---- 目录 ----
    root_dir: str = "./projects"
    cache_dir: str = "./cache"
    output_dir: str = "./output"

    # ---- 输出文件名 ----
    projects_subdir: str = "projects"
    project_excel_name: str = "财务报表.xlsx"
    project_risk_report_name: str = "风险分析报告.json"
    comprehensive_risk_report_name: str = "综合风险报告.json"
    comprehensive_summary_json_name: str = "综合风险信息汇总表.json"
    comprehensive_summary_excel_name: str = "综合风险信息汇总表.xlsx"
    risk_input_file: str = "./risk_inputs.json"

    # ---- 风险信息汇总表 ----
    summary_json_name: str = "风险信息汇总表.json"
    summary_excel_name: str = "风险信息汇总表.xlsx"
    force_rerun: bool = False

    # ---- 汇总表增量备份 ----
    summary_backup_dir: str = "history"
    summary_backup_keep: int = 50

    # ---- 失败重试队列 ----
    retry_rounds: int = 2
    retry_delay: float = 5.0

    # ---- OCR ----
    batch_size: int = 1
    image_exts: tuple = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
    fs_dir_keywords: tuple = ("财务报表", "财务报告", "报表", "财报")
    credit_dir_keywords: tuple = ("授信报告", "授信资料", "授信材料", "授信")
    scan_max_depth: int = 4

    llm: LLMConfig = field(default_factory=LLMConfig)