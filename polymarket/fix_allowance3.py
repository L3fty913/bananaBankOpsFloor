#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
wallet = acct.address
print(f"Wallet: {wallet}")

client = ClobClient(
    "https://clob.polymarket.com",
    key=pk,
    chain_id=137,
    signature_type=0,
    funder=wallet,
)
client.set_api_creds(client.create_or_derive_api_creds())

# Create proper params - signature_type 0 = EOA
params = BalanceAllowanceParams(asset_type=None, token_id=None, signature_type=0)

print("\nGetting balance/allowance...")
try:
    result = client.get_balance_allowance(params)
    print(f"Balance/Allowance: {result}")
except Exception as e:
    print(f"get_balance_allowance error: {e}")

print("\nUpdating balance/allowance...")
try:
    result = client.update_balance_allowance(params)
    print(f"Update result: {result}")
except Exception as e:
    print(f"update_balance_allowance error: {e}")

# Try with signature_type=1 (POLY_GNOSIS_SAFE)
params2 = BalanceAllowanceParams(asset_type=None, token_id=None, signature_type=1)
print("\nGetting balance/allowance (sig_type=1)...")
try:
    result = client.get_balance_allowance(params2)
    print(f"Balance/Allowance: {result}")
except Exception as e:
    print(f"Error: {e}")
