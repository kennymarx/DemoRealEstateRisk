# 房地产合作项目财务报表 OCR + 风险评估

自动扫描项目目录 → 大模型 OCR 识别财务报表图片 → 写入 Excel → 结合外部风险给出高/中/低三档评级。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备输入（见下节）

# 3. 配置大模型（编辑 run.sh 或 run.bat 顶部三行）

# 4. 一键运行
./run.sh          # Linux / Mac
run.bat           # Windows
```

## 输入数据准备

```
projects/
├── 项目A/
│   └── 2023年财务报表/      ← 文件夹名含"财务报表/财报/报表/财务报告"即可
│       ├── 资产负债表_01.jpg
│       ├── 利润表_01.jpg
│       └── ...
└── 项目B/
    └── 财务报告/
        └── ...
```

并在 `risk_inputs.json` 填写开发商与项目的外部风险信息（可选）。

## 输出结果

```
output/
├── 财务报表汇总.xlsx         # 「明细」长表 + 「宽表」
├── 风险分析报告.json         # 全部项目合并
├── 风险信息汇总表.json       # 断点续作依据
├── 风险信息汇总表.xlsx       # 给人看，等级带红/黄/绿
├── history/                  # 汇总表自动备份（保留最近 50 个）
└── reports/
    └── 项目名.json           # 单项目详细报告
```

## 命令行参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--root` | 项目根目录 | `./projects` |
| `--output` | 输出目录 | `./output` |
| `--cache` | 缓存目录 | `./cache` |
| `--batch-size` | 单次发送图片数 | 10 |
| `--base-url` | 大模型 base url | 环境变量 |
| `--api-key` | 大模型 api key | 环境变量 |
| `--model` | 大模型名称 | 环境变量 |
| `--risk-input` | 外部风险信息 JSON | `./risk_inputs.json` |
| `--qps` | 每秒最大调用次数 | 6 |
| `--qps-burst` | 瞬时突发峰值 | 等于 QPS |
| `--retry-rounds` | 失败重试轮数 | 2 |
| `--retry-delay` | 首次重试等待秒数 | 5 |
| `--backup-keep` | 汇总表备份保留个数 | 50（0=禁用） |
| `--skip-risk` | 只做 OCR + Excel | 关 |
| `--force-rerun` | 忽略汇总表全量重跑 | 关 |
| `-v` | 详细日志 | 关 |

## 核心机制

### 1. 分批 OCR + 缓存
- 每批默认 10 张图
- 每批结果缓存到 `cache/`
- 中途崩溃重跑时，已识别批次直接命中缓存

### 2. 大模型限流（默认 6 QPS）
- 令牌桶算法，允许瞬时突发
- 服务端返回 429 时自动指数退避
- 线程安全，未来改并发也不会超限

### 3. 断点续作
- 每个项目计算**指纹**（图片路径+大小+mtime 的 MD5）
- 指纹不变 + 上次成功 → 跳过风险分析
- 指纹变化 / 上次失败 → 自动重跑

### 4. 失败重试队列
- 单项目独立 try/except，互不影响
- 首轮结束后失败项目进队列
- 按 5s → 10s → 20s 指数退避重试

### 5. 汇总表增量备份
- 每次覆盖前自动备份到 `output/history/`
- 内容与最新备份相同则跳过
- 默认保留最近 50 个

## 人工恢复汇总表

```python
from summary_manager import SummaryManager

s = SummaryManager("./output/风险信息汇总表.json")
print(s.list_backups())                                  # 查看备份
s.restore_from_backup("./output/history/汇总表_xxx.json")  # 恢复
```

## 常见问题

**Q: OCR 结果不准？**
A: 编辑 `ocr_processor.py` 中 `OCR_PROMPT_TEMPLATE` 补充术语示例。

**Q: 服务端限流？**
A: 调小 `--qps`，或增大 `--retry-delay`。

**Q: 想并发提速？**
A: 把 `main.py` 阶段一改为 `ThreadPoolExecutor`，限流器已线程安全。

**Q: 想改回看历史某次汇总？**
A: 打开 `output/history/` 里的任意 JSON，或调用 `restore_from_backup`。