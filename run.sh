#!/usr/bin/env bash
set -e

# ====== 请修改以下配置 ======
export LLM_BASE_URL="https://your-llm-endpoint/v1"
export LLM_API_KEY="sk-xxxxxxxxxxxxxxxx"
export LLM_MODEL="gpt-4o"
# ============================

python -m pip install -r requirements.txt

python main.py \
  --root ./projects \
  --output ./output \
  --cache ./cache \
  --risk-input ./risk_inputs.json \
  --batch-size 10 \
  --qps 6 \
  --retry-rounds 2 \
  --retry-delay 5 \
  --backup-keep 50 \
  -v