"""
Gemini 信息差套利系统 (Gemini Info-Arbitrage System)
架构：漏斗式筛选 + RAG 增强
"""

import os
import json
import time
import requests
import google.generativeai as genai

# ================= 配置区 =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
MODEL_NAME = "gemini-3-flash-preview"  # 最新模型，知识截止2025年1月，支持思考模式

# 套利参数
MIN_EDGE = 0.10          # 最小优势阈值 (10%)
MAX_CONFIDENCE = 0.85    # 防止过度自信，概率上限
MIN_CONFIDENCE = 0.15    # 概率下限
MAX_BET_RATIO = 0.10     # 单笔最大仓位比例 (10%)

# 搜索配置
USE_REAL_SEARCH = True   # 是否使用真实搜索 API
# =========================================


def search_news_brave(query, count=5):
    """
    使用 Brave Search API 搜索最新新闻
    """
    print(f"🔍 [Brave Search] 正在搜索: '{query}'...")
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    params = {
        "q": query,
        "count": count,
        "freshness": "pw"  # 过去一周的新闻
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        web_results = data.get("web", {}).get("results", [])
        
        for i, item in enumerate(web_results[:count], 1):
            title = item.get("title", "")
            description = item.get("description", "")
            url = item.get("url", "")
            results.append(f"{i}. [{title}] {description}")
        
        if results:
            return "Search Results:\n" + "\n".join(results)
        else:
            return "No recent news found."
            
    except Exception as e:
        print(f"⚠️ Brave Search 失败: {e}")
        return search_news_mock(query)


def search_news_mock(query):
    """
    模拟搜索结果 (备用)
    """
    print(f"🔍 [模拟搜索] 正在抓取关于 '{query}' 的最新新闻...")
    
    mock_results = f"""
    Search Results for "{query}":
    1. [Reuters] Latest analysis suggests market uncertainty remains high.
    2. [Bloomberg] Experts divided on outcome, with slight lean toward current consensus.
    3. [CNBC] Recent developments indicate situation is evolving rapidly.
    4. [AP News] Official statements remain ambiguous, market awaits clarity.
    """
    return mock_results


def search_news(query):
    """
    搜索最新新闻 (RAG 核心)
    """
    if USE_REAL_SEARCH and BRAVE_API_KEY:
        return search_news_brave(query)
    else:
        return search_news_mock(query)


def analyze_market_with_gemini(market_question, market_description, current_price):
    """
    使用 Gemini 分析市场并给出套利信号
    
    Args:
        market_question: 市场问题
        market_description: 市场描述
        current_price: 当前 Yes 价格 (0-1)
    
    Returns:
        dict: 分析结果
    """
    # 1. 初始化客户端
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    # 2. 获取外部信息 (RAG 增强)
    news_context = search_news(market_question)
    
    # 3. 构建提示词 (Chain of Thought)
    prompt = f"""
你是一位专业的预测市场套利分析师。你的任务是发现市场定价错误并给出交易信号。

## 目标事件
问题: "{market_question}"
描述: "{market_description[:500] if market_description else 'N/A'}"
当前市场价格 (隐含概率): {current_price:.2%}

## 最新新闻上下文
{news_context}

## 分析任务
1. 分析新闻情绪和事实数据
2. 估算事件发生的真实概率 (YES 的概率)
3. 将你的概率与市场价格对比
4. 仅当优势 (Edge) > 10% 时给出交易信号

## 重要规则
- 概率必须在 {MIN_CONFIDENCE:.0%} 到 {MAX_CONFIDENCE:.0%} 之间 (防止过度自信)
- 如果信息不足，倾向于 HOLD
- Edge = |你的概率 - 市场价格|

## 输出格式 (JSON)
{{
    "reasoning": "简洁的分析理由 (50字以内)",
    "my_probability": 0.xx,
    "market_price": {current_price},
    "edge": 0.xx,
    "signal": "BUY_YES" | "BUY_NO" | "HOLD",
    "confidence_level": "HIGH" | "MEDIUM" | "LOW"
}}

只输出 JSON，不要有其他内容。
"""

    print(f"🤖 Gemini ({MODEL_NAME}) 正在推理...")
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2  # 降低幻觉，提高理性
            )
        )
        
        # 解析 JSON 响应
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        
        analysis = json.loads(text)
        
        # 强制应用概率边界
        if analysis['my_probability'] > MAX_CONFIDENCE:
            analysis['my_probability'] = MAX_CONFIDENCE
        if analysis['my_probability'] < MIN_CONFIDENCE:
            analysis['my_probability'] = MIN_CONFIDENCE
        
        # 重新计算 edge
        if analysis['signal'] == 'BUY_YES':
            analysis['edge'] = analysis['my_probability'] - current_price
        elif analysis['signal'] == 'BUY_NO':
            analysis['edge'] = (1 - analysis['my_probability']) - (1 - current_price)
        else:
            analysis['edge'] = abs(analysis['my_probability'] - current_price)
        
        return analysis

    except Exception as e:
        print(f"❌ Gemini 调用失败: {e}")
        return None


