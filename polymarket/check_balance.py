#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
client.set_api_creds(client.create_or_derive_api_creds())

acct = Account.from_key(pk)
print(f"Wallet: {acct.address}")

# Check allowances
try:
    a = client.get_allowances()
    print(f"Allowances: {a}")
except Exception as e:
    print(f"Allowances error: {e}")

# Try to set/update allowances
try:
    print("Setting max allowance...")
    result = client.set_allowances()
    print(f"Set allowances result: {result}")
except Exception as e:
    print(f"Set allowances error: {e}")

# Re-check
try:
    a = client.get_allowances()
    print(f"Allowances after set: {a}")
except Exception as e:
    print(f"Re-check error: {e}")
