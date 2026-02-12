#!/usr/bin/env python3
"""Approve USDC and deposit into Polymarket exchange via proxy wallet"""
import os, json, time
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

load_dotenv("/opt/polybot/.env")
pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
acct = Account.from_key(pk)
wallet = acct.address
print(f"Wallet: {wallet}")

# Try multiple RPCs
rpcs = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://rpc-mainnet.maticvigil.com",
    "https://polygon.meowrpc.com",
    "https://polygon.drpc.org",
]

w3 = None
for rpc in rpcs:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
        if w3.is_connected():
            cid = w3.eth.chain_id
            print(f"Connected to {rpc} (chain {cid})")
            break
        else:
            w3 = None
    except Exception as e:
        print(f"Failed {rpc}: {e}")
        w3 = None

if not w3:
    print("ERROR: Could not connect to any Polygon RPC")
    exit(1)

USDC_NATIVE = Web3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")

# Polymarket CTF Exchange and Neg Risk Exchange
CTF_EXCHANGE = Web3.to_checksum_address("0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E")
NEG_RISK_EXCHANGE = Web3.to_checksum_address("0xC5d563A36AE78145C45a50134d48A1215220f80a")
THIRD_CONTRACT = Web3.to_checksum_address("0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296")

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')

usdc = w3.eth.contract(address=USDC_NATIVE, abi=ERC20_ABI)
balance = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
decimals = usdc.functions.decimals().call()
print(f"\nUSDC balance: {balance / 10**decimals:.6f}")

MAX_UINT256 = 2**256 - 1

for label, spender in [("CTF Exchange", CTF_EXCHANGE), ("Neg Risk Exchange", NEG_RISK_EXCHANGE), ("Third Contract", THIRD_CONTRACT)]:
    current = usdc.functions.allowance(Web3.to_checksum_address(wallet), spender).call()
    print(f"\n{label} ({spender}):")
    print(f"  Current allowance: {current / 10**decimals:.2f}")
    
    if current < balance:
        print(f"  Approving max USDC...")
        nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(wallet))
        tx = usdc.functions.approve(spender, MAX_UINT256).build_transaction({
            'from': Web3.to_checksum_address(wallet),
            'nonce': nonce,
            'gas': 60000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 137,
        })
        signed = w3.eth.account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"  TX sent: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        print(f"  Status: {'SUCCESS' if receipt['status'] == 1 else 'FAILED'}")
        time.sleep(2)
    else:
        print(f"  Already approved!")

# Now re-check via Polymarket API
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137, signature_type=0, funder=wallet)
client.set_api_creds(client.create_or_derive_api_creds())

params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=0)

print("\n--- Updating Polymarket balance/allowance cache ---")
try:
    client.update_balance_allowance(params)
    print("Update sent!")
except Exception as e:
    print(f"Update error: {e}")

print("\n--- Final balance check ---")
result = client.get_balance_allowance(params)
print(f"Polymarket sees: {result}")
bal = int(result.get('balance', '0'))
print(f"USDC on exchange: {bal / 1e6:.2f}")
