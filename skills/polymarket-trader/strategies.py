"""
Polymarket 多策略交易系统
包含 4 种核心策略配置
"""

import os
import json
import time
import requests
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

import config

# ================= 策略配置 =================

class StrategyType(Enum):
    HARVESTER = "harvester"      # 收割者 - 微套利
    CLEANER = "cleaner"          # 清洁工 - 反向黑天鹅
    LEARNER = "learner"          # 学习者 - 小资金
    SELF_SUSTAIN = "self_sustain" # AI 自维持


@dataclass
class StrategyConfig:
    """策略配置基类"""
    name: str
    description: str
    min_edge: float           # 最小优势阈值
    max_position_ratio: float # 单笔最大仓位比例
    target_win_rate: float    # 目标胜率
    max_daily_trades: int     # 每日最大交易次数
    cooldown_seconds: int     # 交易冷却时间


# ================= 策略一：收割者模型 =================
HARVESTER_CONFIG = StrategyConfig(
    name="收割者 (Harvester)",
    description="高频微套利，利用 Yes+No < $1 的数学错误定价",
    min_edge=0.001,           # 0.1% 即可触发 (几美分利润)
    max_position_ratio=0.05,  # 单笔 5% 仓位
    target_win_rate=0.99,     # 99% 胜率 (数学套利)
    max_daily_trades=1000,    # 高频
    cooldown_seconds=1        # 1 秒冷却
)


# ================= 策略二：清洁工模型 =================
CLEANER_CONFIG = StrategyConfig(
    name="清洁工 (Cleaner)",
    description="反向黑天鹅，买入极高概率的 No 选项",
    min_edge=0.01,            # 1% 利润即可
    max_position_ratio=0.20,  # 单笔 20% 仓位 (高确定性)
    target_win_rate=0.999,    # 99.9% 胜率
    max_daily_trades=50,      # 低频
    cooldown_seconds=60       # 1 分钟冷却
)


# ================= 策略三：学习者模型 =================
LEARNER_CONFIG = StrategyConfig(
    name="学习者 (Learner)",
    description="小资金试错，AI 进化高胜率策略",
    min_edge=0.10,            # 10% 优势
    max_position_ratio=0.10,  # 单笔 10% 仓位
    target_win_rate=0.92,     # 92% 胜率
    max_daily_trades=10,      # 低频学习
    cooldown_seconds=300      # 5 分钟冷却
)


# ================= 策略四：AI 自维持模型 =================
SELF_SUSTAIN_CONFIG = StrategyConfig(
    name="AI 自维持 (Self-Sustain)",
    description="覆盖 API 成本，实现自主运营",
    min_edge=0.05,            # 5% 优势
    max_position_ratio=0.15,  # 单笔 15% 仓位
    target_win_rate=0.80,     # 80% 胜率
    max_daily_trades=100,     # 中频
    cooldown_seconds=30       # 30 秒冷却
)


STRATEGY_CONFIGS = {
    StrategyType.HARVESTER: HARVESTER_CONFIG,
    StrategyType.CLEANER: CLEANER_CONFIG,
    StrategyType.LEARNER: LEARNER_CONFIG,
    StrategyType.SELF_SUSTAIN: SELF_SUSTAIN_CONFIG,
}


# ================= 策略实现 =================

class BaseStrategy:
    """策略基类"""
    
    def __init__(self, config: StrategyConfig, client: ClobClient):
        self.config = config
        self.client = client
        self.trade_count = 0
        self.last_trade_time = 0
        self.wins = 0
        self.losses = 0
    
    def can_trade(self) -> bool:
        """检查是否可以交易"""
        # 检查每日交易次数
        if self.trade_count >= self.config.max_daily_trades:
            return False
        
        # 检查冷却时间
        if time.time() - self.last_trade_time < self.config.cooldown_seconds:
            return False
        
        return True
    
    def calculate_position_size(self, balance: float, edge: float) -> float:
        """计算仓位大小"""
        # Kelly 公式简化版
        kelly = edge * self.config.target_win_rate
        kelly = min(kelly, self.config.max_position_ratio)
        
        position = balance * kelly
        return max(position, 2.0)  # 最小 $2
    
    def record_trade(self, is_win: bool):
        """记录交易结果"""
        self.trade_count += 1
        self.last_trade_time = time.time()
        if is_win:
            self.wins += 1
        else:
            self.losses += 1
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self.wins + self.losses
        win_rate = self.wins / total if total > 0 else 0
        return {
            "strategy": self.config.name,
            "trades": total,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2%}"
        }


