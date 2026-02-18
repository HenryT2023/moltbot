#!/usr/bin/env python3
"""
Polymarket 定时交易脚本
- 每 15 分钟执行一次
- 扫描市场、AI 分析、自动交易
- 通过 Telegram 发送交易和持仓总结
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging
import os
import sys

# 设置代理
os.environ['https_proxy'] = 'http://127.0.0.1:7890'
os.environ['http_proxy'] = 'http://127.0.0.1:7890'

# 配置日志
log_dir = os.path.expanduser('~/polymarket-logs')
log_file = os.path.join(log_dir, 'polymarket_cron.log')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

import config
from market_scanner import (
    fetch_active_markets, 
    fetch_breaking_news_markets,
    fetch_newest_markets,
    fetch_by_liquidity,
    fetch_by_volume,
    fetch_by_24h_volume,
    fetch_ending_soon,
    fetch_competitive,
    fetch_all_sorted_markets,
    fetch_priority_markets,
    filter_markets, 
    get_market_prices,
    fetch_clob_markets,
    filter_clob_markets,
)
from ai_brain_gemini import analyze_market_with_gemini

# ================= 配置 =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8235051205:AAEtOGdqFOcfno2xzONVHaMuHgirlZx0uk4")
TELEGRAM_CHAT_ID = "8054772943"
PROXY_WALLET = "0xdC32539E1B60e77de554fEc4347fC04d980Fa523"

# ============== 资金管理配置 ($200 本金) ==============
TOTAL_CAPITAL = 200.0        # 总本金
MAX_POSITION_PCT = 0.80      # 最大仓位比例 80%
MAX_TOTAL_POSITION = TOTAL_CAPITAL * MAX_POSITION_PCT  # $160
MAX_SINGLE_POSITION = 30.0   # 单票最大持仓 $30
MIN_AVAILABLE_BALANCE = 20.0 # 最小可用余额，低于此值停止开仓
MAX_POSITION_COUNT = 25      # 最大持仓数量
COOLDOWN_HOURS = 24          # 同一市场冷却时间（小时）

# ============== 止损配置 ==============
STOP_LOSS_PCT = 0.05         # 固定止损 -5%
TIME_STOP_DAYS = 7           # 时间止损：持仓超过7天且无盈利则清仓
TRAILING_PROFIT_TRIGGER = 0.02  # 移动止盈触发：盈利 2%
TRAILING_PROFIT_CALLBACK = 0.01 # 移动止盈回撤：1%

# ============== 收割者策略配置 (Harvester) ==============
# 核心逻辑：不预测涨跌，只利用 Yes + No < 1 的数学错误定价
# 单笔收益：几美分 | 执行频率：高频 | 风险：零风险套利
DRY_RUN = False

# 收割者策略参数 (核心策略)
HARVESTER_THRESHOLD = 0.995  # Yes + No < 99.5% 时触发套利 (放宽)
HARVESTER_BET_PER_SIDE = 2.0 # 每边下注金额 $2 (总投入 $4)
HARVESTER_MIN_PROFIT = 0.001 # 最小利润 0.1 美分
HARVESTER_MAX_TRADES = 3     # 每周期最多套利次数 (降低)

# 清洁工策略参数 (押注"永远不会发生的事")
CLEANER_MIN_NO_PRICE = 0.94  # NO 价格 >= 94% 才买入
CLEANER_MAX_BET = 2.0        # 清洁工单笔最大 $2 (降低)
CLEANER_MAX_TRADES = 3       # 每周期最多清洁工交易

# 钓鱼者策略参数 (做市商策略 - Spread Fishing)
# 原理：在买卖价差大的市场双向挂单，赚取价差
FISHER_MIN_SPREAD = 0.05     # 最小价差 5% 才值得做市
FISHER_BET_SIZE = 2.0        # 每边挂单金额 $2
FISHER_EDGE_FROM_MID = 0.02  # 距离中间价的偏移 2%
FISHER_MAX_TRADES = 1        # 每周期最多做市次数 (降低)
FISHER_ENABLED = False       # 暂时禁用钓鱼者策略

# 捡漏者策略参数 (低价挂单等待砸盘)
# 原理：在市场价 -5% 位置挂买单，等待恐慌性抛售
BARGAIN_DISCOUNT = 0.05      # 低于市场价 5% 挂单
BARGAIN_BET_SIZE = 2.0       # 每笔挂单金额 $2
BARGAIN_MAX_TRADES = 2       # 每周期最多挂单数 (降低)
BARGAIN_MIN_VOLUME = 1000    # 最小交易量要求 (过滤冷门市场)
BARGAIN_ENABLED = True       # 启用捡漏者策略

# 卖出策略参数
SELL_TARGET_PROFIT_PCT = 0.00   # 目标利润: 1美分即卖 (高频模式)
SELL_MIN_BID_PRICE = 0.05       # 最低 bid 价格 (低于此价格不卖)
SELL_LIMIT_PRICE_OFFSET = 0.00  # 挂单价格偏移 (0 = 按目标价挂单)

# AI 信号策略参数 (辅助策略)
AI_MAX_BET = 3.0             # AI 信号单笔最大 $3 (主力策略)
AI_MIN_EDGE = 0.08           # AI 信号最小优势 8% (放宽)
AI_MAX_MARKETS = 10          # AI 分析市场数 (扩大)
AI_MAX_TRADES = 4            # 每周期最多 AI 交易 (提升)

# 每周期最大总交易数
MAX_TRADES_PER_CYCLE = 8     # 买入策略最多 8 笔（卖出不占此配额）

# ============== 新闻驱动策略 (Trading Scout) ==============
NEWS_ENABLED = True
NEWS_MAX_BET = 3.0           # 新闻信号单笔最大 $3
NEWS_MIN_CONFIDENCE = 7      # Gemini 置信度阈值 (1-10)
NEWS_MAX_TRADES = 2          # 每周期最多新闻驱动交易
NEWS_FRESHNESS = "pd"        # Brave 搜索时效: pd=过去24h
NEWS_KEYWORDS = [
    "Trump executive order 2026",
    "US tariff trade war new",
    "SEC crypto regulation 2026",
    "Bitcoin ETF news today",
    "Fed interest rate decision",
    "US government shutdown deadline",
    "AI regulation bill Congress",
    "Ukraine Russia ceasefire deal",
]
# ========================================


def escape_markdown(text: str) -> str:
    """转义 Markdown 特殊字符"""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, '\\' + char)
    return text


def send_telegram_message(message: str):
    """发送 Telegram 消息，自动添加 Polymarket 标识"""
    # 添加来源标识
    tagged_message = f"🎰 [Polymarket]\n\n{message}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": tagged_message
    }
    
    try:
        resp = requests.post(url, json=data, timeout=10)
        if resp.status_code == 200:
            print("✅ Telegram 消息已发送")
        else:
            print(f"⚠️ Telegram 发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")


def init_client() -> ClobClient:
    """初始化 Polymarket 客户端"""
    creds = ApiCreds(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        api_passphrase=config.API_PASSPHRASE
    )
    
    return ClobClient(
        host=config.HOST,
        key=config.PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        creds=creds,
        signature_type=2,
        funder=PROXY_WALLET
    )


# ============== 持仓和余额检测 ==============
# 记录已交易的市场和时间，用于冷却期检查
# 持久化到文件，避免 cron 重启后冷却失效
TRADED_MARKETS_FILE = os.path.join(log_dir, 'traded_markets.json')

def _load_traded_markets() -> dict:
    """从文件加载交易记录，清理过期条目"""
    try:
        if os.path.exists(TRADED_MARKETS_FILE):
            with open(TRADED_MARKETS_FILE, 'r') as f:
                data = json.load(f)
            # 清理过期条目
            now = datetime.now()
            cooldown_seconds = COOLDOWN_HOURS * 3600
            cleaned = {}
            for token_id, ts_str in data.items():
                ts = datetime.fromisoformat(ts_str)
                if (now - ts).total_seconds() < cooldown_seconds:
                    cleaned[token_id] = ts_str
            return cleaned
    except Exception as e:
        logger.warning(f"加载交易记录失败: {e}")
    return {}

def _save_traded_markets(data: dict):
    """保存交易记录到文件"""
    try:
        with open(TRADED_MARKETS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"保存交易记录失败: {e}")

_traded_markets = _load_traded_markets()


def get_current_positions(client: ClobClient) -> dict:
    """
    获取当前所有持仓的详细信息
    返回: {
        'positions': [{token_id, outcome, quantity, cost, avg_cost, market}],
        'total_cost': float,
        'position_count': int,
        'available_balance': float
    }
    """
    result = {
        'positions': [],
        'total_cost': 0.0,
        'position_count': 0,
        'available_balance': TOTAL_CAPITAL
    }
    
    try:
        trades = client.get_trades()
        
        # 按 token 统计持仓
        positions = {}
        for t in trades:
            token_id = t.get('asset_id', '')
            side = t.get('side', '')
            size = float(t.get('size', 0))
            price = float(t.get('price', 0))
            outcome = t.get('outcome', '')
            market = t.get('market', '')[:50] if t.get('market') else ''
            created_at = t.get('created_at', '')
            
            if not token_id:
                continue
            
            if token_id not in positions:
                positions[token_id] = {
                    'token_id': token_id,
                    'outcome': outcome,
                    'market': market,
                    'buy_qty': 0,
                    'buy_cost': 0,
                    'sell_qty': 0,
                    'first_buy_time': created_at
                }
            
            if side == 'BUY':
                positions[token_id]['buy_qty'] += size
                positions[token_id]['buy_cost'] += size * price
            elif side == 'SELL':
                positions[token_id]['sell_qty'] += size
        
        # 过滤出有持仓的
        for token_id, pos in positions.items():
            net_qty = pos['buy_qty'] - pos['sell_qty']
            if net_qty > 0:
                avg_cost = pos['buy_cost'] / pos['buy_qty'] if pos['buy_qty'] > 0 else 0
                net_cost = net_qty * avg_cost
                pos['quantity'] = net_qty
                pos['cost'] = net_cost
                pos['avg_cost'] = avg_cost
                result['positions'].append(pos)
                result['total_cost'] += net_cost
        
        result['position_count'] = len(result['positions'])
        result['available_balance'] = TOTAL_CAPITAL - result['total_cost']
        
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
    
    return result


def check_can_open_position(client: ClobClient, token_id: str, amount: float) -> tuple:
    """
    检查是否可以开仓
    返回: (can_open: bool, reason: str)
    """
    pos_info = get_current_positions(client)
    
    # 1. 检查可用余额
    if pos_info['available_balance'] < MIN_AVAILABLE_BALANCE:
        return False, f"余额不足: ${pos_info['available_balance']:.2f} < ${MIN_AVAILABLE_BALANCE}"
    
    # 2. 检查总仓位
    if pos_info['total_cost'] + amount > MAX_TOTAL_POSITION:
        return False, f"总仓位超限: ${pos_info['total_cost']:.2f} + ${amount:.2f} > ${MAX_TOTAL_POSITION}"
    
    # 3. 检查持仓数量
    if pos_info['position_count'] >= MAX_POSITION_COUNT:
        # 检查是否是已有持仓的加仓
        existing = [p for p in pos_info['positions'] if p['token_id'] == token_id]
        if not existing:
            return False, f"持仓数量已满: {pos_info['position_count']} >= {MAX_POSITION_COUNT}"
    
    # 4. 检查单票持仓限制
    for pos in pos_info['positions']:
        if pos['token_id'] == token_id:
            if pos['cost'] + amount > MAX_SINGLE_POSITION:
                return False, f"单票超限: ${pos['cost']:.2f} + ${amount:.2f} > ${MAX_SINGLE_POSITION}"
    
    # 5. 检查冷却期（从持久化文件加载）
    if token_id in _traded_markets:
        try:
            last_trade_time = datetime.fromisoformat(_traded_markets[token_id])
        except:
            last_trade_time = datetime.now()
        cooldown_seconds = COOLDOWN_HOURS * 3600
        if (datetime.now() - last_trade_time).total_seconds() < cooldown_seconds:
            hours_left = (cooldown_seconds - (datetime.now() - last_trade_time).total_seconds()) / 3600
            return False, f"冷却期: 还需等待 {hours_left:.1f} 小时"
    
    return True, "OK"


def record_trade(token_id: str):
    """记录交易时间，用于冷却期检查（持久化到文件）"""
    _traded_markets[token_id] = datetime.now().isoformat()
    _save_traded_markets(_traded_markets)


def get_positions(client: ClobClient) -> List[dict]:
    """获取当前持仓"""
    try:
        trades = client.get_trades()
        return trades[:10]  # 最近 10 笔
    except Exception as e:
        print(f"❌ 获取持仓失败: {e}")
        return []


def analyze_portfolio(client: ClobClient) -> dict:
    """
    分析投资组合收益
    返回：总成本、总估值、已实现收益、未实现收益
    """
    result = {
        'total_trades': 0,
        'buy_count': 0,
        'sell_count': 0,
        'total_buy_cost': 0,
        'total_sell_revenue': 0,
        'positions': [],
        'position_cost': 0,
        'position_value': 0,
        'unrealized_pnl': 0
    }
    
    try:
        trades = client.get_trades()
        result['total_trades'] = len(trades)
        
        # 按 token 统计持仓
        positions = {}
        
        for t in trades:
            side = t.get('side', '')
            size = float(t.get('size', 0))
            price = float(t.get('price', 0))
            outcome = t.get('outcome', '')
            token_id = t.get('asset_id', '')
            
            cost = size * price
            
            if side == 'BUY':
                result['total_buy_cost'] += cost
                result['buy_count'] += 1
            elif side == 'SELL':
                result['total_sell_revenue'] += cost
                result['sell_count'] += 1
            
            # 统计持仓
            if token_id:
                if token_id not in positions:
                    positions[token_id] = {'outcome': outcome, 'buy_qty': 0, 'buy_cost': 0, 'sell_qty': 0, 'token_id': token_id}
                if side == 'BUY':
                    positions[token_id]['buy_qty'] += size
                    positions[token_id]['buy_cost'] += cost
                elif side == 'SELL':
                    positions[token_id]['sell_qty'] += size
        
        # 计算持仓价值（用 order book 实时 bid 估值）
        for token_id, pos in positions.items():
            net_qty = pos['buy_qty'] - pos['sell_qty']
            if net_qty > 0:
                avg_cost = pos['buy_cost'] / pos['buy_qty'] if pos['buy_qty'] > 0 else 0
                net_cost = net_qty * avg_cost
                # 获取当前市场价 (bid) 进行估值
                # Polymarket order book 极度稀疏 (bid=0.001, ask=0.999)
                # bid < 0.05 时用成本价估值，避免虚假低估
                try:
                    book = client.get_order_book(token_id)
                    if book and book.bids and len(book.bids) > 0:
                        current_bid = float(book.bids[0].price)
                        if current_bid < 0.05:
                            current_bid = avg_cost  # 稀疏book，用成本价
                    else:
                        current_bid = avg_cost
                except:
                    current_bid = avg_cost
                estimated_value = net_qty * current_bid
                
                result['positions'].append({
                    'outcome': pos['outcome'],
                    'quantity': net_qty,
                    'avg_cost': avg_cost,
                    'cost': net_cost,
                    'value': estimated_value,
                    'current_price': current_bid,
                    'pnl': estimated_value - net_cost
                })
                result['position_cost'] += net_cost
                result['position_value'] += estimated_value
        
        result['unrealized_pnl'] = result['position_value'] - result['position_cost']
        
    except Exception as e:
        print(f"❌ 分析投资组合失败: {e}")
    
    return result


def format_portfolio_report(portfolio: dict) -> str:
    """格式化投资组合报告 - 简明版"""
    n_pos = len(portfolio.get('positions', []))
    cost = portfolio.get('position_cost', 0)
    value = portfolio.get('position_value', 0)
    pnl = portfolio.get('unrealized_pnl', 0)
    pnl_sign = '+' if pnl >= 0 else ''
    return f"💼 {n_pos}仓 成本${cost:.2f} 估值${value:.2f} PnL {pnl_sign}${pnl:.2f}"


def analyze_positions_for_sell(client: ClobClient) -> List[dict]:
    """
    分析当前持仓，检测卖出机会
    
    卖出模式：
    1. 止损卖出：亏损超过 STOP_LOSS_PCT (5%)
    2. 时间止损：持仓超过 TIME_STOP_DAYS 天且无盈利
    3. 获利了结：当前价格已达到目标利润
    4. NO 接近结算：NO 价格 >= 98%，锁定利润
    5. 挂单模式：按目标价格挂限价单等待成交
    """
    sell_opportunities = []
    
    try:
        trades = client.get_trades()
        
        # 统计持仓
        positions = {}
        for t in trades:
            token_id = t.get('asset_id', '')
            side = t.get('side', '')
            size = float(t.get('size', 0))
            price = float(t.get('price', 0))
            outcome = t.get('outcome', '')
            created_at = t.get('created_at', '')
            
            if not token_id:
                continue
            
            if token_id not in positions:
                positions[token_id] = {
                    'token_id': token_id,
                    'outcome': outcome,
                    'buy_qty': 0,
                    'buy_cost': 0,
                    'sell_qty': 0,
                    'first_buy_time': None,
                    'trades': []
                }
            
            if side == 'BUY':
                positions[token_id]['buy_qty'] += size
                positions[token_id]['buy_cost'] += size * price
                if positions[token_id]['first_buy_time'] is None and created_at:
                    positions[token_id]['first_buy_time'] = created_at
            elif side == 'SELL':
                positions[token_id]['sell_qty'] += size
            
            positions[token_id]['trades'].append(t)
        
        # 分析每个持仓的卖出机会
        for token_id, pos in positions.items():
            net_qty = pos['buy_qty'] - pos['sell_qty']
            if net_qty <= 0:
                continue
            
            avg_cost = pos['buy_cost'] / pos['buy_qty'] if pos['buy_qty'] > 0 else 0
            pos['quantity'] = net_qty
            
            # 获取当前市场价格 (最佳买价 bid)
            try:
                book = client.get_order_book(token_id)
                if book and book.bids and len(book.bids) > 0:
                    current_bid = float(book.bids[0].price)
                else:
                    current_bid = 0
            except:
                current_bid = 0
            
            # 计算目标卖出价格: 成本 + $0.01 (Polymarket 最小价格单位)
            target_sell_price = min(round(avg_cost + 0.01, 2), 0.99)
            
            # 安全检查
            if avg_cost <= 0:
                continue
            
            # 计算当前利润率
            profit_pct = (current_bid - avg_cost) / avg_cost if current_bid > 0 and avg_cost > 0 else 0
            
            # 计算持仓天数
            holding_days = 0
            if pos['first_buy_time']:
                try:
                    first_buy = datetime.fromisoformat(pos['first_buy_time'].replace('Z', '+00:00'))
                    holding_days = (datetime.now(first_buy.tzinfo) - first_buy).days
                except:
                    pass
            
            # 判断卖出类型
            sell_type = None
            reason = ""
            limit_price = target_sell_price  # 默认挂单价格
            is_stop_loss = False
            
            # ========== 止损条件 (最高优先级) ==========
            # 注意：如果市场流动性极差（bid < 0.05），不触发止损，等待市场结算
            min_bid_for_stop = 0.05  # 最低 bid 价格才考虑止损
            
            # 条件0: 固定止损 - 亏损超过 STOP_LOSS_PCT
            # 只有当 bid 价格合理时才止损，否则等待结算
            if current_bid >= min_bid_for_stop and profit_pct <= -STOP_LOSS_PCT:
                sell_type = 'STOP_LOSS'
                limit_price = round(current_bid - 0.01, 2)  # 略低于当前价确保成交
                reason = f"🛑 止损 ({profit_pct:.1%} <= -{STOP_LOSS_PCT:.0%})"
                is_stop_loss = True
            
            # 条件0.5: 时间止损 - 持仓超过 TIME_STOP_DAYS 天且无盈利
            elif holding_days >= TIME_STOP_DAYS and profit_pct <= 0 and current_bid >= min_bid_for_stop:
                sell_type = 'TIME_STOP'
                limit_price = round(current_bid - 0.01, 2)
                reason = f"⏰ 时间止损 ({holding_days}天, {profit_pct:.1%})"
                is_stop_loss = True
            
            # 条件0.6: 市场流动性极差 (bid < 0.05)
            elif current_bid < min_bid_for_stop:
                if holding_days >= 3 and avg_cost > 0.02:
                    # 持仓 >= 3天：以成本价挂限价卖单尝试退出
                    sell_type = 'ILLIQUID_EXIT'
                    limit_price = round(avg_cost, 2)
                    reason = f"💤 低流动性退出 ({holding_days}天, bid=${current_bid:.3f})"
                else:
                    # 持仓 < 3天：跳过，等待流动性恢复
                    continue
            
            # ========== 获利条件 ==========
            # 条件1: NO 持仓价格接近 1.0 (>= 0.98)，立即卖出锁定利润
            elif pos['outcome'] == 'No' and current_bid >= 0.98:
                sell_type = 'IMMEDIATE'
                limit_price = round(current_bid - 0.005, 3)  # 略低于当前价确保成交
                reason = f"NO 接近结算 (bid=${current_bid:.3f})"
            
            # 条件2: 当前 bid > 成本，有盈利就立即卖出
            elif current_bid > avg_cost and current_bid >= SELL_MIN_BID_PRICE:
                sell_type = 'IMMEDIATE'
                limit_price = round(current_bid - 0.005, 3)
                reason = f"有盈利立即卖 (+{profit_pct:.1%})"
            
            # 条件3: 挂单等待 - 当前 bid 不够，挂单在可达范围内
            elif avg_cost >= SELL_MIN_BID_PRICE and target_sell_price > avg_cost:
                sell_type = 'LIMIT_ORDER'
                # 取 cost+1¢ 和 bid+2¢ 的较小值，确保挂单价格在市场可达范围
                realistic_price = round(current_bid + 0.02, 2) if current_bid > 0 else target_sell_price
                limit_price = min(target_sell_price, realistic_price)
                limit_price = max(limit_price, 0.02)  # 安全下限
                reason = f"挂单等待 (目标${limit_price:.3f}, bid=${current_bid:.3f})"
            
            if sell_type:
                potential_profit = (limit_price - avg_cost) * pos['quantity']
                sell_opportunities.append({
                    'type': 'SELL',
                    'sell_type': sell_type,
                    'token_id': token_id,
                    'outcome': pos['outcome'],
                    'quantity': pos['quantity'],
                    'avg_cost': avg_cost,
                    'current_bid': current_bid,
                    'target_price': target_sell_price,
                    'limit_price': limit_price,
                    'potential_profit': potential_profit,
                    'profit_pct': profit_pct,
                    'reason': reason,
                    'is_stop_loss': is_stop_loss,
                    'holding_days': holding_days
                })
        
        # 按卖出类型排序：止损 > IMMEDIATE > LIMIT_ORDER，然后按利润排序
        type_priority = {'STOP_LOSS': 0, 'TIME_STOP': 0, 'IMMEDIATE': 1, 'LIMIT_ORDER': 2, 'ILLIQUID_EXIT': 3}
        sell_opportunities.sort(key=lambda x: (type_priority.get(x['sell_type'], 3), -x['potential_profit']))
        
    except Exception as e:
        print(f"❌ 分析持仓失败: {e}")
    
    return sell_opportunities


def execute_sell(client: ClobClient, opp: dict) -> Optional[dict]:
    """
    执行卖出操作 - 支持立即卖出和挂单两种模式
    """
    token_id = opp['token_id']
    quantity = opp['quantity']
    limit_price = opp['limit_price']
    sell_type = opp.get('sell_type', 'LIMIT_ORDER')
    
    # 确保价格有效
    sell_price = round(limit_price, 2)
    if sell_price <= 0.01:
        sell_price = 0.01
    if sell_price > 0.99:
        sell_price = 0.99
    
    size = int(quantity)  # 取整数
    if size < 1:
        return None
    
    try:
        order_args = OrderArgs(
            price=sell_price,
            size=float(size),
            side=SELL,
            token_id=token_id
        )
        
        mode_emoji = "🔴" if sell_type == 'IMMEDIATE' else "📋"
        if sell_type in ('STOP_LOSS', 'TIME_STOP'):
            mode_emoji = "🛑"
        mode_text = {
            'IMMEDIATE': '立即卖出',
            'LIMIT_ORDER': '挂单卖出',
            'STOP_LOSS': '止损卖出',
            'TIME_STOP': '时间止损'
        }.get(sell_type, '卖出')
        
        print(f"   {mode_emoji} [{mode_text}] {opp['outcome']} @ ${sell_price:.2f} x {size}")
        print(f"      成本: ${opp['avg_cost']:.3f} | 目标: ${opp['target_price']:.3f}")
        print(f"      当前bid: ${opp['current_bid']:.3f} | 挂单价: ${sell_price:.3f}")
        print(f"      预期利润: ${opp['potential_profit']:.4f} ({opp['reason']})")
        
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
        
        # 检查响应是否有错误
        if isinstance(resp, dict) and resp.get('error'):
            error_msg = resp.get('error', 'Unknown error')
            logger.error(f"订单被拒绝: {error_msg}")
            print(f"   ❌ 订单被拒绝: {error_msg}")
            return None
        
        logger.info(f"卖出订单成功: {sell_type} {opp['outcome']} @ ${sell_price:.2f} x {size}")
        
        return {
            'type': 'SELL',
            'sell_type': sell_type,
            'outcome': opp['outcome'],
            'quantity': size,
            'sell_price': sell_price,
            'avg_cost': opp['avg_cost'],
            'target_price': opp['target_price'],
            'potential_profit': opp['potential_profit'],
            'reason': opp['reason'],
            'order_id': resp.get('orderID', 'N/A'),
            'is_stop_loss': opp.get('is_stop_loss', False)
        }
    except Exception as e:
        error_str = str(e)
        logger.error(f"卖出失败: {error_str}")
        print(f"   ❌ 卖出失败: {error_str}")
        # 尝试解析更详细的错误信息
        if '400' in error_str:
            print(f"      💡 可能原因: 余额不足、价格无效、或持仓不足")
        return None


def format_positions_report(trades: List[dict]) -> str:
    """格式化持仓报告"""
    if not trades:
        return "📭 暂无交易记录"
    
    lines = ["📊 *最近交易记录*\n"]
    
    for i, t in enumerate(trades[:5], 1):
        side = t.get('side', 'N/A')
        outcome = t.get('outcome', 'N/A')
        size = t.get('size', '0')
        price = t.get('price', '0')
        status = t.get('status', 'N/A')
        
        emoji = "🟢" if side == "BUY" else "🔴"
        lines.append(f"{emoji} {side} {outcome} x{size} @${price} ({status})")
    
    return "\n".join(lines)


def find_fisher_opportunities(markets: List[dict], client: ClobClient) -> List[dict]:
    """
    钓鱼者策略：寻找价差大的市场进行双向挂单做市
    
    原理：
    - 很多市场的 Bid (买一) 和 Ask (卖一) 之间有巨大价差
    - 例如 Yes 买单 30¢，卖单 40¢，中间有 10¢ 真空带
    - 在中间价附近双向挂单，等待急躁的散户吃单
    """
    opportunities = []
    
    if not FISHER_ENABLED:
        return opportunities
    
    for market in markets:
        try:
            # 获取市场的 token_id
            tokens = market.get('tokens', [])
            if not tokens:
                continue
            
            yes_token = None
            no_token = None
            for token in tokens:
                if token.get('outcome') == 'Yes':
                    yes_token = token.get('token_id')
                elif token.get('outcome') == 'No':
                    no_token = token.get('token_id')
            
            if not yes_token:
                continue
            
            # 获取订单簿
            book = client.get_order_book(yes_token)
            if not book or not book.bids or not book.asks:
                continue
            
            best_bid = float(book.bids[0].price)
            best_ask = float(book.asks[0].price)
            spread = best_ask - best_bid
            
            # 价差必须足够大才值得做市
            if spread < FISHER_MIN_SPREAD:
                continue
            
            # 计算中间价和挂单价格
            mid_price = (best_bid + best_ask) / 2
            buy_price = round(mid_price - FISHER_EDGE_FROM_MID, 2)
            sell_price = round(mid_price + FISHER_EDGE_FROM_MID, 2)
            
            # 确保价格在合理范围
            if buy_price <= 0.01 or sell_price >= 0.99:
                continue
            
            # 预期利润 = 价差 - 2 * 偏移
            expected_profit = spread - 2 * FISHER_EDGE_FROM_MID
            
            opportunities.append({
                'type': 'FISHER',
                'question': market.get('question', '')[:50],
                'yes_token': yes_token,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spread': spread,
                'mid_price': mid_price,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'expected_profit': expected_profit
            })
            
        except Exception as e:
            continue
    
    # 按价差排序，优先做市价差大的市场
    opportunities.sort(key=lambda x: -x['spread'])
    return opportunities[:FISHER_MAX_TRADES]


def find_bargain_opportunities(markets: List[dict], client: ClobClient) -> List[dict]:
    """
    捡漏者策略：在市场价 -5% 位置挂买单，等待恐慌性抛售
    
    原理：
    - 无论 AI 怎么判断，永远在市场价的 -5% 位置挂一个 Buy Limit Order
    - 万一有人手滑市价砸盘，瞬间接到便宜货
    """
    opportunities = []
    
    if not BARGAIN_ENABLED:
        return opportunities
    
    for market in markets:
        try:
            # 检查交易量
            volume = float(market.get('volume', 0) or 0)
            if volume < BARGAIN_MIN_VOLUME:
                continue
            
            # 获取市场的 token_id
            tokens = market.get('tokens', [])
            if not tokens:
                continue
            
            # 优先捡漏 NO (因为我们的清洁工策略主要买 NO)
            target_token = None
            target_outcome = None
            token_data = None
            for token in tokens:
                if token.get('outcome') == 'No':
                    target_token = token.get('token_id')
                    target_outcome = 'No'
                    token_data = token
                    break
            
            if not target_token:
                for token in tokens:
                    if token.get('outcome') == 'Yes':
                        target_token = token.get('token_id')
                        target_outcome = 'Yes'
                        token_data = token
                        break
            
            if not target_token:
                continue
            
            # 使用 Gamma/CLOB 中间价（而非 best_ask=0.99）
            mid_price = float(token_data.get('price', 0)) if token_data else 0
            if mid_price <= 0.05 or mid_price >= 0.95:
                continue
            
            # 计算捡漏价格 (中间价 - 5%)
            bargain_price = round(mid_price * (1 - BARGAIN_DISCOUNT), 2)
            
            # 确保价格合理
            if bargain_price <= 0.01 or bargain_price >= 0.95:
                continue
            
            # 预期折扣
            discount_pct = (mid_price - bargain_price) / mid_price
            
            opportunities.append({
                'type': 'BARGAIN',
                'question': market.get('question', '')[:50],
                'token_id': target_token,
                'outcome': target_outcome,
                'mid_price': mid_price,
                'bargain_price': bargain_price,
                'discount_pct': discount_pct,
                'volume': volume
            })
            
        except Exception as e:
            continue
    
    # 按交易量排序，优先在热门市场捡漏
    opportunities.sort(key=lambda x: -x['volume'])
    return opportunities[:BARGAIN_MAX_TRADES]


def execute_fisher_trade(client: ClobClient, opp: dict) -> Optional[dict]:
    """执行钓鱼者做市交易 - 双向挂单"""
    try:
        yes_token = opp['yes_token']
        buy_price = opp['buy_price']
        sell_price = opp['sell_price']
        
        # 计算挂单数量
        buy_size = int(FISHER_BET_SIZE / buy_price)
        sell_size = int(FISHER_BET_SIZE / sell_price)
        
        if buy_size < 1 or sell_size < 1:
            return None
        
        print(f"   🎣 [钓鱼者] {opp['question']}...")
        print(f"      价差: {opp['spread']:.2%} (Bid ${opp['best_bid']:.2f} / Ask ${opp['best_ask']:.2f})")
        print(f"      挂单: 买 ${buy_price:.2f} x{buy_size} | 卖 ${sell_price:.2f} x{sell_size}")
        
        # 挂买单
        buy_order = OrderArgs(
            price=buy_price,
            size=float(buy_size),
            side=BUY,
            token_id=yes_token
        )
        signed_buy = client.create_order(buy_order)
        buy_resp = client.post_order(signed_buy, OrderType.GTC)
        
        # 挂卖单 (需要先有持仓才能卖，这里先跳过)
        # sell_order = OrderArgs(...)
        
        return {
            'type': 'FISHER',
            'question': opp['question'],
            'buy_price': buy_price,
            'sell_price': sell_price,
            'spread': opp['spread'],
            'expected_profit': opp['expected_profit'],
            'buy_order_id': buy_resp.get('orderID', 'N/A')
        }
        
    except Exception as e:
        print(f"   ❌ 钓鱼者交易失败: {e}")
        return None


def execute_bargain_trade(client: ClobClient, opp: dict) -> Optional[dict]:
    """执行捡漏者交易 - 低价挂单"""
    try:
        token_id = opp['token_id']
        bargain_price = opp['bargain_price']
        
        # 计算挂单数量
        size = int(BARGAIN_BET_SIZE / bargain_price)
        if size < 1:
            return None
        
        print(f"   💰 [捡漏者] {opp['question']}...")
        print(f"      中间价: ${opp.get('mid_price', 0):.2f} -> 挂单: ${bargain_price:.2f} (-{opp['discount_pct']:.1%})")
        print(f"      数量: x{size} ({opp['outcome']})")
        
        order_args = OrderArgs(
            price=bargain_price,
            size=float(size),
            side=BUY,
            token_id=token_id
        )
        
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
        
        return {
            'type': 'BARGAIN',
            'question': opp['question'],
            'outcome': opp['outcome'],
            'mid_price': opp.get('mid_price', 0),
            'bargain_price': bargain_price,
            'discount_pct': opp['discount_pct'],
            'size': size,
            'order_id': resp.get('orderID', 'N/A')
        }
        
    except Exception as e:
        print(f"   捡漏者交易失败: {e}")
        return None


def find_cleaner_opportunities(markets: List[dict], held_token_ids: set = None) -> List[dict]:
    """
    清洁工策略：寻找 NO 价格 >= 94% 的市场
    押注“永远不会发生的事”，如：
    - 外星人会在2025年前登陆地球吗？No
    - 比特币这周会涨到50万美元吗？No
    - 本周五前会爆发第三次世界大战吗？No
    """
    if held_token_ids is None:
        held_token_ids = set()
    opportunities = []
    
    for market in markets:
        # 排除已持仓市场
        clob_token_ids = market.get('clobTokenIds', '[]')
        token_ids = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
        if any(tid in held_token_ids for tid in token_ids):
            continue
        
        prices = get_market_prices(market)
        no_price = prices.get('No', 0)
        yes_price = prices.get('Yes', 1)
        
        # NO 价格 >= 94% 且 YES 价格较低（说明几乎不可能发生）
        if no_price >= CLEANER_MIN_NO_PRICE and yes_price <= 0.10:
            edge = 1.0 - no_price  # 预期收益率
            opportunities.append({
                'type': 'CLEANER',
                'market': market,
                'question': market.get('question', ''),
                'signal': 'BUY_NO',
                'no_price': no_price,
                'yes_price': yes_price,
                'edge': edge,
                'confidence': 'HIGH',  # 清洁工策略信心高
                'max_bet': CLEANER_MAX_BET
            })
    
    return opportunities


def find_harvester_opportunities(markets: List[dict], client: ClobClient, held_token_ids: set = None) -> List[dict]:
    """
    收割者策略：寻找 Yes + No < 1 的市场，同时买入双方，无风险套利
    
    核心逻辑：
    - 监控指标：Price(Yes) + Price(No)
    - 买入信号：总价 < $1.00
    - 操作动作：同时买入 Yes 和 No
    - 利润来源：市场结算时必定获得 $1，减去买入成本即为利润
    
    例如：Yes=$0.48, No=$0.50, 总价=$0.98
    买入 1 份 Yes + 1 份 No = $0.98
    结算时无论结果如何都获得 $1.00
    利润 = $1.00 - $0.98 = $0.02 (2美分)
    """
    if held_token_ids is None:
        held_token_ids = set()
    opportunities = []
    
    for market in markets:
        # 排除已持仓市场
        clob_token_ids = market.get('clobTokenIds', '[]')
        token_ids_raw = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
        if any(tid in held_token_ids for tid in token_ids_raw):
            continue
        
        prices = get_market_prices(market)
        yes_price = prices.get('Yes', 0)
        no_price = prices.get('No', 0)
        
        if yes_price <= 0 or no_price <= 0:
            continue
        
        total = yes_price + no_price
        
        # Yes + No < 阈值时存在套利机会
        if total < HARVESTER_THRESHOLD and total > 0.5:
            profit_per_unit = 1.0 - total  # 每单位利润
            
            # 计算预期利润
            bet_per_side = HARVESTER_BET_PER_SIDE
            units_yes = bet_per_side / yes_price
            units_no = bet_per_side / no_price
            min_units = min(units_yes, units_no)  # 取较小值保证两边数量一致
            
            total_cost = min_units * yes_price + min_units * no_price
            total_return = min_units * 1.0  # 结算时获得 $1/单位
            expected_profit = total_return - total_cost
            
            if expected_profit >= HARVESTER_MIN_PROFIT:
                opportunities.append({
                    'type': 'HARVESTER',
                    'market': market,
                    'question': market.get('question', ''),
                    'signal': 'HARVESTER',
                    'yes_price': yes_price,
                    'no_price': no_price,
                    'total': total,
                    'edge': profit_per_unit,
                    'units': min_units,
                    'expected_profit': expected_profit,
                    'confidence': 'HIGH'
                })
    
    # 按预期利润排序
    opportunities.sort(key=lambda x: -x['expected_profit'])
    return opportunities


def execute_harvester_trade(client: ClobClient, opp: dict) -> Optional[dict]:
    """
    执行收割者套利交易 - 同时买入 Yes 和 No
    """
    market = opp['market']
    yes_price = opp['yes_price']
    no_price = opp['no_price']
    units = opp['units']
    
    # 获取 token IDs
    clob_token_ids = market.get('clobTokenIds', '[]')
    if isinstance(clob_token_ids, str):
        token_ids = json.loads(clob_token_ids)
    else:
        token_ids = clob_token_ids
    
    if len(token_ids) < 2:
        print(f"   ⚠️ Token IDs 不足")
        return None
    
    yes_token = token_ids[0]
    no_token = token_ids[1]
    
    # 获取实际订单簿价格
    try:
        yes_book = client.get_order_book(yes_token)
        no_book = client.get_order_book(no_token)
        
        if yes_book and yes_book.asks and len(yes_book.asks) > 0:
            yes_exec_price = min(float(yes_book.asks[0].price), 0.99)
        else:
            yes_exec_price = min(yes_price, 0.99)
        
        if no_book and no_book.asks and len(no_book.asks) > 0:
            no_exec_price = min(float(no_book.asks[0].price), 0.99)
        else:
            no_exec_price = min(no_price, 0.99)
        
        # 重新检查套利条件
        actual_total = yes_exec_price + no_exec_price
        if actual_total >= 1.0:
            print(f"   ⚠️ 实际价格无套利空间: Yes={yes_exec_price:.3f} + No={no_exec_price:.3f} = {actual_total:.3f}")
            return None
        
        print(f"   📊 实际价格: Yes=${yes_exec_price:.3f} + No=${no_exec_price:.3f} = ${actual_total:.3f}")
        
    except Exception as e:
        print(f"   ⚠️ 获取订单簿失败: {e}")
        return None
    
    # 计算实际下单数量 (取整数)
    size = max(1, int(units))
    
    # 下单 Yes
    try:
        yes_order = OrderArgs(
            price=round(yes_exec_price, 2),
            size=float(size),
            side=BUY,
            token_id=yes_token
        )
        print(f"   🟢 BUY YES @ ${yes_exec_price:.2f} x {size}")
        yes_signed = client.create_order(yes_order)
        yes_resp = client.post_order(yes_signed, OrderType.GTC)
    except Exception as e:
        print(f"   ❌ YES 下单失败: {e}")
        return None
    
    # 下单 No
    try:
        no_order = OrderArgs(
            price=round(no_exec_price, 2),
            size=float(size),
            side=BUY,
            token_id=no_token
        )
        print(f"   🔴 BUY NO @ ${no_exec_price:.2f} x {size}")
        no_signed = client.create_order(no_order)
        no_resp = client.post_order(no_signed, OrderType.GTC)
    except Exception as e:
        print(f"   ❌ NO 下单失败: {e}")
        return None
    
    actual_profit = size * (1.0 - actual_total)
    print(f"   💰 预期利润: ${actual_profit:.4f}")
    
    # 记录两个 token 的冷却
    record_trade(yes_token)
    record_trade(no_token)
    
    return {
        'type': 'HARVESTER',
        'question': opp['question'][:40],
        'signal': 'HARVESTER',
        'yes_price': yes_exec_price,
        'no_price': no_exec_price,
        'size': size,
        'total_cost': size * actual_total,
        'expected_profit': actual_profit,
        'edge': 1.0 - actual_total
    }


def cancel_stale_orders(client: ClobClient, max_age_hours: float = 2.0) -> int:
    """
    P5: 订单生命周期管理 — 取消超时未成交的挂单
    避免资金被锁在无效挂单中，也防止同一市场重复挂单
    """
    cancelled = 0
    try:
        orders = client.get_orders()
        if not orders or not isinstance(orders, list):
            return 0
        
        now = datetime.now(timezone.utc)
        active_orders = [o for o in orders if isinstance(o, dict) and o.get('status') == 'live']
        
        if not active_orders:
            return 0
        
        print(f"   📋 当前活跃挂单: {len(active_orders)} 个")
        
        for order in active_orders:
            order_id = order.get('id', '')
            created = order.get('created_at', '')
            
            if not created or not order_id:
                continue
            
            try:
                order_time = datetime.fromisoformat(created.replace('Z', '+00:00'))
                age_hours = (now - order_time).total_seconds() / 3600
                
                if age_hours >= max_age_hours:
                    client.cancel(order_id)
                    cancelled += 1
                    price = order.get('price', '?')
                    side = order.get('side', '?')
                    print(f"   🗑️ 取消过期挂单: {side} @${price} (挂单{age_hours:.1f}h)")
            except Exception:
                continue
        
    except Exception as e:
        logger.warning(f"取消过期挂单失败: {e}")
    
    return cancelled


# ============== Trading Scout + Market Matcher ==============
_news_url_cache = set()  # 跨周期 URL 去重缓存

def trading_scout() -> List[Dict]:
    """
    轻量级新闻扫描 — 用 Brave Search API 搜索 Polymarket 相关新闻。
    不写文件，不碰 BettaFish pipeline。
    返回: [{title, content, url, keyword}]
    """
    if not NEWS_ENABLED:
        return []
    
    brave_key = getattr(config, 'BRAVE_API_KEY', '') or os.environ.get('BRAVE_API_KEY', '')
    if not brave_key:
        print("   ⚠️ BRAVE_API_KEY 未配置，跳过新闻扫描")
        return []
    
    all_items = []
    headers = {"Accept": "application/json", "X-Subscription-Token": brave_key}
    
    for kw in NEWS_KEYWORDS:
        try:
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params={"q": kw, "count": 3, "freshness": NEWS_FRESHNESS},
                timeout=8
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for r in data.get("web", {}).get("results", [])[:3]:
                url = r.get("url", "")
                if url in _news_url_cache:
                    continue
                _news_url_cache.add(url)
                all_items.append({
                    "title": r.get("title", ""),
                    "content": (r.get("description", ""))[:300],
                    "url": url,
                    "keyword": kw,
                })
        except Exception as e:
            logger.debug(f"Brave search '{kw}' failed: {e}")
    
    # 限制缓存大小
    if len(_news_url_cache) > 500:
        _news_url_cache.clear()
    
    return all_items


def match_news_to_markets(news_items: List[Dict], markets: List[Dict]) -> List[Dict]:
    """
    用 Gemini 一次性匹配新闻与市场，返回交易信号。
    输入: top-10 新闻 + top-30 竞争性市场
    输出: [{market_idx, signal: BUY_YES/BUY_NO, confidence: 1-10, reason}]
    """
    if not news_items or not markets:
        return []
    
    gemini_key = getattr(config, 'GEMINI_API_KEY', '')
    if not gemini_key:
        return []
    
    from google import genai
    from google.genai import types
    
    # 构建新闻摘要
    news_text = ""
    for i, n in enumerate(news_items[:10]):
        news_text += f"[N{i}] {n['title']}\n    {n['content']}\n"
    
    # 构建市场列表 (只选竞争性 15-85%)
    market_text = ""
    market_list = []
    for m in markets:
        if len(market_list) >= 30:
            break
        prices = get_market_prices(m)
        yes_price = prices.get('Yes', 0.5)
        if 0.15 < yes_price < 0.85:
            idx = len(market_list)
            q = m.get('question', '')[:80]
            market_text += f"[M{idx}] {q} (Yes={yes_price:.0%})\n"
            market_list.append(m)
    
    if not market_list:
        return []
    
    prompt = f"""You are a prediction market analyst. Given recent news and active prediction markets, identify if any news directly impacts any market's outcome probability.