def calculate_position_size(balance, edge, confidence_level):
    """
    根据 Kelly 公式简化版计算仓位大小
    
    Args:
        balance: 可用余额
        edge: 优势比例
        confidence_level: 信心等级
    
    Returns:
        float: 建议下注金额
    """
    # 信心系数
    confidence_multiplier = {
        'HIGH': 1.0,
        'MEDIUM': 0.6,
        'LOW': 0.3
    }.get(confidence_level, 0.5)
    
    # 简化 Kelly: bet = edge * confidence * max_ratio * balance
    kelly_fraction = edge * confidence_multiplier
    
    # 限制最大仓位
    kelly_fraction = min(kelly_fraction, MAX_BET_RATIO)
    
    bet_size = balance * kelly_fraction
    
    # 最小下注 $2
    return max(bet_size, 2.0)


def print_analysis_report(analysis, market_question):
    """打印分析报告"""
    if not analysis:
        print("❌ 分析失败")
        return
    
    print("\n" + "="*50)
    print(f"📊 市场: {market_question[:50]}...")
    print("="*50)
    print(f"🎯 交易信号: {analysis['signal']}")
    print(f"🧠 AI 估算概率: {analysis['my_probability']:.2%}")
    print(f"📈 市场当前赔率: {analysis['market_price']:.2%}")
    print(f"💰 潜在利润空间 (Edge): {analysis['edge']:.2%}")
    print(f"🎚️ 信心等级: {analysis.get('confidence_level', 'N/A')}")
    print(f"📝 理由: {analysis['reasoning']}")
    print("="*50 + "\n")


# ================= 单元测试 =================
if __name__ == "__main__":
    print("\n" + "🚀 Gemini 信息差套利系统测试 🚀".center(50))
    print("="*50)
    
    # 测试案例 1: 美联储利率决议
    test_cases = [
        {
            "question": "Will the Fed hold rates in March 2026?",
            "description": "This market resolves to YES if the Federal Reserve maintains current interest rates at their March 2026 FOMC meeting.",
            "price": 0.40
        },
        {
            "question": "Will Bitcoin reach $150,000 by end of February 2026?",
            "description": "This market resolves to YES if Bitcoin's price reaches or exceeds $150,000 USD at any point before March 1, 2026.",
            "price": 0.15
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n📌 测试案例 {i}")
        analysis = analyze_market_with_gemini(
            case["question"],
            case["description"],
            case["price"]
        )
        print_analysis_report(analysis, case["question"])
        
        if analysis and analysis['signal'] != 'HOLD':
            # 假设余额 100 USDC
            bet_size = calculate_position_size(
                100, 
                analysis['edge'], 
                analysis.get('confidence_level', 'MEDIUM')
            )
            print(f"💵 建议下注金额: ${bet_size:.2f} USDC")
        
        time.sleep(1)  # 避免 API 限流
    
    print("\n✅ 测试完成")
