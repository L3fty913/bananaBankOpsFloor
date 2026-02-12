#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
print(f"Wallet: {acct.address}")

client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
client.set_api_creds(client.create_or_derive_api_creds())

print("\nCalling update_balance_allowance()...")
try:
    result = client.update_balance_allowance()
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")

# Also check if there's a get_balance method or similar
print("\nChecking balance-related methods...")
for method_name in ['get_balance_allowance', 'get_collateral', 'get_funds']:
    m = getattr(client, method_name, None)
    if m:
        try:
            r = m()
            print(f"  {method_name}(): {r}")
        except Exception as e:
            print(f"  {method_name}(): Error - {e}")

# Try a test order to see if allowance is the issue
print("\nTrying to check available balance via API...")
import requests
try:
    # Check the CLOB API for balance info
    headers = client.create_level_2_headers("GET", "/balance")
    resp = requests.get(f"https://clob.polymarket.com/balance", headers=headers, timeout=10)
    print(f"  /balance: {resp.status_code} {resp.text}")
except Exception as e:
    print(f"  Error: {e}")
