#!/usr/bin/env python3
"""Read-only BTC book snapshot collector for preflight numerics (no trading)."""
import os
import json
import time
import requests
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import TradeParams

load_dotenv('/opt/polybot/.env')
PK = os.getenv('POLYGON_WALLET_PRIVATE_KEY')
HOST = 'https://clob.polymarket.com'
CHAIN = 137
GAMMA = 'https://gamma-api.polymarket.com'


def get_client() -> Tuple[ClobClient, str]:
    wallet = Account.from_key(PK).address
    c = ClobClient(HOST, key=PK, chain_id=CHAIN, signature_type=0, funder=wallet)
    c.set_api_creds(c.create_or_derive_api_creds())
    return c, wallet


def find_btc_markets(limit: int = 5) -> List[Dict[str, Any]]:
    # Pull top-volume active markets; filter for BTC/Bitcoin
    out = []
    for offset in range(0, 300, 100):
        r = requests.get(
            f"{GAMMA}/markets",
            params={"limit": 100, "offset": offset, "active": "true", "closed": "false", "order": "volume", "ascending": "false"},
            timeout=15,
        )
        r.raise_for_status()
        mkts = r.json()
        for m in mkts:
            q = (m.get('question') or '')
            ql = q.lower()
            if 'bitcoin' not in ql and ' btc' not in ql and not ql.startswith('btc') and 'btc ' not in ql:
                continue
            out.append(m)
        if len(out) >= limit:
            break
        time.sleep(0.2)
    return out[:limit]


def parse_tokens(m: Dict[str, Any]) -> List[str]:
    raw = m.get('clobTokenIds')
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return list(raw)


def depth_3ticks(levels, tick: float = 0.01, side: str = 'bid') -> float:
    # Sum size within 3 ticks of best level.
    if not levels:
        return 0.0
    best_px = float(levels[0].price)
    total = 0.0
    for lv in levels:
        px = float(lv.price)
        sz = float(lv.size)
        if side == 'bid':
            if best_px - px <= 3 * tick + 1e-9:
                total += sz
        else:
            if px - best_px <= 3 * tick + 1e-9:
                total += sz
    return total


def last_trade_ts(c: ClobClient, token_id: str) -> int:
    try:
        trades = c.get_trades(TradeParams(asset_id=str(token_id), after=int(time.time()) - 6 * 3600))
        if not isinstance(trades, list) or not trades:
            return 0
        mt = 0
        for t in trades:
            try:
                mt = max(mt, int(t.get('match_time') or 0))
            except Exception:
                pass
        return mt
    except Exception:
        return 0


def snapshot() -> Dict[str, Any]:
    c, _ = get_client()
    mkts = find_btc_markets(limit=int(os.getenv('BTC_MARKET_LIMIT', '3')))
    rows = []
    for m in mkts:
        q = (m.get('question') or '')
        tokens = parse_tokens(m)
        for tid in tokens[:2]:
            try:
                ob = c.get_order_book(str(tid))
                bids = getattr(ob, 'bids', []) or []
                asks = getattr(ob, 'asks', []) or []
                bbp = float(bids[0].price) if bids else 0.0
                bbs = float(bids[0].size) if bids else 0.0
                bap = float(asks[0].price) if asks else 0.0
                bas = float(asks[0].size) if asks else 0.0
                d3b = depth_3ticks(bids, side='bid')
                d3a = depth_3ticks(asks, side='ask')
                lts = last_trade_ts(c, str(tid))
                rows.append({
                    'question': q[:120],
                    'token_id': str(tid),
                    'best_bid_price': bbp,
                    'best_bid_size': bbs,
                    'best_ask_price': bap,
                    'best_ask_size': bas,
                    'depth_3ticks_bid': d3b,
                    'depth_3ticks_ask': d3a,
                    'last_trade_ts': lts,
                })
            except Exception as e:
                rows.append({'question': q[:120], 'token_id': str(tid), 'error': str(e)})
    return {'ts': int(time.time()), 'rows': rows}


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
