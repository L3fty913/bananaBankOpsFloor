#!/usr/bin/env python3
import os, requests, json
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account
from web3 import Web3

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
wallet = acct.address
print(f"Wallet: {wallet}")

# Use ClobClient to check what methods exist
client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
client.set_api_creds(client.create_or_derive_api_creds())

# List all public methods
methods = sorted([m for m in dir(client) if not m.startswith('_')])
print(f"\nAll ClobClient methods:")
for m in methods:
    print(f"  {m}")

# Try on-chain with a working RPC
rpcs = [
    "https://1rpc.io/matic",
    "https://polygon-mainnet.g.alchemy.com/v2/demo",
    "https://endpoints.omniatech.io/v1/matic/mainnet/public",
]

USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')

for rpc in rpcs:
    try:
        print(f"\nTrying RPC: {rpc}")
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            print("  Not connected")
            continue
        print(f"  Connected! Chain ID: {w3.eth.chain_id}")
        
        matic = w3.eth.get_balance(Web3.to_checksum_address(wallet))
        print(f"  MATIC/POL: {matic / 10**18:.6f}")
        
        for label, addr in [("USDC.e", USDC_E), ("USDC native", USDC_NATIVE)]:
            c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ERC20_ABI)
            bal = c.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
            dec = c.functions.decimals().call()
            print(f"  {label} balance: {bal / 10**dec:.6f}")
            
            for exl, exa in [("CTF", CTF_EXCHANGE), ("NegRisk", NEG_RISK)]:
                allow = c.functions.allowance(Web3.to_checksum_address(wallet), Web3.to_checksum_address(exa)).call()
                print(f"    Allowance to {exl}: {allow / 10**dec:.2f}")
        
        break  # success
    except Exception as e:
        print(f"  Error: {e}")
        continue
