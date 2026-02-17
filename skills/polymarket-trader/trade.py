import os
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs
from py_clob_client.order_builder.constants import BUY

# 引入我们之前配好的密钥
import config 

def main():
    print("🤖 Moltbot 正在启动...")

    # 1. 初始化客户端
    creds = ApiCreds(
        api_key=config.API_KEY,
        api_secret=config.API_SECRET,
        api_passphrase=config.API_PASSPHRASE
    )
    
    # 代理钱包地址 (Proxy Portfolio)
    PROXY_WALLET = "0xdC32539E1B60e77de554fEc4347fC04d980Fa523"
    
    client = ClobClient(
        host=config.HOST,
        key=config.PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        creds=creds,
        signature_type=2,  # Poly GNOSIS SAFE 钱包使用 type 2
        funder=PROXY_WALLET  # 指定代理钱包作为资金来源
    )

    # 2. 锁定目标：Will Trump deport 500,000-750,000 people?
    # 这是一个有流动性的活跃市场
    condition_id = "0x2393ed0b0fdc450054c7b9071907eca75cf4fc36e385adf4a0a5f99ee62243e8"
    
    # 获取这个问题的 Token ID (Yes 和 No)
    try:
        resp = client.get_market(condition_id)
        # 通常 token[1] 是 No 的 ID，token[0] 是 Yes
        token_id_no = resp['tokens'][1]['token_id']
        print(f"✅ 锁定市场: {resp['question']}")
        print(f"🎯 目标资产: No (Token ID: ...{token_id_no[-6:]})")
    except Exception as e:
        print(f"❌ 获取市场失败: {e}")
        return

    # 3. 询价 (获取盘口数据)
    print("📊 正在分析盘口...")
    orderbook = client.get_order_book(token_id_no)
    
    # 获取卖一价 (Ask) - 市场上最便宜的卖单
    if not orderbook.asks:
        print("❌ 市场流动性不足，暂停交易")
        return
        
    best_ask = float(orderbook.asks[0].price)
    print(f"当前市场最低卖价: {best_ask} ({best_ask * 100:.1f}¢)")

    # 4. 制定策略：挂一个比卖一价便宜 0.01 的单子 (做 Maker)
    my_price = round(best_ask - 0.01, 2)
    # 保护机制：如果价格太低，强制设为 0.1
    if my_price <= 0: my_price = 0.10
    
    print(f"🤖 策略生成: 准备以 {my_price} ({my_price*100:.1f}¢) 买入")

    # 5. 执行下单
    print("🚀 正在发送交易指令...")
    try:
        order_args = OrderArgs(
            price=my_price,     # 价格
            size=2.0,           # 数量 (2 美元，满足最小订单要求)
            side=BUY,           # 买入
            token_id=token_id_no
        )
        
        # 发送签名订单
        tx = client.create_and_post_order(order_args)
        print("\n" + "="*30)
        print(f"✅ 下单成功！")
        print(f"📜 订单 ID: {tx['orderID']}")
        print(f"Success: True")
        print("="*30 + "\n")
        print("💡 请去网页端 'Open Orders' 查看您的机器人挂单")

    except Exception as e:
        print(f"\n❌ 交易失败: {e}")
        print("常见原因: 余额不足、API Key 错误、或 VPN 不稳定")

if __name__ == "__main__":
    main()
