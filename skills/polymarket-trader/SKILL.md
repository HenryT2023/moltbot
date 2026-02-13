---
name: polymarket-trader
description: Polymarket 自动交易系统 - 定时扫描市场、AI 分析、自动交易并发送 Telegram 报告
metadata:
  emoji: 📈
  requires:
    bins:
      - python3
    env:
      - POLYMARKET_KEY
---

# Polymarket 自动交易系统

这个 Skill 用于自动化 Polymarket 预测市场交易。

## 功能

1. **市场扫描** - 使用 Gamma API 获取活跃市场
2. **AI 分析** - 使用 Gemini 分析市场概率
3. **自动交易** - 发现套利机会时自动下单
4. **Telegram 通知** - 发送交易和持仓报告

## 定时任务

系统每 15 分钟自动执行一次交易周期。

## 工具

### poly_scan

扫描 Polymarket 活跃市场。

```bash
cd /Users/tangheng/HenryBot && source polymarket-venv/bin/activate && python market_scanner.py
```

### poly_trade

执行一次交易周期并发送 Telegram 报告。

```bash
cd /Users/tangheng/HenryBot && source polymarket-venv/bin/activate && python polymarket_cron.py
```

### poly_positions

查看当前持仓和交易历史。

```bash
cd /Users/tangheng/HenryBot && source polymarket-venv/bin/activate && python -c "
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config
import os
os.environ['https_proxy'] = 'http://127.0.0.1:7890'

creds = ApiCreds(api_key=config.API_KEY, api_secret=config.API_SECRET, api_passphrase=config.API_PASSPHRASE)
client = ClobClient(host=config.HOST, key=config.PRIVATE_KEY, chain_id=config.CHAIN_ID, creds=creds, signature_type=2, funder='0xdC32539E1B60e77de554fEc4347fC04d980Fa523')

trades = client.get_trades()
print(f'最近交易: {len(trades)} 笔')
for t in trades[:5]:
    print(f'  {t.get(\"side\")} {t.get(\"outcome\")} x{t.get(\"size\")} @\${t.get(\"price\")} - {t.get(\"status\")}')
"
```

## 配置

- **代理钱包**: `0xdC32539E1B60e77de554fEc4347fC04d980Fa523`
- **单笔最大**: $5
- **最小优势**: 10%
- **扫描间隔**: 15 分钟