NEWS (last 24h):
{news_text}

PREDICTION MARKETS:
{market_text}

TASK: For each news-market pair where news DIRECTLY and CLEARLY impacts the market outcome, output a JSON array:
[{{"news_idx": 0, "market_idx": 0, "signal": "BUY_YES", "confidence": 8, "reason": "brief reason"}}]

Rules:
- signal must be "BUY_YES" or "BUY_NO"
- confidence: 1-10 (only include if >= {NEWS_MIN_CONFIDENCE})
- Only include CLEAR, DIRECT causal links. Do NOT force matches.
- If no news impacts any market, return empty array: []
- Return ONLY valid JSON, no other text."""
    
    try:
        gclient = genai.Client(api_key=gemini_key)
        response = gclient.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2000)
        )
        
        text = response.text.strip()
        # 清理 markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3].strip()
        
        signals = json.loads(text)
        if not isinstance(signals, list):
            return []
        
        # 过滤并关联回 market 对象，同一市场只保留 confidence 最高的信号
        best_by_market = {}  # market_idx -> best signal
        for s in signals:
            midx = s.get('market_idx', -1)
            conf = s.get('confidence', 0)
            sig = s.get('signal', '')
            if midx < 0 or midx >= len(market_list):
                continue
            if conf < NEWS_MIN_CONFIDENCE:
                continue
            if sig not in ('BUY_YES', 'BUY_NO'):
                continue
            if midx not in best_by_market or conf > best_by_market[midx]['confidence_score']:
                best_by_market[midx] = {
                    'market': market_list[midx],
                    'signal': sig,
                    'confidence_score': conf,
                    'reason': s.get('reason', ''),
                    'news_title': news_items[s.get('news_idx', 0)]['title'][:60] if s.get('news_idx', 0) < len(news_items) else '',
                }
        result = sorted(best_by_market.values(), key=lambda x: -x['confidence_score'])
        return result
    
    except Exception as e:
        logger.warning(f"Market Matcher 失败: {e}")
        return []


def run_trading_cycle(client: ClobClient) -> dict:
    """
    运行一个交易周期 - 策略优先级：卖出/止损 > AI信号(主力) > 新闻驱动 > 清洁工 > 捡漏
    
    资金管理：
    - 总仓位上限 $160 (80%)
    - 单票最大 $30
    - 最小可用余额 $20
    - 每周期最多 5 笔交易
    """
    result = {
        'timestamp': datetime.now().isoformat(),
        'markets_scanned': 0,
        'opportunities_found': 0,
        'trades_executed': 0,
        'trades': [],
        'harvester_opps': 0,
        'cleaner_opps': 0,
        'ai_opps': 0,
        'news_opps': 0,
        'total_profit': 0.0,
        'position_info': None,
        'can_open_new': True,
        'skip_reason': ''
    }
    
    # ============== 0. 检查当前持仓和余额 ==============
    print("💰 检查账户状态...")
    pos_info = get_current_positions(client)
    result['position_info'] = pos_info
    
    print(f"   📊 当前持仓: {pos_info['position_count']} 个")
    print(f"   💵 持仓成本: ${pos_info['total_cost']:.2f}")
    print(f"   💰 可用余额: ${pos_info['available_balance']:.2f}")
    
    # 判断是否可以开新仓
    can_open_new = True
    skip_reason = ""
    
    if pos_info['available_balance'] < MIN_AVAILABLE_BALANCE:
        can_open_new = False
        skip_reason = f"余额不足 (${pos_info['available_balance']:.2f} < ${MIN_AVAILABLE_BALANCE})"
        print(f"   ⚠️ {skip_reason}")
        send_telegram_message(f"⚠️ 余额不足警告\n可用: ${pos_info['available_balance']:.2f}\n最低要求: ${MIN_AVAILABLE_BALANCE}")
    elif pos_info['total_cost'] >= MAX_TOTAL_POSITION:
        can_open_new = False
        skip_reason = f"总仓位已满 (${pos_info['total_cost']:.2f} >= ${MAX_TOTAL_POSITION})"
        print(f"   ⚠️ {skip_reason}")
    elif pos_info['position_count'] >= MAX_POSITION_COUNT:
        can_open_new = False
        skip_reason = f"持仓数量已满 ({pos_info['position_count']} >= {MAX_POSITION_COUNT})"
        print(f"   ⚠️ {skip_reason}")
    else:
        print(f"   ✅ 可以开新仓")
    
    result['can_open_new'] = can_open_new
    result['skip_reason'] = skip_reason
    
    # 构建已持仓 token_id 集合，用于排除重复买入
    held_token_ids = set()
    for pos in pos_info.get('positions', []):
        if pos.get('token_id'):
            held_token_ids.add(pos['token_id'])
    if held_token_ids:
        print(f"   📌 已持仓 {len(held_token_ids)} 个 token，将跳过重复买入")
    
    # 1. CLOB-First 全量扫描 + Gamma 热门补充
    print("\n📡 CLOB-First 市场扫描...")
    
    # 主力: CLOB API 全量扫描 (3100+ 市场，自带中间价)
    clob_markets = fetch_clob_markets(client, max_pages=3, sports_filter=True)
    
    # 补充: Gamma API 热门市场 (带 volume/liquidity 元数据)
    gamma_markets = fetch_all_sorted_markets(limit_per_sort=30)
    gamma_filtered = filter_markets(gamma_markets)
    
    # 合并去重：CLOB 优先，Gamma 补充
    seen_ids = set()
    markets = []
    for m in clob_markets:
        mid = m.get('id') or m.get('conditionId', '')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            markets.append(m)
    for m in gamma_filtered:
        mid = m.get('id') or m.get('conditionId', '')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            markets.append(m)
    
    # 统计各来源数量
    source_counts = {}
    for m in markets:
        src = m.get('_source', 'unknown')
        source_counts[src] = source_counts.get(src, 0) + 1
    
    print("   📊 各来源市场数量:")
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        emoji = {
            'clob': '🔗',
            'breaking-news': '🔥',
            'newest': '🆕', 
            '24h-volume': '📈',
            'liquidity': '💧',
            'ending-soon': '⏰',
            'competitive': '⚔️'
        }.get(src, '📌')
        print(f"      {emoji} {src}: {count} 个")
    
    result['markets_scanned'] = len(markets)
    print(f"   ✅ 总计: {len(markets)} 个活跃市场")
    
    if not markets:
        return result
    
    # ============== 1.3 清理过期挂单 ==============
    print("\n🗑️ 检查过期挂单...")
    cancelled = cancel_stale_orders(client, max_age_hours=2.0)
    if cancelled > 0:
        print(f"   ✅ 已取消 {cancelled} 个过期挂单")
    else:
        print("   ✅ 无过期挂单")
    
    # ============== 1.5 优先处理卖出/止损 ==============
    print("\n📈 持仓扫描 (检测卖出/止损机会)...")
    sell_opps = analyze_positions_for_sell(client)
    result['sell_opps'] = len(sell_opps)
    
    # 分类统计
    stop_loss_opps = [o for o in sell_opps if o.get('is_stop_loss')]
    profit_opps = [o for o in sell_opps if not o.get('is_stop_loss')]
    
    if stop_loss_opps:
        print(f"   🛑 发现 {len(stop_loss_opps)} 个止损机会:")
        for opp in stop_loss_opps[:5]:
            print(f"      • {opp['outcome']} x{opp['quantity']:.0f} @ ${opp['avg_cost']:.3f}")
            print(f"        当前: ${opp['current_bid']:.3f} ({opp['profit_pct']:.1%})")
            print(f"        {opp['reason']}")
    
    if profit_opps:
        print(f"   💰 发现 {len(profit_opps)} 个获利/挂单机会")
    
    # 执行卖出（止损优先，卖出不占用买入配额）
    sell_trades_count = 0
    if sell_opps and not DRY_RUN:
        print("\n   💰 执行卖出...")
        for opp in sell_opps[:5]:  # 最多卖出 5 笔
            try:
                trade_result = execute_sell(client, opp)
                if trade_result:
                    result['trades'].append(trade_result)
                    result['total_profit'] += trade_result.get('potential_profit', 0)
                    sell_trades_count += 1
            except Exception as e:
                print(f"   ❌ 卖出失败: {e}")
        print(f"   ✅ 卖出完成: {sell_trades_count} 笔")
    
    # ============== 2. AI 信号策略 (主力) ==============
    # 只有在可以开新仓时才执行买入策略
    if not can_open_new:
        print(f"\n⏸️ 跳过买入策略: {skip_reason}")
    else:
        print("\n🧠 AI 信号策略扫描 (主力 - Gemini 分析竞争性市场)...")
        ai_trades = 0
        # 从全量市场中筛选: competitive(30-70%)、未持仓、非体育
        ai_candidates = []
        for m in markets:
            if len(ai_candidates) >= AI_MAX_MARKETS:
                break
            clob_ids_raw = m.get('clobTokenIds', '[]')
            t_ids = json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
            if any(tid in held_token_ids for tid in t_ids):
                continue
            # 检查冷却
            if any(tid in _traded_markets for tid in t_ids):
                continue
            # 竞争性市场: Yes 在 15%-85% 范围
            prices = get_market_prices(m)
            yes_price = prices.get('Yes', 0.5)
            if yes_price < 0.15 or yes_price > 0.85:
                continue
            # 优先选24h交易量大的（Gamma市场有此字段）
            vol_24h = float(m.get('volume24hr', 0) or 0)
            ai_candidates.append((vol_24h, m))
        
        # 排序：有volume数据的优先，然后随机打散无volume的
        ai_candidates.sort(key=lambda x: -x[0])
        ai_candidates = [m for _, m in ai_candidates[:AI_MAX_MARKETS]]
        
        result['ai_opps'] = 0
        print(f"   📊 AI 候选市场: {len(ai_candidates)} 个 (竞争性 15-85%)")
        
        for m in ai_candidates:
            if result['trades_executed'] >= MAX_TRADES_PER_CYCLE:
                break
            try:
                question = m.get('question', '')
                description = m.get('description', '')
                prices = get_market_prices(m)
                yes_price = prices.get('Yes', 0.5)
                
                analysis = analyze_market_with_gemini(question, description, yes_price)
                if not analysis or analysis.get('signal') == 'HOLD':
                    continue
                
                edge = analysis.get('edge', 0)
                if edge < AI_MIN_EDGE:
                    continue
                
                result['ai_opps'] += 1
                signal = analysis['signal']
                confidence = analysis.get('confidence_level', 'MEDIUM')
                print(f"   🎯 AI 发现机会: {question[:40]}...")
                print(f"      信号: {signal} | Edge: {edge:.1%} | 信心: {confidence}")
                
                if not DRY_RUN:
                    opp = {
                        'type': 'AI_SIGNAL',
                        'market': m,
                        'question': question,
                        'signal': signal,
                        'no_price': 1.0 - yes_price,
                        'yes_price': yes_price,
                        'market_price': yes_price,
                        'edge': edge,
                        'confidence': confidence,
                        'max_bet': AI_MAX_BET
                    }
                    trade_result = execute_trade(client, opp)
                    if trade_result:
                        result['trades'].append(trade_result)
                        result['trades_executed'] += 1
                        ai_trades += 1
                        record_trade(trade_result.get('token_id', ''))
            except Exception as e:
                logger.warning(f"AI 分析失败: {e}")
            
            import time as _time
            _time.sleep(1)  # 避免 Gemini API 限流
        
        if ai_trades > 0:
            print(f"   ✅ AI 信号交易完成: {ai_trades} 笔")
        else:
            print(f"   ⏸️ AI 信号无交易机会 (发现 {result['ai_opps']} 个信号)")
        
        # ============== 2.5 新闻驱动信号 (Trading Scout) ==============
        if NEWS_ENABLED and result['trades_executed'] < MAX_TRADES_PER_CYCLE:
            print("\n📰 新闻驱动策略 (Trading Scout + Market Matcher)...")
            try:
                news_items = trading_scout()
                print(f"   📡 扫描到 {len(news_items)} 条新闻")
                
                if news_items:
                    news_signals = match_news_to_markets(news_items, markets)
                    result['news_opps'] = len(news_signals)
                    
                    if news_signals:
                        print(f"   🎯 发现 {len(news_signals)} 个新闻驱动信号:")
                        for ns in news_signals[:5]:
                            q = ns['market'].get('question', '')[:40]
                            print(f"      • {q}...")
                            print(f"        {ns['signal']} 置信度:{ns['confidence_score']}/10 | {ns['reason'][:50]}")
                            print(f"        📰 {ns['news_title']}")
                    
                    news_trades = 0
                    for ns in news_signals[:NEWS_MAX_TRADES]:
                        if result['trades_executed'] >= MAX_TRADES_PER_CYCLE:
                            break
                        # 去重：跳过已持仓的市场
                        m = ns['market']
                        clob_ids_raw = m.get('clobTokenIds', '[]')
                        t_ids = json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
                        if any(tid in held_token_ids for tid in t_ids):
                            continue
                        if any(tid in _traded_markets for tid in t_ids):
                            continue
                        
                        prices = get_market_prices(m)
                        yes_price = prices.get('Yes', 0.5)
                        conf_map = {10: 'HIGH', 9: 'HIGH', 8: 'HIGH', 7: 'MEDIUM'}
                        opp = {
                            'type': 'NEWS_SIGNAL',
                            'market': m,
                            'question': m.get('question', ''),
                            'signal': ns['signal'],
                            'yes_price': yes_price,
                            'no_price': 1.0 - yes_price,
                            'market_price': yes_price,
                            'edge': ns['confidence_score'] / 10.0,
                            'confidence': conf_map.get(ns['confidence_score'], 'MEDIUM'),
                            'max_bet': NEWS_MAX_BET,
                        }
                        try:
                            trade_result = execute_trade(client, opp)
                            if trade_result:
                                result['trades'].append(trade_result)
                                result['trades_executed'] += 1
                                news_trades += 1
                                record_trade(trade_result.get('token_id', ''))
                        except Exception as e:
                            print(f"   ❌ 新闻交易失败: {e}")
                    
                    if news_trades > 0:
                        print(f"   ✅ 新闻驱动交易完成: {news_trades} 笔")
                    else:
                        print(f"   ⏸️ 新闻驱动无交易 (发现 {result['news_opps']} 个信号)")
                else:
                    print("   ⏸️ 无新鲜新闻")
            except Exception as e:
                logger.warning(f"新闻驱动策略失败: {e}")
                print(f"   ❌ 新闻驱动策略异常: {e}")
        
        # ============== 3. 清洁工策略 ==============
        print("\n🧹 清洁工策略扫描 (NO >= 94%)...")
        cleaner_opps = find_cleaner_opportunities(markets, held_token_ids)
        result['cleaner_opps'] = len(cleaner_opps)
        
        if cleaner_opps:
            print(f"   发现 {len(cleaner_opps)} 个清洁工机会:")
            for opp in cleaner_opps[:3]:
                print(f"      • {opp['question'][:40]}... NO@{opp['no_price']:.2f}")
        
        # ============== 4. 执行清洁工交易 ==============
        if cleaner_opps and not DRY_RUN and result['trades_executed'] < MAX_TRADES_PER_CYCLE:
            print("\n   💰 执行清洁工交易...")
            cleaner_trades = 0
            for opp in cleaner_opps[:CLEANER_MAX_TRADES]:
                if result['trades_executed'] >= MAX_TRADES_PER_CYCLE:
                    print(f"   ⏸️ 达到每周期交易上限 ({MAX_TRADES_PER_CYCLE})")
                    break
                try:
                    trade_result = execute_trade(client, opp)
                    if trade_result:
                        result['trades'].append(trade_result)
                        result['trades_executed'] += 1
                        # 清洁工预期利润 = (1 - 买入价) * 数量
                        expected_profit = (1.0 - trade_result.get('price', 0)) * trade_result.get('size', 0)
                        result['total_profit'] += expected_profit
                        cleaner_trades += 1
                except Exception as e:
                    print(f"   ❌ 交易失败: {e}")
            print(f"   ✅ 清洁工交易完成: {cleaner_trades} 笔")
    
    # ============== 5. 钓鱼者策略 (做市) ==============
    if FISHER_ENABLED:
        print("\n🎣 钓鱼者策略扫描 (价差做市)...")
        fisher_opps = find_fisher_opportunities(markets, client)
        result['fisher_opps'] = len(fisher_opps)
        
        if fisher_opps:
            print(f"   🎯 发现 {len(fisher_opps)} 个做市机会:")
            for opp in fisher_opps[:3]:
                print(f"      • {opp['question'][:35]}...")
                print(f"        价差: {opp['spread']:.2%} (Bid ${opp['best_bid']:.2f} / Ask ${opp['best_ask']:.2f})")
            
            # 执行钓鱼者交易
            if not DRY_RUN:
                print("\n   💰 执行钓鱼者挂单...")
                fisher_trades = 0
                for opp in fisher_opps[:FISHER_MAX_TRADES]:
                    try:
                        trade_result = execute_fisher_trade(client, opp)
                        if trade_result:
                            result['trades'].append(trade_result)
                            result['trades_executed'] += 1
                            fisher_trades += 1
                    except Exception as e:
                        print(f"   ❌ 钓鱼者交易失败: {e}")
                print(f"   ✅ 钓鱼者挂单完成: {fisher_trades} 笔")
        else:
            print("   ⏸️ 暂无做市机会 (价差不足)")
    
    # ============== 6. 捡漏者策略 (低价挂单) ==============
    if BARGAIN_ENABLED:
        print("\n💰 捡漏者策略扫描 (低价挂单)...")
        bargain_opps = find_bargain_opportunities(markets, client)
        result['bargain_opps'] = len(bargain_opps)
        
        if bargain_opps:
            print(f"   🎯 发现 {len(bargain_opps)} 个捡漏机会:")
            for opp in bargain_opps[:3]:
                print(f"      • {opp['question'][:35]}...")
                print(f"        当前: ${opp['best_ask']:.2f} -> 挂单: ${opp['bargain_price']:.2f} (-{opp['discount_pct']:.1%})")
            
            # 执行捡漏者交易
            if not DRY_RUN:
                print("\n   💰 执行捡漏者挂单...")
                bargain_trades = 0
                for opp in bargain_opps[:BARGAIN_MAX_TRADES]:
                    try:
                        trade_result = execute_bargain_trade(client, opp)
                        if trade_result:
                            result['trades'].append(trade_result)
                            result['trades_executed'] += 1
                            bargain_trades += 1
                    except Exception as e:
                        print(f"   ❌ 捡漏者交易失败: {e}")
                print(f"   ✅ 捡漏者挂单完成: {bargain_trades} 笔")
        else:
            print("   ⏸️ 暂无捡漏机会")
    
    # ============== 7. 统计总机会 ==============
    result['opportunities_found'] = (
        result['harvester_opps'] + 
        result['cleaner_opps'] + 
        result.get('ai_opps', 0) +
        result.get('fisher_opps', 0) + 
        result.get('bargain_opps', 0) + 
        result.get('sell_opps', 0)
    )
    
    print(f"\n{'='*50}")
    print(f"📊 本轮统计:")
    print(f"   🌾 收割者机会: {result['harvester_opps']} 个")
    print(f"   🧹 清洁工机会: {result['cleaner_opps']} 个")
    print(f"   🧠 AI信号机会: {result.get('ai_opps', 0)} 个")
    print(f"   📰 新闻驱动机会: {result.get('news_opps', 0)} 个")
    print(f"   🎣 钓鱼者机会: {result.get('fisher_opps', 0)} 个")
    print(f"   💰 捡漏者机会: {result.get('bargain_opps', 0)} 个")
    print(f"   📈 卖出机会: {result.get('sell_opps', 0)} 个")
    print(f"   💰 买入交易: {result['trades_executed']} 笔 | 卖出: {sell_trades_count} 笔")
    print(f"   💵 预期利润: ${result['total_profit']:.4f}")
    print(f"{'='*50}")
    
    return result


def execute_trade(client: ClobClient, opp: dict) -> Optional[dict]:
    """执行单笔交易 - 支持清洁工、套利、AI信号三种策略"""
    market = opp['market']
    signal = opp['signal']
    edge = opp['edge']
    confidence = opp['confidence']
    trade_type = opp.get('type', 'AI_SIGNAL')
    max_bet = opp.get('max_bet', AI_MAX_BET)
    
    # 根据策略类型和信心计算仓位
    multiplier = {'HIGH': 1.0, 'MEDIUM': 0.6, 'LOW': 0.3}.get(confidence, 0.5)
    position = min(max_bet * multiplier, max_bet)
    
    # 获取 token IDs
    clob_token_ids = market.get('clobTokenIds', '[]')
    token_ids = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
    
    # 根据信号类型确定 token 和价格
    if signal == 'BUY_YES' and len(token_ids) > 0:
        token_id = token_ids[0]
        price = opp.get('market_price', opp.get('yes_price', 0.5))
    elif signal == 'BUY_NO' and len(token_ids) > 1:
        token_id = token_ids[1]
        price = opp.get('no_price', 1.0 - opp.get('market_price', 0.5))
    elif signal == 'ARBITRAGE':
        # 套利策略：同时买入 Yes 和 No (这里简化为只买 Yes，实际应该两边都买)
        # TODO: 实现完整套利逻辑
        print(f"   ⚠️ 套利策略暂未完全实现，跳过")
        return None
    else:
        return None
    
    if price <= 0 or price >= 1:
        return None
    
    # 使用中间价+偏移作为限价单价格（而非 best_ask）
    # Polymarket 订单簿在中间价位通常无挂单（bid=0.01, ask=0.99），
    # 用 best_ask 下单 = 以 $0.99 买任何东西，是灾难性的。
    # 正确做法：以中间价附近挂限价单(GTC)等待成交。
    LIMIT_PRICE_OFFSET = 0.02  # 在中间价基础上加 2¢ 提高成交率
    mid_price = price  # price 已经是 Gamma/CLOB 的中间价
    execution_price = min(round(mid_price + LIMIT_PRICE_OFFSET, 2), 0.95)
    # 安全下限：执行价不能低于 0.02
    execution_price = max(execution_price, 0.02)
    print(f"   📊 [{trade_type}] 中间价: ${mid_price:.3f}, 限价单: ${execution_price:.2f} (mid+{LIMIT_PRICE_OFFSET})")
    
    # 重新计算数量 - 精度限制：价格2位，数量取整数
    size = int(position / execution_price)
    if size < 1:
        size = 1
    
    # 创建订单
    order_args = OrderArgs(
        price=execution_price,
        size=float(size),
        side=BUY,
        token_id=token_id
    )
    
    emoji = {'CLEANER': '🧹', 'ARBITRAGE': '💰', 'AI_SIGNAL': '🧠', 'NEWS_SIGNAL': '📰'}.get(trade_type, '📤')
    print(f"   {emoji} [{trade_type}] {signal} @ ${execution_price:.2f} x {size}")
    
    signed_order = client.create_order(order_args)
    resp = client.post_order(signed_order, OrderType.GTC)
    
    # 记录交易到冷却文件
    record_trade(token_id)
    
    return {
        'type': trade_type,
        'question': opp['question'][:40],
        'signal': signal,
        'price': execution_price,
        'size': size,
        'amount': position,
        'edge': edge,
        'token_id': token_id,
        'order_id': resp.get('orderID', 'N/A')
    }


def format_cycle_report(result: dict, positions: List[dict], portfolio: dict = None) -> str:
    """格式化周期报告 - 简明版"""
    lines = [
        f"🌾 Polymarket {datetime.now().strftime('%m-%d %H:%M')}",
        f"扫描 {result['markets_scanned']} | 交易 {result['trades_executed']} | 利润 ${result.get('total_profit', 0):.4f}",
    ]

    # 只列出有机会的策略（一行汇总）
    opp_parts = []
    for key, emoji in [('harvester_opps', '🌾'), ('cleaner_opps', '🧹'), ('ai_opps', '🧠'),
                        ('news_opps', '📰'), ('fisher_opps', '🎣'), ('bargain_opps', '💰'), ('sell_opps', '📈')]:
        val = result.get(key, 0)
        if val > 0:
            opp_parts.append(f"{emoji}{val}")
    if opp_parts:
        lines.append("机会: " + " ".join(opp_parts))

    # 交易详情（每笔一行）
    if result['trades']:
        for t in result['trades']:
            tt = t.get('type', '?')
            emoji = {'HARVESTER': '🌾', 'CLEANER': '🧹', 'AI_SIGNAL': '🧠',
                     'FISHER': '🎣', 'BARGAIN': '💰', 'SELL': '🔴'}.get(tt, '📤')
            q = t.get('question', t.get('outcome', ''))[:25]
            profit = t.get('expected_profit', t.get('potential_profit', t.get('amount', 0)))
            lines.append(f"{emoji} {q} ${profit:.4f}")

    # 投资组合（简明）
    if portfolio:
        lines.append(format_portfolio_report(portfolio))

    return "\n".join(lines)


def main():
    """主函数"""
    print("\n" + "="*50)
    print(f"🚀 Polymarket 定时交易 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # 初始化
    client = init_client()
    
    # 运行交易周期
    result = run_trading_cycle(client)
    
    # 获取持仓和投资组合分析
    positions = get_positions(client)
    portfolio = analyze_portfolio(client)
    
    # 生成报告 (包含投资组合分析)
    report = format_cycle_report(result, positions, portfolio)
    print("\n" + report)
    
    # 发送 Telegram 通知
    send_telegram_message(report)
    
    print("\n✅ 周期完成")


if __name__ == "__main__":
    main()
