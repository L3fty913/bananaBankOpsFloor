import os
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv('/opt/polybot/.env')
pk=os.getenv('POLYGON_WALLET_PRIVATE_KEY')
acct=Account.from_key(pk)
addr=acct.address
rpcs=['https://polygon-rpc.com','https://rpc.ankr.com/polygon','https://polygon.llamarpc.com']
w3=None
for rpc in rpcs:
    try:
        cand=Web3(Web3.HTTPProvider(rpc,request_kwargs={'timeout':20}))
        if cand.is_connected():
            w3=cand
            print('rpc',rpc)
            break
    except Exception:
        pass
if w3 is None:
    raise RuntimeError('No Polygon RPC available')
ct_addr=Web3.to_checksum_address('0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')
ops=[
 '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',
 '0xC5d563A36AE78145C45a50134d48A1215220f80a',
 '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296',
]
abi=[
 {"inputs":[{"internalType":"address","name":"account","type":"address"},{"internalType":"address","name":"operator","type":"address"}],"name":"isApprovedForAll","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"operator","type":"address"},{"internalType":"bool","name":"approved","type":"bool"}],"name":"setApprovalForAll","outputs":[],"stateMutability":"nonpayable","type":"function"}
]
ct=w3.eth.contract(address=ct_addr,abi=abi)
nonce=w3.eth.get_transaction_count(addr)
print('wallet',addr,'nonce',nonce)
for op in ops:
    op=Web3.to_checksum_address(op)
    ok=ct.functions.isApprovedForAll(addr,op).call()
    print('before',op,ok)
    if ok:
        continue
    tx=ct.functions.setApprovalForAll(op,True).build_transaction({
        'from': addr,
        'nonce': nonce,
        'gas': 150000,
        'maxFeePerGas': w3.to_wei('200','gwei'),
        'maxPriorityFeePerGas': w3.to_wei('40','gwei'),
        'chainId': 137,
    })
    signed=w3.eth.account.sign_transaction(tx,pk)
    h=w3.eth.send_raw_transaction(signed.raw_transaction)
    print('sent',h.hex())
    rc=w3.eth.wait_for_transaction_receipt(h,timeout=180)
    print('receipt',rc.status,'gasUsed',rc.gasUsed)
    nonce += 1
    print('after',op,ct.functions.isApprovedForAll(addr,op).call())