class HarvesterStrategy(BaseStrategy):
    """
    策略一：收割者模型 (微套利)
    
    核心逻辑：监控 Yes + No 价格，当总和 < $1 时同时买入双方
    """
    
    def __init__(self, client: ClobClient):
        super().__init__(HARVESTER_CONFIG, client)
    
    def find_arbitrage(self, markets: List[dict]) -> List[dict]:
        """寻找套利机会"""
        opportunities = []
        
        for market in markets:
            tokens = market.get('tokens', [])
            if len(tokens) < 2:
                continue
            
            yes_token = tokens[0]
            no_token = tokens[1]
            
            yes_price = float(yes_token.get('price', 0.5))
            no_price = float(no_token.get('price', 0.5))
            
            total_price = yes_price + no_price
            
            # 套利条件：Yes + No < 1.00
            if total_price < 0.99:  # 留 1% 作为手续费缓冲
                edge = 1.0 - total_price
                if edge >= self.config.min_edge:
                    opportunities.append({
                        'market': market,
                        'yes_token': yes_token.get('token_id'),
                        'no_token': no_token.get('token_id'),
                        'yes_price': yes_price,
                        'no_price': no_price,
                        'edge': edge,
                        'signal': 'ARBITRAGE'
                    })
        
        return opportunities
    
    def execute(self, opportunity: dict, balance: float) -> Optional[dict]:
        """执行套利交易"""
        if not self.can_trade():
            return None
        
        edge = opportunity['edge']
        position = self.calculate_position_size(balance, edge)
        
        # 分配资金：按价格比例分配
        yes_price = opportunity['yes_price']
        no_price = opportunity['no_price']
        total = yes_price + no_price
        
        yes_amount = position * (yes_price / total)
        no_amount = position * (no_price / total)
        
        print(f"🎰 [收割者] 发现套利机会!")
        print(f"   Yes: ${yes_price:.3f}, No: ${no_price:.3f}")
        print(f"   Edge: {edge:.2%}")
        print(f"   买入 Yes: ${yes_amount:.2f}, No: ${no_amount:.2f}")
        
        return {
            'yes_token': opportunity['yes_token'],
            'no_token': opportunity['no_token'],
            'yes_amount': yes_amount,
            'no_amount': no_amount,
            'edge': edge
        }


class CleanerStrategy(BaseStrategy):
    """
    策略二：清洁工模型 (反向黑天鹅)
    
    核心逻辑：买入极高概率的 No 选项 (价格 > $0.94)
    """
    
    # 清洁工目标价格区间
    MIN_NO_PRICE = 0.94  # 最低 94 美分
    MAX_NO_PRICE = 0.99  # 最高 99 美分
    
    def __init__(self, client: ClobClient):
        super().__init__(CLEANER_CONFIG, client)
    
    def find_opportunities(self, markets: List[dict]) -> List[dict]:
        """寻找清洁工机会"""
        opportunities = []
        
        for market in markets:
            tokens = market.get('tokens', [])
            if len(tokens) < 2:
                continue
            
            no_token = tokens[1]
            no_price = float(no_token.get('price', 0.5))
            
            # 清洁工条件：No 价格在 94-99 美分之间
            if self.MIN_NO_PRICE <= no_price <= self.MAX_NO_PRICE:
                edge = 1.0 - no_price  # 利润空间
                if edge >= self.config.min_edge:
                    opportunities.append({
                        'market': market,
                        'question': market.get('question', ''),
                        'no_token': no_token.get('token_id'),
                        'no_price': no_price,
                        'edge': edge,
                        'signal': 'BUY_NO'
                    })
        
        # 按利润空间排序
        opportunities.sort(key=lambda x: x['edge'], reverse=True)
        return opportunities
    
    def execute(self, opportunity: dict, balance: float) -> Optional[dict]:
        """执行清洁工交易"""
        if not self.can_trade():
            return None
        
        edge = opportunity['edge']
        position = self.calculate_position_size(balance, edge)
        
        print(f"🧹 [清洁工] 发现高确定性机会!")
        print(f"   市场: {opportunity['question'][:50]}...")
        print(f"   No 价格: ${opportunity['no_price']:.3f}")
        print(f"   预期利润: {edge:.2%}")
        print(f"   买入金额: ${position:.2f}")
        
        return {
            'token_id': opportunity['no_token'],
            'price': opportunity['no_price'],
            'amount': position,
            'edge': edge
        }


class LearnerStrategy(BaseStrategy):
    """
    策略三：学习者模型 (小资金启动)
    
    核心逻辑：小资金试错，记录结果，进化策略
    """
    
    def __init__(self, client: ClobClient):
        super().__init__(LEARNER_CONFIG, client)
        self.learning_history = []
        self.max_loss = 20.0  # 最大学习成本 $20
        self.total_loss = 0.0
    
    def can_trade(self) -> bool:
        """检查是否可以继续学习"""
        if self.total_loss >= self.max_loss:
            print("⚠️ [学习者] 已达到学习成本上限，暂停交易")
            return False
        return super().can_trade()
    
    def learn_from_result(self, trade: dict, is_win: bool, pnl: float):
        """从交易结果中学习"""
        self.learning_history.append({
            'trade': trade,
            'is_win': is_win,
            'pnl': pnl,
            'timestamp': time.time()
        })
        
        if not is_win:
            self.total_loss += abs(pnl)
        
        self.record_trade(is_win)
        
        # 分析学习结果
        if len(self.learning_history) >= 10:
            self._analyze_patterns()
    
    def _analyze_patterns(self):
        """分析交易模式"""
        wins = [h for h in self.learning_history if h['is_win']]
        losses = [h for h in self.learning_history if not h['is_win']]
        
        win_rate = len(wins) / len(self.learning_history)
        
        print(f"📊 [学习者] 学习进度:")
        print(f"   总交易: {len(self.learning_history)}")
        print(f"   胜率: {win_rate:.2%}")
        print(f"   学习成本: ${self.total_loss:.2f}")


