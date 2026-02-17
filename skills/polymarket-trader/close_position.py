import os
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs
from py_clob_client.order_builder.constants import SELL

import config

# 代理钱包地址 (Proxy Portfolio)
PROXY_WALLET = "0xdC32539E1B60e77de554fEc4347fC04d980Fa523"

def main():
    print("🔄 Moltbot 平仓系统启动...")
    print("=" * 50)

    # 1. 初始化客户端
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
        signature_type=2,  # Poly GNOSIS SAFE 钱包
        funder=PROXY_WALLET
    )

    # 2. 先取消所有未成交的挂单
    print("\n📋 第一步：取消所有未成交挂单...")
    try:
        result = client.cancel_all()
        print(f"   ✅ 已取消 {len(result.get('canceled', []))} 个挂单")
    except Exception as e:
        print(f"   ⚠️ 取消挂单时出错: {e}")

    # 3. 扫描当前持仓 (通过交易历史计算)
    print("\n📊 第二步：扫描当前持仓...")
    try:
        # 获取交易历史
        trades = client.get_trades()
        
        if not trades:
            print("   ℹ️ 没有交易记录，无持仓")
            return
        
        # 计算每个 token 的净持仓
        positions = {}
        for trade in trades:
            token_id = trade.get('asset_id', '')
            side = trade.get('side', '')
            size = float(trade.get('size', 0))
            price = float(trade.get('price', 0))
            outcome = trade.get('outcome', '')
            market = trade.get('market', '')
            
            if token_id not in positions:
                positions[token_id] = {
                    'size': 0,
                    'cost': 0,
                    'outcome': outcome,
                    'market': market
                }
            
            if side == 'BUY':
                positions[token_id]['size'] += size
                positions[token_id]['cost'] += size * price
            elif side == 'SELL':
                positions[token_id]['size'] -= size
                positions[token_id]['cost'] -= size * price
        
        # 过滤出有持仓的 token
        active_positions = {k: v for k, v in positions.items() if v['size'] > 0.001}
        
        if not active_positions:
            print("   ℹ️ 当前没有持仓（所有头寸已平仓）")
            return
        
        print(f"   发现 {len(active_positions)} 个持仓:")
        
        for token_id, pos in active_positions.items():
            size = pos['size']
            avg_price = pos['cost'] / size if size > 0 else 0
            
            print(f"\n   📌 Token: ...{token_id[-8:]}")
            print(f"      选项: {pos['outcome']}")
            print(f"      持仓数量: {size:.4f}")
            print(f"      平均成本: {avg_price:.4f}")
            
            # 4. 获取当前市场价格
            try:
                orderbook = client.get_order_book(token_id)
                
                if orderbook.bids:
                    best_bid = float(orderbook.bids[0].price)
                    print(f"      当前买一价: {best_bid}")
                    
                    # 计算盈亏
                    pnl = (best_bid - avg_price) * size
                    pnl_pct = ((best_bid / avg_price) - 1) * 100 if avg_price > 0 else 0
                    print(f"      预估盈亏: ${pnl:.4f} ({pnl_pct:+.2f}%)")
                    
                    # 5. 以略低于买一价的价格挂卖单 (激进限价)
                    sell_price = round(best_bid - 0.01, 2)
                    if sell_price <= 0:
                        sell_price = 0.01
                    
                    print(f"      🔻 准备以 {sell_price} 卖出 {size:.4f} 份...")
                    
                    order_args = OrderArgs(
                        price=sell_price,
                        size=size,
                        side=SELL,
                        token_id=token_id
                    )
                    
                    tx = client.create_and_post_order(order_args)
                    print(f"      ✅ 卖单已提交！订单 ID: {tx.get('orderID', 'N/A')[:16]}...")
                    
                else:
                    print(f"      ⚠️ 无买盘，无法卖出")
                    
            except Exception as e:
                print(f"      ❌ 处理失败: {e}")
        
        print("\n" + "=" * 50)
        print("✅ 平仓操作完成！请去网页端确认订单状态。")
        
    except Exception as e:
        print(f"❌ 获取持仓失败: {e}")

if __name__ == "__main__":
    main()
