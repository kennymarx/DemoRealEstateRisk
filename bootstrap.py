# -*- coding: utf-8 -*-
"""运行一次即可生成整个项目结构"""
from pathlib import Path

ROOT = Path("realestate_risk")

FILES = {
    "requirements.txt": """requests>=2.31.0
openpyxl>=3.1.2
""",
    # ↓↓↓ 把上面所有文件内容原样粘进来 ↓↓↓
    # "config.py": '''...''',
    # "rate_limiter.py": '''...''',
    # "llm_client.py": '''...''',
    # "scanner.py": '''...''',
    # "cache_manager.py": '''...''',
    # "ocr_processor.py": '''...''',
    # "excel_writer.py": '''...''',
    # "risk_analyzer.py": '''...''',
    # "summary_manager.py": '''...''',
    # "main.py": '''...''',
    # "risk_inputs.json": '''...''',
    # "run.sh": '''...''',
    # "run.bat": '''...''',
    # ".gitignore": '''...''',
    # "README.md": '''...''',
}

DIRS = ["projects", "cache", "output", "output/reports", "output/history"]


def main():
    ROOT.mkdir(exist_ok=True)
    for d in DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    for name, content in FILES.items():
        p = ROOT / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        print(f"✅ {p}")
    (ROOT / "run.sh").chmod(0o755)
    print(f"\n🎉 项目已生成到 {ROOT.resolve()}")


if __name__ == "__main__":
    main()