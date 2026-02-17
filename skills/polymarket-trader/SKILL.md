---
name: polymarket-trader
description: Polymarket automated trading system with 5 strategies - market scanning, AI analysis, auto trading, and Telegram reports.
metadata: {"moltbot":{"emoji":"📈","requires":{"bins":["python3"],"env":["POLYMARKET_KEY"]}}}
---

# Polymarket 自动交易系统

基于 Polymarket CLOB API 的自动化交易系统，支持多策略并行执行。

## 5 大交易策略

| 策略 | 触发条件 | 风险等级 | 说明 |
|------|----------|----------|------|
| 🌾 收割者 (Harvester) | Yes + No < 99.9% | 零风险 | 利用市场定价错误进行无风险套利 |
| 🧹 清洁工 (Cleaner) | NO >= 94% | 低风险 | 押注"永远不会发生的事" |
| 🎣 钓鱼者 (Fisher) | 价差 >= 5% | 中风险 | 双向挂单做市，赚取价差 |
| 💰 捡漏者 (Bargain) | 市场价 -5% | 低风险 | 低价挂单等待恐慌性抛售 |
| 📈 卖出 (Sell) | 利润 >= 2% | - | 自动挂单卖出锁定利润 |

## 文件结构

```text
polymarket-trader/
├── SKILL.md              # 本文件
├── polymarket_cron.py    # 主交易脚本 (定时任务入口)
├── trading_engine.py     # 交易引擎
├── market_scanner.py     # 市场扫描器
├── strategies.py         # 策略定义
├── ai_brain_gemini.py    # AI 分析模块 (Gemini)
├── auto_trader.py        # 自动交易器
├── trade.py              # 交易执行
├── check_balance.py      # 余额查询
├── close_position.py     # 平仓工具
├── get_ids.py            # 市场 ID 查询
└── scan_markets.py       # 市场扫描
```

## 工具

### poly_scan

扫描 Polymarket 活跃市场。

```bash
cd ~/HenryBot/moltbot/skills/polymarket-trader && source ~/polymarket-venv/bin/activate && python market_scanner.py
```

### poly_trade

执行一次交易周期并发送 Telegram 报告。

```bash
cd ~/HenryBot/moltbot/skills/polymarket-trader && source ~/polymarket-venv/bin/activate && python polymarket_cron.py
```

### poly_positions

查看当前持仓。

```bash
cd ~/HenryBot/moltbot/skills/polymarket-trader && source ~/polymarket-venv/bin/activate && python check_balance.py
```

## 配置

- **代理钱包**: `0xdC32539E1B60e77de554fEc4347fC04d980Fa523`
- **单笔最大**: $5
- **最小优势**: 10%
- **扫描间隔**: 15 分钟 (Cron)

## 环境变量

需要在 `config.py` 中配置（已 gitignore）：

```python
PRIVATE_KEY = "your_private_key"
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
API_PASSPHRASE = "your_api_passphrase"
```
