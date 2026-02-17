"""
Moltbot 全自动交易系统
扫描市场 → AI 分析 → 自动下单
"""

import os
import json
import time
from google import genai
from google.genai import types
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

import config

# ================= 配置区 =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAiYvgVtxHm73ddnYYn5G4iPIDtrBr3zxE")
MODEL = "gemini-3-flash-preview"
PROXY_WALLET = "0xdC32539E1B60e77de554fEc4347fC04d980Fa523"

# 交易参数
MIN_EDGE = 0.05        # 最小优势阈值 (5%)
ORDER_SIZE = 2.0       # 每单金额 (USDC)
MAX_MARKETS = 5        # 最多分析几个市场
DRY_RUN = True         # 模拟模式 (True=不实际下单)
# =========================================


def init_polymarket_client():
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


def scan_markets(client, max_markets=5):
    """扫描有流动性的活跃市场"""
    print("📡 扫描活跃市场...")
    
    markets_to_analyze = []
    cursor = ''
    
    for page in range(30):
        resp = client.get_markets(next_cursor=cursor)
        markets = resp.get('data', [])
        
        for m in markets:
            if not m.get('active') or m.get('closed') or not m.get('accepting_orders'):
                continue
            
            tokens = m.get('tokens', [])
            if len(tokens) < 2 or not tokens[0].get('token_id') or not tokens[1].get('token_id'):
                continue
            
            # 尝试获取订单簿
            try:
                ob = client.get_order_book(tokens[0].get('token_id'))
                if ob.bids and ob.asks:
                    yes_price = float(tokens[0].get('price', 0.5))
                    markets_to_analyze.append({
                        'question': m.get('question'),
                        'description': m.get('description', '')[:500],
                        'condition_id': m.get('condition_id'),
                        'yes_token': tokens[0].get('token_id'),
                        'no_token': tokens[1].get('token_id'),
                        'yes_price': yes_price,
                        'no_price': 1 - yes_price
                    })
                    
                    if len(markets_to_analyze) >= max_markets:
                        break
            except:
                pass
        
        if len(markets_to_analyze) >= max_markets:
            break
        
        cursor = resp.get('next_cursor', '')
        if not cursor:
            break
    
    print(f"   找到 {len(markets_to_analyze)} 个可分析市场")
    return markets_to_analyze


def analyze_with_ai(market):
    """使用 Gemini 3 分析市场"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
你是一位精通地缘政治和概率分析的超级预测家 (Superforecaster)。
你的任务是根据提供的问题和背景，通过逻辑推理，给出一个该事件发生的客观概率 (0.00 到 1.00)。

Event: {market['question']}
Context: {market['description']}
Current Market Price (Yes): {market['yes_price']}

请分析这个事件，给出你独立的概率预测。

请严格遵循以下 JSON 格式输出:
{{
    "reasoning": "你的详细分析过程 (100字以内)...",
    "predicted_probability": 0.xx,
    "confidence": "High/Medium/Low"
}}

只输出 JSON，不要有其他内容。
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="medium")
            )
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        
        return json.loads(text)
        
    except Exception as e:
        print(f"   ❌ AI 分析失败: {e}")
        return None


def make_decision(analysis, market):
    """根据 AI 分析做出交易决策"""
    if not analysis:
        return None, None
    
    my_prob = analysis['predicted_probability']
    market_yes = market['yes_price']
    
    # 计算优势
    yes_edge = my_prob - market_yes
    no_edge = (1 - my_prob) - (1 - market_yes)
    
    if yes_edge > MIN_EDGE:
        return "BUY_YES", yes_edge
    elif no_edge > MIN_EDGE:
        return "BUY_NO", no_edge
    else:
        return "HOLD", 0


def execute_trade(client, market, decision, edge):
    """执行交易"""
    if decision == "HOLD":
        return None
    
    if decision == "BUY_YES":
        token_id = market['yes_token']
        price = market['yes_price']
    else:  # BUY_NO
        token_id = market['no_token']
        price = market['no_price']
    
    # 获取最新订单簿
    try:
        ob = client.get_order_book(token_id)
        if ob.asks:
            best_ask = float(ob.asks[0].price)
            # 以略低于卖一价挂单
            my_price = round(best_ask - 0.01, 2)
            if my_price <= 0:
                my_price = 0.01
        else:
            my_price = round(price - 0.01, 2)
    except:
        my_price = round(price - 0.01, 2)
    
    if DRY_RUN:
        print(f"   🔸 [模拟] 将以 {my_price} 买入 {ORDER_SIZE} USDC")
        return {"orderID": "DRY_RUN_ORDER", "simulated": True}
    
    # 实际下单
    try:
        order_args = OrderArgs(
            price=my_price,
            size=ORDER_SIZE,
            side=BUY,
            token_id=token_id
        )
        
        tx = client.create_and_post_order(order_args)
        return tx
    except Exception as e:
        print(f"   ❌ 下单失败: {e}")
        return None


def run_trading_cycle():
    """运行一个完整的交易周期"""
    print("\n" + "="*60)
    print("🤖 Moltbot 全自动交易系统启动")
    print(f"   模式: {'模拟' if DRY_RUN else '实盘'}")
    print(f"   最小优势: {MIN_EDGE:.0%}")
    print(f"   单笔金额: {ORDER_SIZE} USDC")
    print("="*60 + "\n")
    
    # 初始化客户端
    poly_client = init_polymarket_client()
    
    # 扫描市场
    markets = scan_markets(poly_client, MAX_MARKETS)
    
    if not markets:
        print("❌ 没有找到可分析的市场")
        return
    
    opportunities = []
    
    # 分析每个市场
    for i, market in enumerate(markets, 1):
        print(f"\n📊 [{i}/{len(markets)}] 分析: {market['question'][:50]}...")
        
        # AI 分析
        analysis = analyze_with_ai(market)
        if not analysis:
            continue
        
        # 决策
        decision, edge = make_decision(analysis, market)
        
        print(f"   🧠 AI 预测: {analysis['predicted_probability']:.0%} (信心: {analysis['confidence']})")
        print(f"   📈 市场价格: Yes={market['yes_price']:.0%}")
        
        if decision != "HOLD":
            print(f"   ✅ 发现机会! {decision} (优势: {edge:.1%})")
            opportunities.append({
                'market': market,
                'analysis': analysis,
                'decision': decision,
                'edge': edge
            })
        else:
            print(f"   ⏸️ 观望 (优势不足)")
        
        # 避免 API 限流
        time.sleep(1)
    
    # 执行交易
    print("\n" + "-"*60)
    print(f"📋 分析完成: 发现 {len(opportunities)} 个交易机会")
    
    for opp in opportunities:
        market = opp['market']
        decision = opp['decision']
        edge = opp['edge']
        
        print(f"\n🚀 执行交易: {market['question'][:40]}...")
        print(f"   决策: {decision}, 优势: {edge:.1%}")
        
        result = execute_trade(poly_client, market, decision, edge)
        
        if result:
            print(f"   ✅ 订单已提交: {result.get('orderID', 'N/A')[:20]}...")
    
    print("\n" + "="*60)
    print("✅ 交易周期完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_trading_cycle()
