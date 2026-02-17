"""
Polymarket 自动化交易引擎
整合多策略 + AI 分析 + 实时搜索
"""

import os
import json
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

import config
from strategies import (
    StrategyType, StrategyManager, 
    HARVESTER_CONFIG, CLEANER_CONFIG, LEARNER_CONFIG, SELF_SUSTAIN_CONFIG
)
from ai_brain_gemini import analyze_market_with_gemini, search_news
from market_scanner import fetch_active_markets, filter_markets, get_market_prices

# ================= 配置区 =================
PROXY_WALLET = "0xdC32539E1B60e77de554fEc4347fC04d980Fa523"

# 运行模式
DRY_RUN = False          # 实盘模式 (False=实际下单)
LOG_FILE = "/Users/tangheng/HenryBot/trading_log.json"

# 扫描参数
SCAN_INTERVAL = 300      # 扫描间隔 (秒)
MAX_MARKETS_PER_SCAN = 20

# ⚠️ 风控参数 (实盘安全限制)
MAX_SINGLE_BET = 5.0     # 单笔最大下注 $5
MAX_DAILY_LOSS = 20.0    # 每日最大亏损 $20
MIN_EDGE_THRESHOLD = 0.10 # 最小优势阈值 10%
# =========================================


class TradingEngine:
    """自动化交易引擎"""
    
    def __init__(self, strategy_type: StrategyType = StrategyType.LEARNER, dry_run: bool = True):
        self.dry_run = dry_run
        self.strategy_manager = StrategyManager()
        self.strategy_manager.set_strategy(strategy_type)
        self.client = self.strategy_manager.client
        
        self.trade_log = []
        self.total_pnl = 0.0
        self.session_start = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"🚀 Polymarket 自动化交易引擎")
        print(f"{'='*60}")
        print(f"   策略: {self.strategy_manager.strategies[strategy_type].config.name}")
        print(f"   模式: {'模拟' if dry_run else '实盘'}")
        print(f"   代理钱包: {PROXY_WALLET[:10]}...{PROXY_WALLET[-6:]}")
        print(f"{'='*60}\n")
    
    def get_balance(self) -> float:
        """获取余额"""
        try:
            # 简化：假设余额 100 USDC
            # 实际应该调用 API 获取
            return 100.0
        except Exception as e:
            print(f"⚠️ 获取余额失败: {e}")
            return 0.0
    
    def scan_markets(self) -> List[dict]:
        """扫描市场 - 使用 Gamma API 获取真正活跃的市场"""
        print("📡 扫描市场 (Gamma API)...")
        
        try:
            # 使用新的市场扫描器
            raw_markets = fetch_active_markets(limit=200)
            print(f"   原始数据: {len(raw_markets)} 个市场")
            
            # 应用新鲜度过滤器
            markets = filter_markets(raw_markets)
            print(f"   过滤后: {len(markets)} 个活跃市场")
            
            return markets[:MAX_MARKETS_PER_SCAN]
            
        except Exception as e:
            print(f"⚠️ 扫描失败: {e}")
            return []
    
    def find_harvester_opportunities(self, markets: List[dict]) -> List[dict]:
        """
        策略一：收割者 - 寻找微套利机会
        条件：Yes + No < $1.00
        """
        opportunities = []
        
        for market in markets:
            # 使用 Gamma API 的价格格式
            prices = get_market_prices(market)
            yes_price = prices.get('Yes', 0.5)
            no_price = prices.get('No', 0.5)
            
            total = yes_price + no_price
            
            if total < 0.98 and total > 0:  # 套利空间
                edge = 1.0 - total
                
                # 获取 token IDs
                clob_token_ids = market.get('clobTokenIds', '[]')
                try:
                    import json
                    token_ids = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
                except:
                    token_ids = []
                
                opportunities.append({
                    'type': 'ARBITRAGE',
                    'market': market,
                    'question': market.get('question', ''),
                    'yes_token': token_ids[0] if len(token_ids) > 0 else None,
                    'no_token': token_ids[1] if len(token_ids) > 1 else None,
                    'yes_price': yes_price,
                    'no_price': no_price,
                    'edge': edge
                })
        
        return opportunities
    
    def find_cleaner_opportunities(self, markets: List[dict]) -> List[dict]:
        """
        策略二：清洁工 - 寻找高确定性 No 机会
        条件：No 价格在 $0.94 - $0.99 之间
        """
        opportunities = []
        
        for market in markets:
            # 使用 Gamma API 的价格格式
            prices = get_market_prices(market)
            no_price = prices.get('No', 0.5)
            
            if 0.94 <= no_price <= 0.99:
                edge = 1.0 - no_price
                
                # 获取 token IDs
                clob_token_ids = market.get('clobTokenIds', '[]')
                try:
                    import json
                    token_ids = json.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
                except:
                    token_ids = []
                
                opportunities.append({
                    'type': 'CLEANER',
                    'market': market,
                    'question': market.get('question', ''),
                    'no_token': token_ids[1] if len(token_ids) > 1 else None,
                    'no_price': no_price,
                    'edge': edge
                })
        
        # 按利润排序
        opportunities.sort(key=lambda x: x['edge'], reverse=True)
        return opportunities
    
    def find_ai_opportunities(self, markets: List[dict]) -> List[dict]:
        """
        策略三/四：AI 分析 - 使用 Gemini 寻找信息差
        """
        opportunities = []
        
        for market in markets[:5]:  # 限制 AI 分析数量
            question = market.get('question', '')
            description = market.get('description', '')
            
            # 使用 Gamma API 的价格格式
            prices = get_market_prices(market)
            yes_price = prices.get('Yes', 0.5)
            
            # 调用 AI 分析
            analysis = analyze_market_with_gemini(question, description, yes_price)
            
            if analysis and analysis.get('signal') != 'HOLD':
                edge = analysis.get('edge', 0)
                if edge >= 0.10:  # 10% 以上优势
                    opportunities.append({
                        'type': 'AI_SIGNAL',
                        'market': market,
                        'question': question,
                        'signal': analysis['signal'],
                        'ai_probability': analysis['my_probability'],
                        'market_price': yes_price,
                        'edge': edge,
                        'confidence': analysis.get('confidence_level', 'MEDIUM'),
                        'reasoning': analysis.get('reasoning', '')
                    })
            
            time.sleep(1)  # 避免 API 限流
        
        return opportunities
    
    def execute_trade(self, opportunity: dict, balance: float) -> Optional[dict]:
        """执行交易"""
        opp_type = opportunity['type']
        
        if opp_type == 'ARBITRAGE':
            return self._execute_arbitrage(opportunity, balance)
        elif opp_type == 'CLEANER':
            return self._execute_cleaner(opportunity, balance)
        elif opp_type == 'AI_SIGNAL':
            return self._execute_ai_signal(opportunity, balance)
        
        return None
    
    def _execute_arbitrage(self, opp: dict, balance: float) -> dict:
        """执行套利交易"""
        edge = opp['edge']
        position = min(balance * 0.05, 10.0)  # 最大 $10
        
        yes_price = opp['yes_price']
        no_price = opp['no_price']
        total = yes_price + no_price
        
        yes_amount = position * (yes_price / total)
        no_amount = position * (no_price / total)
        
        result = {
            'type': 'ARBITRAGE',
            'yes_amount': yes_amount,
            'no_amount': no_amount,
            'edge': edge,
            'expected_profit': position * edge,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n🎰 [收割者] 执行套利")
        print(f"   Yes: ${yes_price:.3f} x ${yes_amount:.2f}")
        print(f"   No: ${no_price:.3f} x ${no_amount:.2f}")
        print(f"   预期利润: ${result['expected_profit']:.4f}")
        
        if not self.dry_run:
            # 实际下单逻辑
            pass
        else:
            print(f"   [模拟模式] 未实际下单")
        
        return result
    
    def _execute_cleaner(self, opp: dict, balance: float) -> dict:
        """执行清洁工交易"""
        edge = opp['edge']
        position = min(balance * 0.20, 20.0)  # 最大 $20
        
        result = {
            'type': 'CLEANER',
            'question': opp['question'][:50],
            'no_price': opp['no_price'],
            'amount': position,
            'edge': edge,
            'expected_profit': position * edge,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n🧹 [清洁工] 执行交易")
        print(f"   市场: {opp['question'][:40]}...")
        print(f"   No 价格: ${opp['no_price']:.3f}")
        print(f"   买入: ${position:.2f}")
        print(f"   预期利润: ${result['expected_profit']:.4f}")
        
        if not self.dry_run:
            # 实际下单逻辑
            pass
        else:
            print(f"   [模拟模式] 未实际下单")
        
        return result
    
    def _execute_ai_signal(self, opp: dict, balance: float) -> dict:
        """执行 AI 信号交易"""
        edge = opp['edge']
        confidence = opp['confidence']
        
        # 根据信心调整仓位，并应用风控限制
        multiplier = {'HIGH': 1.0, 'MEDIUM': 0.6, 'LOW': 0.3}.get(confidence, 0.5)
        position = min(balance * 0.10 * multiplier, MAX_SINGLE_BET)  # 应用单笔限制
        
        result = {
            'type': 'AI_SIGNAL',
            'question': opp['question'][:50],
            'signal': opp['signal'],
            'ai_probability': opp['ai_probability'],
            'market_price': opp['market_price'],
            'amount': position,
            'edge': edge,
            'confidence': confidence,
            'reasoning': opp['reasoning'],
            'expected_profit': position * edge,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n🧠 [AI 信号] 执行交易")
        print(f"   市场: {opp['question'][:40]}...")
        print(f"   信号: {opp['signal']}")
        print(f"   AI 概率: {opp['ai_probability']:.0%} vs 市场: {opp['market_price']:.0%}")
        print(f"   Edge: {edge:.1%}, 信心: {confidence}")
        print(f"   买入: ${position:.2f}")
        
        if not self.dry_run:
            # 实际下单逻辑
            try:
                market = opp['market']
                signal = opp['signal']
                
                # 获取 token IDs
                clob_token_ids = market.get('clobTokenIds', '[]')
                import json as json_lib
                token_ids = json_lib.loads(clob_token_ids) if isinstance(clob_token_ids, str) else clob_token_ids
                
                if signal == 'BUY_YES' and len(token_ids) > 0:
                    token_id = token_ids[0]
                    price = opp['market_price']
                elif signal == 'BUY_NO' and len(token_ids) > 1:
                    token_id = token_ids[1]
                    price = 1.0 - opp['market_price']
                else:
                    print(f"   ⚠️ 无法确定 token ID")
                    return result
                
                # 计算数量
                size = position / price if price > 0 else 0
                
                # 创建订单
                order_args = OrderArgs(
                    price=price,
                    size=size,
                    side=BUY,
                    token_id=token_id
                )
                
                print(f"   📤 提交订单: {signal} @ ${price:.3f} x {size:.2f}")
                
                signed_order = self.client.create_order(order_args)
                resp = self.client.post_order(signed_order, OrderType.GTC)
                
                result['order_id'] = resp.get('orderID')
                result['status'] = 'SUBMITTED'
                print(f"   ✅ 订单已提交: {result['order_id']}")
                
            except Exception as e:
                print(f"   ❌ 下单失败: {e}")
                result['status'] = 'FAILED'
                result['error'] = str(e)
        else:
            print(f"   [模拟模式] 未实际下单")
        
        return result
    
    def log_trade(self, trade: dict):
        """记录交易"""
        self.trade_log.append(trade)
        
        # 保存到文件
        try:
            with open(LOG_FILE, 'w') as f:
                json.dump(self.trade_log, f, indent=2)
        except Exception as e:
            print(f"⚠️ 保存日志失败: {e}")
    
    def run_cycle(self, strategy: str = 'all'):
        """运行一个交易周期"""
        print(f"\n{'='*60}")
        print(f"⏰ 交易周期开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        balance = self.get_balance()
        print(f"💰 当前余额: ${balance:.2f}")
        
        if balance < 2:
            print("❌ 余额不足，跳过本轮")
            return
        
        # 扫描市场
        markets = self.scan_markets()
        
        if not markets:
            print("❌ 没有可用市场")
            return
        
        opportunities = []
        
        # 根据策略寻找机会
        if strategy in ['all', 'harvester']:
            arb_opps = self.find_harvester_opportunities(markets)
            opportunities.extend(arb_opps)
            print(f"   🎰 收割者机会: {len(arb_opps)}")
        
        if strategy in ['all', 'cleaner']:
            clean_opps = self.find_cleaner_opportunities(markets)
            opportunities.extend(clean_opps)
            print(f"   🧹 清洁工机会: {len(clean_opps)}")
        
        if strategy in ['all', 'ai']:
            ai_opps = self.find_ai_opportunities(markets)
            opportunities.extend(ai_opps)
            print(f"   🧠 AI 信号机会: {len(ai_opps)}")
        
        # 执行交易
        if opportunities:
            print(f"\n📊 总计发现 {len(opportunities)} 个机会")
            
            # 按 edge 排序，优先执行高收益机会
            opportunities.sort(key=lambda x: x['edge'], reverse=True)
            
            # 执行前 3 个最佳机会
            for opp in opportunities[:3]:
                trade = self.execute_trade(opp, balance)
                if trade:
                    self.log_trade(trade)
                    self.total_pnl += trade.get('expected_profit', 0)
        else:
            print("\n⏸️ 本轮无交易机会")
        
        # 显示统计
        print(f"\n📈 本次会话统计:")
        print(f"   总交易: {len(self.trade_log)}")
        print(f"   预期总利润: ${self.total_pnl:.4f}")
    
    def run_continuous(self, interval: int = SCAN_INTERVAL):
        """持续运行"""
        print(f"\n🔄 启动持续运行模式 (间隔: {interval}秒)")
        
        try:
            while True:
                self.run_cycle()
                print(f"\n⏳ 等待 {interval} 秒后进行下一轮扫描...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断，停止运行")
            self.print_summary()
    
    def print_summary(self):
        """打印总结"""
        print(f"\n{'='*60}")
        print(f"📊 交易总结")
        print(f"{'='*60}")
        print(f"   运行时长: {datetime.now() - self.session_start}")
        print(f"   总交易数: {len(self.trade_log)}")
        print(f"   预期总利润: ${self.total_pnl:.4f}")
        
        # 按类型统计
        by_type = {}
        for trade in self.trade_log:
            t = trade.get('type', 'UNKNOWN')
            by_type[t] = by_type.get(t, 0) + 1
        
        print(f"\n   按策略统计:")
        for t, count in by_type.items():
            print(f"      {t}: {count} 笔")
        
        print(f"{'='*60}\n")


# ================= 命令行入口 =================

def main():
    parser = argparse.ArgumentParser(description='Polymarket 自动化交易引擎')
    parser.add_argument('--strategy', '-s', 
                        choices=['all', 'harvester', 'cleaner', 'ai'],
                        default='all',
                        help='选择策略 (默认: all)')
    parser.add_argument('--live', action='store_true',
                        help='实盘模式 (默认: 模拟)')
    parser.add_argument('--once', action='store_true',
                        help='只运行一次 (默认: 持续运行)')
    parser.add_argument('--interval', '-i', type=int, default=300,
                        help='扫描间隔秒数 (默认: 300)')
    
    args = parser.parse_args()
    
    # 确定策略类型
    strategy_map = {
        'harvester': StrategyType.HARVESTER,
        'cleaner': StrategyType.CLEANER,
        'ai': StrategyType.LEARNER,
        'all': StrategyType.SELF_SUSTAIN
    }
    
    engine = TradingEngine(
        strategy_type=strategy_map.get(args.strategy, StrategyType.LEARNER),
        dry_run=not args.live
    )
    
    if args.once:
        engine.run_cycle(args.strategy)
        engine.print_summary()
    else:
        engine.run_continuous(args.interval)


if __name__ == "__main__":
    main()
