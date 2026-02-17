from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config

# ================= 填空区 =================
# 把您从 URL 里复制出来的 Slug 填在这里
TARGET_SLUG = "fed-decision-in-march-885"  # <--- 这里填 URL 里的那串字
# =========================================

def main():
    # 初始化客户端
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
    
    print(f"正在精准定位市场: {TARGET_SLUG}...")
    
    # 通过 Slug 获取市场详情
    try:
        resp = client.get_market(TARGET_SLUG)
        
        print("\n" + "="*40)
        print(f"✅ 市场名称: {resp['question']}")
        print(f"🆔 Condition ID: {resp['condition_id']}")
        print("-" * 40)
        
        # 提取 Token ID
        tokens = resp['tokens']
        # 通常 Token[0] 是 Yes, Token[1] 是 No，但我们需要核对 outcome
        for token in tokens:
            print(f"选项: {token['outcome']} ({token['price']*100:.1f}¢)")
            print(f"   👉 Token ID: {token['token_id']}")
        
        print("="*40 + "\n")
        print("🚀 下一步：请复制上面您想买的那个 Token ID，填入 trade.py")

    except Exception as e:
        print(f"❌ 查找失败: {e}")
        print("提示：请确认 Slug 拼写正确，不要带问号或后面的参数。")

if __name__ == "__main__":
    main()
