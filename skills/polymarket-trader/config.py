"""
Polymarket API 配置
从环境变量读取凭证，避免硬编码敏感信息
"""
import os

# Polymarket CLOB API 凭证
API_KEY = os.environ.get("POLYMARKET_API_KEY", "")
API_SECRET = os.environ.get("POLYMARKET_API_SECRET", "")
API_PASSPHRASE = os.environ.get("POLYMARKET_API_PASSPHRASE", "")

# 钱包私钥
PRIVATE_KEY = os.environ.get("POLYMARKET_PRIVATE_KEY", "")

# Polymarket 配置
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon
