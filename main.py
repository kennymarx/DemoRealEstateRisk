# -*- coding: utf-8 -*-
"""主流程入口"""
import argparse
import json
import logging
import time
from pathlib import Path

from cache_manager import CacheManager
from config import AppConfig
from excel_writer import write_excel
from llm_client import LLMClient
from ocr_processor import OcrProcessor, merge_statements
from risk_analyzer import analyze_project_risk, load_risk_inputs
from scanner import find_financial_dirs, iter_projects
from summary_manager import SummaryManager, project_fingerprint, safe_filename

logger = logging.getLogger("main")


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="房地产合作项目财务报表识别与风险评估")
    p.add_argument("--root", help="项目根目录")
    p.add_argument("--output", help="输出目录")
    p.add_argument("--cache", help="缓存目录")
    p.add_argument("--batch-size", type=int, help="每次发送给大模型的图片数量（默认 10）")
    p.add_argument("--base-url", help="大模型 base url")
    p.add_argument("--api-key", help="大模型 api key")
    p.add_argument("--model", help="大模型名称")
    p.add_argument("--risk-input", help="外部风险信息 JSON 路径")
    p.add_argument("--qps", type=float, help="大模型每秒最大调用次数（默认 6）")
    p.add_argument("--qps-burst", type=float, help="允许的瞬时突发峰值（默认等于 QPS）")
    p.add_argument("--retry-rounds", type=int, help="失败项目的重试轮数（默认 2）")
    p.add_argument("--retry-delay", type=float, help="首次重试前的等待秒数（默认 5）")
    p.add_argument("--backup-keep", type=int,
                   help="汇总表备份保留个数（默认 50，0 表示禁用备份）")
    p.add_argument("--skip-risk", action="store_true", help="只做 OCR + Excel，跳过风险分析")
    p.add_argument("--force-rerun", action="store_true",
                   help="忽略汇总表，强制重跑所有项目的风险分析")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def analyze_one_project(llm, project_name, payload, risk_inputs, summary, reports_dir):
    fp = payload["fingerprint"]
    try:
        result = analyze_project_risk(llm, project_name, payload["statements"], risk_inputs)
    except Exception as e:  # noqa: BLE001
        logger.exception("项目 [%s] 风险分析失败：%s", project_name, e)
        return None, e

    devs = sorted({
        (st.get("company") or "").strip()
        for st in payload["statements"] if st.get("company")
    })
    years = sorted({
        str(st.get("year") or "").strip()
        for st in payload["statements"] if st.get("year")
    })

    clean_result = {k: v for k, v in result.items() if k != "_raw"}
    report_file = reports_dir / f"{safe_filename(project_name)}.json"
    report_file.write_text(
        json.dumps({
            "project_name": project_name,
            "fingerprint": fp,
            "developers": devs,
            "report_years": years,
            "statement_count": len(payload["statements"]),
            "risk_result": clean_result,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary.upsert(
        project_name,
        fingerprint=fp,
        status="success",
        developers=devs,
        report_years=years,
        statement_count=len(payload["statements"]),
        risk_level=result.get("risk_level"),
        risk_score=result.get("risk_score"),
        summary=result.get("summary"),
        key_risks=result.get("key_risks") or [],
        analysis=result.get("analysis"),
        suggestions=result.get("suggestions") or [],
        report_path=str(report_file),
        error=None,
    )
    return clean_result, None


def main():
    args = parse_args()
    setup_logging(args.verbose)

    cfg = AppConfig()
    if args.root:          cfg.root_dir = args.root
    if args.output:        cfg.output_dir = args.output
    if args.cache:         cfg.cache_dir = args.cache
    if args.batch_size:    cfg.batch_size = args.batch_size
    if args.risk_input:    cfg.risk_input_file = args.risk_input
    if args.base_url:      cfg.llm.base_url = args.base_url
    if args.api_key:       cfg.llm.api_key = args.api_key
    if args.model:         cfg.llm.model = args.model
    if args.qps:           cfg.llm.rate_limit_qps = args.qps
    if args.qps_burst:     cfg.llm.rate_limit_burst = args.qps_burst
    if args.retry_rounds is not None: cfg.retry_rounds = args.retry_rounds
    if args.retry_delay is not None:  cfg.retry_delay = args.retry_delay
    if args.backup_keep is not None:  cfg.summary_backup_keep = args.backup_keep
    if args.force_rerun:   cfg.force_rerun = True

    llm = LLMClient(cfg.llm)
    cache = CacheManager(cfg.cache_dir)
    ocr = OcrProcessor(llm, cache, cfg)

    out_dir = Path(cfg.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = out_dir / cfg.reports_subdir
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary = SummaryManager(
        out_dir / cfg.summary_json_name,
        out_dir / cfg.summary_excel_name,
        backup_dir=out_dir / cfg.summary_backup_dir,
        backup_keep=cfg.summary_backup_keep,
    )

    # ============ 阶段一：扫描 + OCR ============
    projects = iter_projects(cfg.root_dir)
    logger.info("发现 %d 个项目目录", len(projects))

    project_payloads = {}
    all_statements = []

    for project in projects:
        fs_dirs = find_financial_dirs(project, cfg.fs_dir_keywords, cfg.scan_max_depth)
        if not fs_dirs:
            logger.warning("项目 [%s] 未找到财务报表文件夹，跳过", project.name)
            continue

        fingerprint = project_fingerprint(project, fs_dirs, cfg.image_exts)

        stmts = []
        for fs_dir in fs_dirs:
            logger.info(">>> 项目[%s] 财报目录：%s", project.name, fs_dir)
            batches = ocr.process_dir(fs_dir)
            stmts.extend(merge_statements(batches, project.name))

        if not stmts:
            logger.warning("项目 [%s] 未提取到有效报表数据", project.name)
            continue

        project_payloads[project.name] = {
            "fs_dirs": fs_dirs,
            "fingerprint": fingerprint,
            "statements": stmts,
        }
        all_statements.extend(stmts)
        logger.info("项目 [%s] 共提取 %d 张报表", project.name, len(stmts))

    if not all_statements:
        logger.error("未提取到任何财务数据，流程结束")
        return

    # ============ 阶段二：写 Excel ============
    excel_path = out_dir / cfg.excel_name
    write_excel(all_statements, excel_path)
    logger.info("✅ 财务报表已写入：%s", excel_path)

    if args.skip_risk:
        summary.export_excel()
        summary.print_summary()
        return

    # ============ 阶段三：风险分析 + 重试 ============
    risk_inputs = load_risk_inputs(cfg.risk_input_file)
    project_entries = {}
    to_analyze = {}
    skipped_names = []
    analyzed_names = []

    for name, payload in project_payloads.items():
        if (not cfg.force_rerun) and summary.is_done(name, payload["fingerprint"]):
            logger.info("⏭  项目 [%s] 已完成且图片未变化，跳过风险分析", name)
            hist = summary.get(name)
            if hist:
                project_entries[name] = {
                    "project_name": name,
                    "risk_level": hist.get("risk_level"),
                    "risk_score": hist.get("risk_score"),
                    "summary": hist.get("summary"),
                    "key_risks": hist.get("key_risks"),
                    "from_summary": True,
                }
            skipped_names.append(name)
        else:
            to_analyze[name] = payload

    def run_batch(batch_names, attempt: int):
        still_failed = set()
        for n in batch_names:
            payload = to_analyze[n]
            result, err = analyze_one_project(
                llm, n, payload, risk_inputs, summary, reports_dir
            )
            if err:
                still_failed.add(n)
                summary.mark_failed(n, payload["fingerprint"], str(err), attempt=attempt)
                project_entries[n] = {
                    "project_name": n,
                    "risk_level": "未知",
                    "error": str(err),
                    "attempt": attempt,
                }
            else:
                analyzed_names.append(n)
                project_entries[n] = result
        return still_failed

    if to_analyze:
        logger.info("🚀 开始风险分析：%d 个项目", len(to_analyze))
        failed_names = run_batch(list(to_analyze.keys()), attempt=1)
    else:
        logger.info("无待分析项目")
        failed_names = set()

    total_attempts = 1
    for round_no in range(1, cfg.retry_rounds + 1):
        if not failed_names:
            break
        delay = cfg.retry_delay * (2 ** (round_no - 1))
        logger.info("🔁 第 %d/%d 轮重试：%d 个项目，等待 %.0fs 后开始",
                    round_no, cfg.retry_rounds, len(failed_names), delay)
        logger.info("   待重试：%s", sorted(failed_names))
        time.sleep(delay)
        failed_names = run_batch(list(failed_names), attempt=round_no + 1)
        total_attempts = round_no + 1

    if failed_names:
        logger.warning("⚠️  经过 %d 轮共 %d 次尝试，仍有 %d 个项目失败：%s",
                       cfg.retry_rounds, total_attempts,
                       len(failed_names), sorted(failed_names))

    # ============ 阶段四：输出 ============
    report = {
        "projects": list(project_entries.values()),
        "generated_from": str(excel_path),
        "summary": {
            "total": len(project_payloads),
            "analyzed": len(analyzed_names),
            "skipped": len(skipped_names),
            "failed": len(failed_names),
        },
    }
    report_path = out_dir / cfg.risk_report_name
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("✅ 全项目风险报告已写入：%s", report_path)

    summary_xlsx = summary.export_excel()
    logger.info("✅ 风险信息汇总表已写入：%s", summary_xlsx)

    print("\n" + "=" * 70)
    print("📊 本轮执行概况")
    print("=" * 70)
    print(f"  ✅ 新分析   ：{len(analyzed_names)} 个项目  {analyzed_names}")
    print(f"  ⏭  跳过     ：{len(skipped_names)} 个项目  {skipped_names}")
    if failed_names:
        print(f"  ❌ 失败     ：{len(failed_names)} 个项目  {sorted(failed_names)}")
    print("-" * 70)
    summary.print_summary()
    print("=" * 70)


if __name__ == "__main__":
    main()