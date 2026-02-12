#!/usr/bin/env python3
import os, json
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from eth_account import Account
from web3 import Web3

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
wallet = acct.address
print(f"Wallet: {wallet}")

# Connect to Polygon
w3 = Web3(Web3.HTTPProvider("https://polygon.llamarpc.com"))
print(f"Polygon connected: {w3.is_connected()}")

# USDC on Polygon
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (bridged)
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # native USDC

# Polymarket CTF Exchange
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
# Polymarket Neg Risk CTF Exchange  
NEG_RISK_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')

for label, addr in [("USDC.e", USDC), ("USDC native", USDC_NATIVE)]:
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ERC20_ABI)
    bal = contract.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
    decimals = contract.functions.decimals().call()
    print(f"\n{label} ({addr}):")
    print(f"  Balance: {bal / 10**decimals:.6f}")
    
    for exlabel, exaddr in [("CTF Exchange", CTF_EXCHANGE), ("Neg Risk Exchange", NEG_RISK_EXCHANGE)]:
        allowance = contract.functions.allowance(
            Web3.to_checksum_address(wallet),
            Web3.to_checksum_address(exaddr)
        ).call()
        print(f"  Allowance to {exlabel}: {allowance / 10**decimals:.6f}")

# MATIC balance for gas
matic = w3.eth.get_balance(Web3.to_checksum_address(wallet))
print(f"\nMATIC (POL) balance: {matic / 10**18:.6f}")

# Check ClobClient methods
client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
client.set_api_creds(client.create_or_derive_api_creds())
methods = [m for m in dir(client) if not m.startswith('_') and 'allow' in m.lower() or 'balance' in m.lower() or 'approve' in m.lower()]
print(f"\nClobClient relevant methods: {methods}")
