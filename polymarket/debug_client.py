#!/usr/bin/env python3
import os, inspect
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")

client = ClobClient(
    "https://clob.polymarket.com",
    key=pk,
    chain_id=137,
    signature_type=0,
    funder="0x0458bf63BDa7834D911cE20aF2b2b6A9089f7fBB",
)
client.set_api_creds(client.create_or_derive_api_creds())

# Check internals
print(f"client.signer: {client.signer}")
print(f"type(client.signer): {type(client.signer)}")
if client.signer:
    print(f"signer attrs: {[a for a in dir(client.signer) if not a.startswith('_')]}")
    if hasattr(client.signer, 'signature_type'):
        print(f"signer.signature_type: {client.signer.signature_type}")

# Look at update_balance_allowance source
print(f"\nupdate_balance_allowance source:")
try:
    src = inspect.getsource(client.update_balance_allowance)
    print(src[:2000])
except:
    print("Could not get source")

# Look at the contract_config
if hasattr(client, 'contract_config'):
    print(f"\ncontract_config: {client.contract_config}")
