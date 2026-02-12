#!/usr/bin/env python3
import os, inspect
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
wallet = acct.address
print(f"Wallet: {wallet}")

# Check AssetType values
print(f"\nAssetType members: {[a for a in dir(AssetType) if not a.startswith('_')]}")
try:
    print(f"AssetType values: {list(AssetType)}")
except:
    for a in dir(AssetType):
        if not a.startswith('_'):
            print(f"  AssetType.{a} = {getattr(AssetType, a)}")

# Check BalanceAllowanceParams
print(f"\nBalanceAllowanceParams fields:")
print(inspect.getsource(BalanceAllowanceParams))

client = ClobClient(
    "https://clob.polymarket.com",
    key=pk,
    chain_id=137,
    signature_type=0,
    funder=wallet,
)
client.set_api_creds(client.create_or_derive_api_creds())

# Try COLLATERAL asset type
for at in [AssetType.COLLATERAL if hasattr(AssetType, 'COLLATERAL') else None,
           AssetType.CONDITIONAL if hasattr(AssetType, 'CONDITIONAL') else None]:
    if at is None:
        continue
    print(f"\nTrying asset_type={at}...")
    params = BalanceAllowanceParams(asset_type=at, token_id="", signature_type=0)
    try:
        result = client.get_balance_allowance(params)
        print(f"Balance/Allowance: {result}")
    except Exception as e:
        print(f"Error: {e}")
    
    print(f"Updating allowance for {at}...")
    try:
        result = client.update_balance_allowance(params)
        print(f"Update: {result}")
    except Exception as e:
        print(f"Error: {e}")
