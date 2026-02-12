#!/usr/bin/env python3
import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

CLOB_HOST = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
CHAIN_ID = 137


def best_bid(token_id: str):
    r = requests.get(f"{CLOB_HOST}/book", params={"token_id": token_id}, timeout=20)
    r.raise_for_status()
    book = r.json()
    bids = book.get("bids") or []
    if not bids:
        return None
    return max(float(b["price"]) for b in bids if b.get("price") is not None)


def get_positions(wallet: str):
    r = requests.get(f"{DATA_API}/positions", params={"user": wallet}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    out = []
    for p in rows:
        size = float(p.get("size") or 0)
        if size <= 0:
            continue
        out.append({
            "token_id": str(p.get("asset")),
            "size": size,
            "title": p.get("title") or "",
            "current_value": float(p.get("currentValue") or 0),
        })
    return out


def main():
    load_dotenv("/home/codespace/.openclaw/workspace/polymarket/.env")
    pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    if not pk:
        raise RuntimeError("Missing POLYGON_WALLET_PRIVATE_KEY in polymarket/.env")

    client = ClobClient(CLOB_HOST, key=pk, chain_id=CHAIN_ID)
    client.set_api_creds(client.create_or_derive_api_creds())
    wallet = client.get_api_keys().get("address") if hasattr(client, "get_api_keys") else None

    # Safer: derive wallet from private key using client signer path (address may not be in api keys)
    from eth_account import Account
    wallet = Account.from_key(pk).address

    positions = get_positions(wallet)
    print(f"Wallet: {wallet}")
    print(f"Open positions: {len(positions)}")

    sold = 0
    skipped = 0
    for p in positions:
        token_id = p["token_id"]
        size = round(float(p["size"]), 2)
        title = p["title"][:80]

        if size <= 0:
            skipped += 1
            continue

        bid = best_bid(token_id)
        if not bid or bid <= 0:
            print(f"SKIP no bid | size={size} | {title}")
            skipped += 1
            continue

        try:
            order_args = OrderArgs(price=round(bid, 4), size=size, side="SELL", token_id=token_id)
            signed = client.create_order(order_args)
            resp = client.post_order(signed, OrderType.FAK)
            print(f"SELL size={size} @ {bid:.4f} | {title} | resp={resp}")
            sold += 1
        except Exception as e:
            print(f"FAIL size={size} @ {bid:.4f} | {title} | err={e}")

    print(f"Done. attempted={len(positions)} sold_calls={sold} skipped={skipped}")


if __name__ == "__main__":
    main()
