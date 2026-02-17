from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config

def main():
    print("📡 正在扫描 Polymarket 当前活跃市场...")
    
    # 初始化客户端（需要使用 ApiCreds）
    creds = ApiCreds(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        api_passphrase=config.API_PASSPHRASE
    )
    
    client = ClobClient(
        host=config.HOST,
        key=config.PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        creds=creds,
        signature_type=0
    )
    
    # 1. 搜索包含 "Fed" 关键词的活跃市场
    # 我们只找 active=True (活跃中) 且 closed=False (未结算) 的
    resp = client.get_markets(next_cursor="")
    
    found_count = 0
    print(f"\n{'='*20} 扫描结果 {'='*20}\n")
    
    for market in resp.get('data', []):
        # 只看活跃且未关闭的市场
        if not market.get('active') or market.get('closed'):
            continue
            
        # 过滤关键词 (大小写不敏感)
        question = market.get('question', '')
        if "Fed" in question or "Bitcoin" in question or "fed" in question.lower() or "btc" in question.lower():
            
            # 必须开启订单簿模式
            if not market.get('enable_order_book'):
                continue
                
            print(f"✅ 发现目标: {question}")
            print(f"   Condition ID: {market['condition_id']}")
            
            # 打印 Yes/No 的 Token ID
            tokens = market.get('tokens', [])
            if len(tokens) >= 2:
                print(f"   🔴 No (Token ID): {tokens[1]['token_id']}")
                print(f"   🟢 Yes (Token ID): {tokens[0]['token_id']}")
            
            print("-" * 50)
            found_count += 1
            
            # 只显示前 3 个，避免刷屏
            if found_count >= 3:
                break
    
    if found_count == 0:
        print("❌ 未找到符合条件的市场（需要 enable_order_book=True）")
        print("\n正在搜索所有有订单簿的活跃市场...")
        
        # 显示任意有订单簿的市场
        for market in resp.get('data', []):
            if market.get('active') and not market.get('closed') and market.get('enable_order_book'):
                tokens = market.get('tokens', [])
                if len(tokens) >= 2 and tokens[0].get('token_id') and tokens[1].get('token_id'):
                    print(f"\n✅ 发现有订单簿的市场: {market.get('question')}")
                    print(f"   Condition ID: {market['condition_id']}")
                    print(f"   🔴 No (Token ID): {tokens[1]['token_id']}")
                    print(f"   🟢 Yes (Token ID): {tokens[0]['token_id']}")
                    found_count += 1
                    if found_count >= 3:
                        break
        
        if found_count == 0:
            print("❌ 当前没有启用订单簿的活跃市场")

if __name__ == "__main__":
    main()
