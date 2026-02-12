#!/usr/bin/env python3
import os, inspect
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import AMOY, POLYGON
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
print(f"Wallet: {acct.address}")

# Check what ClobClient __init__ expects
sig = inspect.signature(ClobClient.__init__)
print(f"\nClobClient.__init__ params: {sig}")

# Try with signature_type and funder
from py_clob_client.clob_types import ApiCreds
import py_clob_client.clob_types as ct

# List all exports from clob_types
print(f"\nclob_types exports: {[x for x in dir(ct) if not x.startswith('_')]}")

# Try creating client with signature_type
try:
    client = ClobClient(
        "https://clob.polymarket.com",
        key=pk,
        chain_id=POLYGON,
        signature_type=1,  # POLY_GNOSIS_SAFE
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    print(f"\nClient created with sig_type=1")
    
    try:
        result = client.update_balance_allowance()
        print(f"update_balance_allowance: {result}")
    except Exception as e:
        print(f"update_balance_allowance error: {e}")
    
    try:
        result = client.get_balance_allowance()
        print(f"get_balance_allowance: {result}")
    except Exception as e:
        print(f"get_balance_allowance error: {e}")

except Exception as e:
    print(f"Client creation error: {e}")

# Try with signature_type=0 (EOA)
try:
    client2 = ClobClient(
        "https://clob.polymarket.com",
        key=pk,
        chain_id=POLYGON,
        signature_type=0,  # EOA
    )
    client2.set_api_creds(client2.create_or_derive_api_creds())
    print(f"\nClient created with sig_type=0 (EOA)")
    
    try:
        result = client2.update_balance_allowance()
        print(f"update_balance_allowance: {result}")
    except Exception as e:
        print(f"update_balance_allowance error: {e}")

    try:
        result = client2.get_balance_allowance()
        print(f"get_balance_allowance: {result}")
    except Exception as e:
        print(f"get_balance_allowance error: {e}")

except Exception as e:
    print(f"Client creation error: {e}")
