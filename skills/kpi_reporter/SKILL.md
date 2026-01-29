---
name: kpi_reporter
description: 自动化 KPI 报表生成与推送。支持从本地 CSV/JSON 数据源抓取数据，计算 KPI 指标，生成 Excel 报表，并推送摘要到 Slack。支持定时（cron）和手动触发。
metadata: {"moltbot":{"emoji":"📈","requires":{"bins":["node","python3"]}}}
---

# KPI Reporter

## 概述

KPI Reporter 是一个自动化报表生成技能，用于替代人工每周/每日拉取数据、清洗、计算指标、生成报表并推送到 Slack。

**核心流程**：数据抓取 → 清洗/聚合 → KPI 计算 → 报表生成 → 推送摘要 + 附件

## 快速开始

### 安装依赖

```bash
cd skills/kpi_reporter
pnpm install
pip install -r requirements.txt
```

### 配置

1. 确保 Moltbot 已配置 Slack channel
2. 设置环境变量（可选）：
   - `KPI_REPORTER_OUTPUT_DIR`：报表输出目录（默认 `./runs`）
   - `KPI_REPORTER_SLACK_ALLOWLIST`：允许推送的 Slack 频道（如 `#growth,#ops`）

### 运行

```bash
# 本地命令行
npx tsx src/index.ts --time_window yesterday --slack_channel "#growth"

# 或通过 Moltbot 聊天
```

## 常用指令示例

### 1. 生成昨日 KPI 报表并发送到指定频道

```text
生成昨天的KPI报表并发到 #growth
```

### 2. 生成上周报表（dry run 模式，不实际发送）

```text
生成上周KPI报表，dry run
```

### 3. 生成近7天报表并 @提醒指定人员

```text
生成近7天KPI报表，发到 #ops 并 @peter
```

### 4. 生成本月报表

```text
生成本月KPI报表
```

### 5. 自定义日期范围

```text
生成2024-01-01到2024-01-15的KPI报表
```

## 工具调用参数

```json
{
  "tool": "kpi_reporter.run",
  "args": {
    "time_window": "yesterday | last_7_days | last_week | this_month | {start, end}",
    "datasource": "local_files",
    "output": {"xlsx": true, "html": false, "slack": true},
    "slack": {"channel": "#growth", "mention": ["@ops"], "thread_ts": null},
    "dry_run": false
  }
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
| ---- | ---- | ---- | ---- |
| time_window | string/object | 是 | 时间窗口：yesterday/last_7_days/last_week/this_month 或 {start, end} |
| datasource | string | 否 | 数据源，默认 local_files |
| output | object | 否 | 输出格式，默认 {xlsx: true, slack: true} |
| slack | object | 否 | Slack 配置：channel, mention, thread_ts |
| dry_run | boolean | 否 | 试运行模式，不实际发送 |

## 输出产物

每次运行会在 `runs/<run_id>/` 目录下生成：

```text
runs/
  2024-01-15_143022_abc123/
    raw/                    # 原始数据快照
    processed/              # 处理后数据
    report.xlsx             # Excel 报表
    slack_message.txt       # Slack 消息文本
    meta.json               # 运行元信息
    run.log                 # 运行日志
```

### report.xlsx 结构

- **Summary**：KPI 总览 + 环比变化
- **BySource**：按数据源拆分的指标
- **RawPreview**：原始数据抽样

## 定时任务配置

### 每周一 09:00 生成上周报表

在 Moltbot cron 配置中添加：

```yaml
cron:
  - name: weekly_kpi_report
    schedule: "0 9 * * 1"
    command: "生成上周KPI报表并发到 #growth"
```

### 每日 09:00 生成昨日报表

```yaml
cron:
  - name: daily_kpi_report
    schedule: "0 9 * * *"
    command: "生成昨天的KPI报表并发到 #ops"
```

## KPI 配置

编辑 `config/kpis.yaml` 自定义 KPI 计算规则：

```yaml
kpis:
  - name: "Leads"
    expr: "sum(metric == 'leads')"
    description: "总线索数"
  
  - name: "Spend"
    expr: "sum(metric == 'ad_spend')"
    description: "广告支出"
  
  - name: "CAC"
    expr: "ratio('Spend', 'Customers')"
    description: "客户获取成本"
```

## 故障排查

### 常见错误

1. **数据文件不存在**：检查 `data/` 目录下是否有对应的 CSV 文件
2. **Slack 发送失败**：确认 channel 在 allowlist 中，检查 bot token 权限
3. **KPI 计算错误**：查看 `run.log` 中的详细错误信息

### 查看运行日志

```bash
cat runs/<run_id>/run.log
```

### 查看运行元信息

```bash
cat runs/<run_id>/meta.json
```

## 数据源扩展

当前支持 `local_files` 适配器。如需添加新数据源，在 `src/pipeline/adapters/` 下创建新适配器并实现 `DataAdapter` 接口。
