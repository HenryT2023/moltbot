# KPI Reporter

📈 自动化 KPI 报表生成与推送工具

## 功能特性

- **数据抓取**：从本地 CSV 文件读取多源数据（CRM、广告、网站、订单）
- **KPI 计算**：支持 sum/count/avg/ratio 表达式，YAML 配置驱动
- **环比分析**：自动计算与上一周期的对比变化
- **报表生成**：生成 Excel 报表（Summary/BySource/RawPreview 三个 Sheet）
- **Slack 推送**：发送摘要文本 + 报表附件到指定频道
- **时间窗口**：支持 yesterday/last_7_days/last_week/this_month/自定义日期

## 快速开始

### 安装依赖

```bash
cd skills/kpi_reporter

# Node.js 依赖
npm install

# Python 依赖（用于 Excel 生成）
pip3 install -r requirements.txt
```

### 运行示例

```bash
# 生成指定日期范围的报表（dry run 模式）
npx tsx src/index.ts --time_window 2024-01-15:2024-01-21 --dry_run

# 生成昨日报表并发送到 Slack
npx tsx src/index.ts --time_window yesterday --slack_channel "#growth"

# 查看帮助
npx tsx src/index.ts --help
```

### 运行测试

```bash
npx tsx tests/test_pipeline_smoke.ts
```

## 目录结构

```text
kpi_reporter/
├── SKILL.md              # Moltbot skill 文档
├── README.md             # 本文件
├── package.json          # Node.js 依赖
├── requirements.txt      # Python 依赖
├── config/
│   ├── kpis.yaml         # KPI 定义配置
│   └── columns_map.yaml  # 字段映射配置
├── data/                 # 样例数据
│   ├── sample_crm.csv
│   ├── sample_ads.csv
│   ├── sample_web.csv
│   └── sample_orders.csv
├── src/
│   ├── index.ts          # CLI 入口
│   ├── utils/            # 工具函数
│   └── pipeline/         # 管线模块
│       ├── adapters/     # 数据适配器
│       ├── transform/    # 数据转换
│       ├── report/       # 报表生成
│       └── notify/       # 通知推送
├── tests/                # 测试文件
└── runs/                 # 运行产物输出
```

## 配置说明

### KPI 定义 (`config/kpis.yaml`)

```yaml
kpis:
  - name: "Leads"
    expr: "sum"
    filter:
      metric: "leads"
    description: "总线索数"

  - name: "CAC"
    expr: "ratio"
    numerator: "Spend"
    denominator: "Customers"
    description: "客户获取成本"
```

### 环境变量

| 变量 | 说明 | 默认值 |
| ---- | ---- | ------ |
| `SLACK_BOT_TOKEN` | Slack Bot Token | 必填（发送时） |
| `KPI_REPORTER_OUTPUT_DIR` | 报表输出目录 | `./runs` |
| `KPI_REPORTER_SLACK_ALLOWLIST` | 允许的 Slack 频道 | 无限制 |

## 输出产物

每次运行会在 `runs/<run_id>/` 目录下生成：

| 文件 | 说明 |
| ---- | ---- |
| `raw/raw_data.json` | 原始数据快照 |
| `processed/data.json` | 标准化后的数据 |
| `report.xlsx` | Excel 报表 |
| `slack_message.txt` | Slack 消息文本 |
| `meta.json` | 运行元信息 |
| `run.log` | 运行日志 |

## 常用命令

```bash
# 生成昨日报表
npx tsx src/index.ts -t yesterday

# 生成上周报表
npx tsx src/index.ts -t last_week

# 生成近7天报表
npx tsx src/index.ts -t last_7_days

# 自定义日期范围
npx tsx src/index.ts -t 2024-01-01:2024-01-15

# 发送到 Slack（需配置 SLACK_BOT_TOKEN）
npx tsx src/index.ts -t yesterday -c "#growth"

# Dry run 模式（不发送）
npx tsx src/index.ts -t yesterday --dry_run
```

## 技术栈

- **Node.js + TypeScript**：CLI 入口、数据处理、Slack 推送
- **Python + openpyxl**：Excel 报表生成
- **date-fns**：时间窗口计算
- **csv-parse**：CSV 解析
- **@slack/web-api**：Slack API 调用

## License

MIT
