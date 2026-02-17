import os
import json
from google import genai
from google.genai import types

# ================= 配置区 =================
# Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAiYvgVtxHm73ddnYYn5G4iPIDtrBr3zxE")
MODEL = "gemini-3-flash-preview"  # Gemini 3 Flash - 最新推理模型
# =========================================

# 模拟一个市场数据（未来从 scan_markets.py 传入）
market_data = {
    "question": "Will Donald Trump be inaugurated as President on Jan 20, 2025?",
    "description": "This market resolves to 'Yes' if Donald Trump is inaugurated...",
    "current_price": 0.45  # 市场认为有 45% 概率
}

def analyze_market(market):
    """使用 Gemini 分析市场并预测概率"""
    
    # 初始化客户端
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 核心提示词 - 赋予它预测家的人格
    prompt = f"""
你是一位精通地缘政治和概率分析的超级预测家 (Superforecaster)。
你的任务是根据提供的问题和背景，通过逻辑推理，给出一个该事件发生的客观概率 (0.00 到 1.00)。

Event: {market['question']}
Context: {market['description']}
Current Market Price (Implied Probability): {market['current_price']}

请分析这个事件，给出你独立的概率预测。

请严格遵循以下 JSON 格式输出:
{{
    "reasoning": "你的详细分析过程...",
    "predicted_probability": 0.xx,
    "confidence": "High/Medium/Low"
}}

只输出 JSON，不要有其他内容。
"""

    print(f"🤖 Moltbot 正在思考: {market['question']}...")
    
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="high")
            )
        )
        
        # 解析 JSON 响应
        text = response.text.strip()
        # 移除可能的 markdown 代码块标记
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        
        result = json.loads(text)
        return result
        
    except Exception as e:
        print(f"❌ 思考失败: {e}")
        return None

def make_decision(analysis, market_price):
    """根据 AI 分析结果做出交易决策"""
    if not analysis: 
        return None
    
    my_prob = analysis['predicted_probability']
    market_prob = market_price
    
    print("\n" + "="*40)
    print(f"🧠 Moltbot 预测概率: {my_prob:.2%} (信心: {analysis['confidence']})")
    print(f"📊 当前市场赔率:   {market_prob:.2%}")
    print(f"📝 分析理由: {analysis['reasoning'][:150]}...")
    
    # 计算优势 (Edge)
    edge = my_prob - market_prob
    
    if edge > 0.05:  # 只有当我有 5% 以上的优势时才动手
        print(f"✅ 机会发现! 优势 {edge:.1%} -> 建议买入 YES")
        decision = "BUY_YES"
    elif edge < -0.05:
        print(f"✅ 机会发现! 优势 {abs(edge):.1%} -> 建议买入 NO")
        decision = "BUY_NO"
    else:
        print("⏸️ 分歧不大，观望")
        decision = "HOLD"
    
    print("="*40 + "\n")
    return decision

if __name__ == "__main__":
    analysis = analyze_market(market_data)
    decision = make_decision(analysis, market_data['current_price'])
    print(f"最终决策: {decision}")
