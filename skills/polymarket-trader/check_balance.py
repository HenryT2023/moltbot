from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType
import config # 导入刚才写的配置文件

def main():
    print("正在建立安全连接...")
    
    try:
        # 构建 API 凭证对象
        creds = ApiCreds(
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
            api_passphrase=config.API_PASSPHRASE
        )
        
        # 初始化客户端 (自动读取 config.py 里的参数)
        client = ClobClient(
            host=config.HOST,
            key=config.PRIVATE_KEY,
            chain_id=config.CHAIN_ID,
            creds=creds,
            signature_type=0  # EOA 钱包
        )

        # 发送请求：查询余额
        print("正在向交易所查询资金...")
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=0)
        balance_info = client.get_balance_allowance(params)
        
        # 解析余额 (单位是最小单位，需要除以 10^6 转换为 USDC)
        balance_usdc = int(balance_info.get('balance', 0)) / 1_000_000
        
        # 打印结果
        print("\n===============================")
        print(f"✅ 连接成功！Moltbot 在线")
        print(f"🏠 钱包地址: {client.get_address()}")
        print(f"💰 账户余额: {balance_usdc} USDC")
        print("===============================\n")

    except Exception as e:
        print(f"❌ 连接失败: {e}")

if __name__ == "__main__":
    main()
