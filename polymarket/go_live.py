#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
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

# Check COLLATERAL (USDC) balance
params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=0)
print("\n--- BEFORE ---")
result = client.get_balance_allowance(params)
print(f"USDC Balance/Allowance: {result}")

# If balance > 0, set allowances
bal = int(result.get('balance', '0'))
if bal > 0:
    print(f"\nBalance detected: {bal / 1e6:.2f} USDC")
    print("Setting allowances...")
    update = client.update_balance_allowance(params)
    print(f"Update result: {update}")
    
    # Re-check
    print("\n--- AFTER ---")
    result2 = client.get_balance_allowance(params)
    print(f"USDC Balance/Allowance: {result2}")
else:
    print("\nBalance is still 0. USDC may not have arrived yet.")
    print("Check if it was sent on Polygon network (not Ethereum mainnet).")
