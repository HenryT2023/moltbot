#!/usr/bin/env python3
"""检查持仓状态和市场结算情况"""
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from collections import defaultdict

# 设置代理
os.environ['https_proxy'] = 'http://127.0.0.1:7890'
os.environ['http_proxy'] = 'http://127.0.0.1:7890'

creds = ApiCreds(
    api_key=os.environ.get("POLYMARKET_API_KEY"),
    api_secret=os.environ.get("POLYMARKET_API_SECRET"),
    api_passphrase=os.environ.get("POLYMARKET_API_PASSPHRASE")
)
client = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ.get("POLYMARKET_PRIVATE_KEY"),
    chain_id=137,
    creds=creds
)

trades = client.get_trades()
positions = defaultdict(lambda: {"buy_qty": 0, "buy_cost": 0, "sell_qty": 0, "outcome": ""})
for t in trades:
    token_id = t.get("asset_id")
    side = t.get("side")
    size = float(t.get("size", 0))
    price = float(t.get("price", 0))
    outcome = t.get("outcome", "")
    if side == "BUY":
        positions[token_id]["buy_qty"] += size
        positions[token_id]["buy_cost"] += size * price
        positions[token_id]["outcome"] = outcome
    elif side == "SELL":
        positions[token_id]["sell_qty"] += size

# 显示有净持仓的
print("=" * 60)
print("持仓分析")
print("=" * 60)
total_cost = 0
total_value = 0
for tid, pos in positions.items():
    net = pos["buy_qty"] - pos["sell_qty"]
    if net > 0:
        avg_cost = pos["buy_cost"] / pos["buy_qty"] if pos["buy_qty"] > 0 else 0
        cost = net * avg_cost
        total_cost += cost
        try:
            book = client.get_order_book(tid)
            bid = float(book.bids[0].price) if book and book.bids else 0
        except:
            bid = 0
        value = net * bid
        total_value += value
        pnl = value - cost
        pnl_pct = pnl / cost * 100 if cost > 0 else 0
        outcome = pos["outcome"]
        print(f"{outcome} x{net:.0f}: cost=${cost:.2f} value=${value:.2f} PnL=${pnl:.2f} ({pnl_pct:+.1f}%)")

print("=" * 60)
print(f"总成本: ${total_cost:.2f}")
print(f"总估值: ${total_value:.2f}")
print(f"总PnL: ${total_value - total_cost:.2f}")
print("=" * 60)