class SelfSustainStrategy(BaseStrategy):
    """
    策略四：AI 自维持模型
    
    核心逻辑：覆盖 API 成本，实现自主运营
    """
    
    # API 成本估算 (每日)
    DAILY_API_COST = 1.0  # $1/天
    TARGET_DAILY_PROFIT = 5.0  # 目标日利润 $5
    
    def __init__(self, client: ClobClient):
        super().__init__(SELF_SUSTAIN_CONFIG, client)
        self.daily_profit = 0.0
        self.daily_api_calls = 0
    
    def is_profitable(self) -> bool:
        """检查是否已覆盖成本"""
        return self.daily_profit > self.DAILY_API_COST * 1.2  # 覆盖 120%
    
    def update_profit(self, pnl: float):
        """更新日利润"""
        self.daily_profit += pnl
        
        if self.daily_profit >= self.TARGET_DAILY_PROFIT:
            print(f"🎉 [AI 自维持] 已达成日目标! 利润: ${self.daily_profit:.2f}")
    
    def reset_daily(self):
        """重置每日统计"""
        self.daily_profit = 0.0
        self.daily_api_calls = 0
        self.trade_count = 0


# ================= 策略管理器 =================

class StrategyManager:
    """策略管理器 - 协调多策略运行"""
    
    def __init__(self):
        self.client = self._init_client()
        self.strategies = {
            StrategyType.HARVESTER: HarvesterStrategy(self.client),
            StrategyType.CLEANER: CleanerStrategy(self.client),
            StrategyType.LEARNER: LearnerStrategy(self.client),
            StrategyType.SELF_SUSTAIN: SelfSustainStrategy(self.client),
        }
        self.active_strategy = StrategyType.LEARNER  # 默认使用学习者模式
    
    def _init_client(self) -> ClobClient:
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
            funder="0xdC32539E1B60e77de554fEc4347fC04d980Fa523"
        )
    
    def set_strategy(self, strategy_type: StrategyType):
        """设置当前策略"""
        self.active_strategy = strategy_type
        print(f"✅ 已切换到策略: {STRATEGY_CONFIGS[strategy_type].name}")
    
    def get_all_stats(self) -> dict:
        """获取所有策略统计"""
        return {
            name.value: strategy.get_stats()
            for name, strategy in self.strategies.items()
        }
    
    def run_cycle(self, balance: float) -> Optional[dict]:
        """运行一个交易周期"""
        strategy = self.strategies[self.active_strategy]
        
        print(f"\n🔄 运行策略: {strategy.config.name}")
        print(f"   余额: ${balance:.2f}")
        
        # 获取市场数据
        markets = self._fetch_markets()
        
        if self.active_strategy == StrategyType.HARVESTER:
            opportunities = strategy.find_arbitrage(markets)
        elif self.active_strategy == StrategyType.CLEANER:
            opportunities = strategy.find_opportunities(markets)
        else:
            # 其他策略使用通用逻辑
            opportunities = []
        
        if opportunities:
            print(f"   发现 {len(opportunities)} 个机会")
            return strategy.execute(opportunities[0], balance)
        else:
            print(f"   暂无机会")
            return None
    
    def _fetch_markets(self, limit: int = 100) -> List[dict]:
        """获取市场数据"""
        try:
            resp = self.client.get_markets()
            return resp.get('data', [])[:limit]
        except Exception as e:
            print(f"❌ 获取市场失败: {e}")
            return []


# ================= 测试入口 =================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎰 Polymarket 多策略交易系统")
    print("="*60)
    
    # 显示所有策略配置
    print("\n📋 可用策略:")
    for strategy_type, cfg in STRATEGY_CONFIGS.items():
        print(f"\n  [{strategy_type.value}] {cfg.name}")
        print(f"      {cfg.description}")
        print(f"      最小优势: {cfg.min_edge:.1%}")
        print(f"      目标胜率: {cfg.target_win_rate:.1%}")
        print(f"      最大仓位: {cfg.max_position_ratio:.1%}")
    
    print("\n" + "="*60)
    print("✅ 策略系统初始化完成")
    print("="*60)
