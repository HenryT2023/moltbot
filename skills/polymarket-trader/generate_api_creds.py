#!/usr/bin/env python3
"""
Polymarket API 凭证生成器
使用钱包私钥自动派生 API 凭证
"""
import os
import sys
import getpass

# 设置代理
os.environ['https_proxy'] = 'http://127.0.0.1:7890'
os.environ['http_proxy'] = 'http://127.0.0.1:7890'

from py_clob_client.client import ClobClient

def main():
    print("=" * 50)
    print("Polymarket API 凭证生成器")
    print("=" * 50)
    print()
    print("请输入你的 MetaMask 钱包私钥")
    print("（私钥以 0x 开头，64 位十六进制字符）")
    print()
    
    private_key = getpass.getpass("私钥: ")
    
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    
    if len(private_key) != 66:
        print(f"错误: 私钥长度不正确 ({len(private_key)} 字符，应为 66)")
        sys.exit(1)
    
    print()
    print("正在连接 Polymarket...")
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137  # Polygon
        )
        
        print("正在派生 API 凭证...")
        creds = client.create_or_derive_api_creds()
        
        print()
        print("=" * 50)
        print("✅ API 凭证生成成功！")
        print("=" * 50)
        print()
        print("请将以下内容添加到 ~/.zshrc:")
        print()
        print(f'export POLYMARKET_API_KEY="{creds.api_key}"')
        print(f'export POLYMARKET_API_SECRET="{creds.api_secret}"')
        print(f'export POLYMARKET_API_PASSPHRASE="{creds.api_passphrase}"')
        print(f'export POLYMARKET_PRIVATE_KEY="{private_key}"')
        print()
        print("=" * 50)
        
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
