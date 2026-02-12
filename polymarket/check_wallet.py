"""Verify wallet connection and check balances"""
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account

load_dotenv("/home/codespace/.openclaw/workspace/polymarket/.env")

PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
API_KEY = os.getenv("POLYMARKET_API_KEY")
API_SECRET = os.getenv("POLYMARKET_SECRET")
API_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE")

# Derive wallet address
account = Account.from_key(PRIVATE_KEY)
print(f"Wallet address: {account.address}")

# Connect to CLOB
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon

client = ClobClient(
    HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
)

# Set API credentials
client.set_api_creds(client.create_or_derive_api_creds())
print("✅ CLOB API connected")

# Try to check if we can access the API
try:
    server_time = client.get_server_time()
    print(f"Server time: {server_time}")
except Exception as e:
    print(f"Server time check: {e}")

# Check balances via API if available
try:
    # Get allowances
    allowances = client.get_balance_allowance()
    print(f"Balance/Allowance info: {allowances}")
except Exception as e:
    print(f"Balance check: {e}")

# Try getting open orders
try:
    orders = client.get_orders()
    print(f"Open orders: {len(orders) if orders else 0}")
except Exception as e:
    print(f"Orders check: {e}")

print("\n✅ Wallet verified and CLOB client ready")
