import asyncio
import json
import os
import time
import requests
import websockets
from datetime import datetime, timezone
from collections import deque
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType
from eth_account import Account

load_dotenv("/opt/polybot/.env")

PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
CLOB_HOST = "https://clob.polymarket.com"
WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API = "https://gamma-api.polymarket.com"
CHAIN_ID = 137

PRICE_WINDOW = 20
DIP_THRESHOLD = 0.04
# close quickly once net-positive after fee/slippage buffer
PROFIT_TARGET = 0.006
STOP_LOSS = 0.04
MAX_POSITION_USDC = 20.0
MIN_SPREAD_PCT = 0.03
SIGNAL_COOLDOWN = 60
WARMUP_MESSAGES = 300

def setup_client(funder):
    # IMPORTANT: use the same signature_type + funder path as go_live.py
    client = ClobClient(
        CLOB_HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=0,
        funder=funder,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client

def find_hot_markets(limit=15):
    all_markets = []
    for offset in range(0, 300, 100):
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={"limit": 100, "offset": offset, "active": "true", "closed": "false", "order": "volume", "ascending": "false"},
                timeout=15,
            )
            if resp.status_code == 200:
                all_markets.extend(resp.json())
        except Exception:
            pass
        time.sleep(0.3)

    candidates = []
    for m in all_markets:
        tokens_raw = m.get("clobTokenIds")
        prices_raw = m.get("outcomePrices")
        volume = float(m.get("volume", 0) or 0)
        liquidity = float(m.get("liquidity", 0) or 0)
        if volume < 5000 or liquidity < 1000:
            continue
        if isinstance(tokens_raw, str):
            try:
                tokens = json.loads(tokens_raw)
            except Exception:
                continue
        else:
            tokens = tokens_raw
        if isinstance(prices_raw, str):
            try:
                prices = [float(p) for p in json.loads(prices_raw)]
            except Exception:
                continue
        else:
            prices = [float(p) for p in prices_raw] if prices_raw else []
        if not tokens or not prices or len(tokens) < 2:
            continue
        question = (m.get("question", "") or "")
        ql = question.lower()
        # Primary lane: BTC-only directional/event markets
        if not ("bitcoin" in ql or " btc" in ql or ql.startswith("btc") or "btc " in ql):
            continue

        yes_price = prices[0]
        if 0.15 <= yes_price <= 0.85:
            candidates.append(
                {
                    "question": question,
                    "condition_id": m.get("conditionId", ""),
                    "yes_token": tokens[0],
                    "no_token": tokens[1],
                    "yes_price": yes_price,
                    "volume": volume,
                    "liquidity": liquidity,
                }
            )
    candidates.sort(key=lambda x: x["volume"], reverse=True)
    return candidates[:limit]


class PriceTracker:
    def __init__(self):
        self.prices = {}
        self.positions = {}
        self.pnl = 0.0
        self.trades = []
        self.last_signal = {}
        self.msg_count = 0

    def update(self, token_id, price, ts):
        if token_id not in self.prices:
            self.prices[token_id] = deque(maxlen=PRICE_WINDOW)
        self.prices[token_id].append((ts, price))

    def get_avg(self, token_id):
        if token_id not in self.prices or len(self.prices[token_id]) < PRICE_WINDOW:
            return None
        return sum(p for _, p in self.prices[token_id]) / len(self.prices[token_id])

    def get_signals(self, token_id, best_bid, best_ask):
        signals = []
        if self.msg_count < WARMUP_MESSAGES:
            return signals
        avg = self.get_avg(token_id)
        if avg is None:
            return signals
        now = time.time()
        if token_id in self.last_signal and (now - self.last_signal[token_id]) < SIGNAL_COOLDOWN:
            return signals

        spread = best_ask - best_bid
        spread_pct = spread / best_ask if best_ask else 0

        if best_ask and avg > 0:
            dip = (avg - best_ask) / avg
            if dip >= DIP_THRESHOLD and token_id not in self.positions:
                signals.append(
                    {
                        "type": "DIP_BUY",
                        "token_id": token_id,
                        "price": best_ask,
                        "avg": avg,
                        "dip_pct": dip * 100,
                        "reason": f"Price ${best_ask:.4f} is {dip*100:.1f}% below avg ${avg:.4f}",
                    }
                )

        if spread_pct >= MIN_SPREAD_PCT and token_id not in self.positions:
            signals.append(
                {
                    "type": "SPREAD_CAPTURE",
                    "token_id": token_id,
                    "bid": best_bid,
                    "ask": best_ask,
                    "spread": spread,
                    "reason": f"Spread ${spread:.4f} ({spread_pct*100:.1f}%)",
                }
            )

        if token_id in self.positions:
            pos = self.positions[token_id]
            entry = pos["entry_price"]
            if best_bid:
                pnl_pct = (best_bid - entry) / entry
                if pnl_pct >= PROFIT_TARGET:
                    signals.append(
                        {
                            "type": "TAKE_PROFIT",
                            "token_id": token_id,
                            "entry": entry,
                            "exit_price": best_bid,
                            "pnl_pct": pnl_pct * 100,
                            "reason": f"TP hit: +{pnl_pct*100:.1f}%",
                        }
                    )
                elif pnl_pct <= -STOP_LOSS:
                    signals.append(
                        {
                            "type": "STOP_LOSS",
                            "token_id": token_id,
                            "entry": entry,
                            "exit_price": best_bid,
                            "pnl_pct": pnl_pct * 100,
                            "reason": f"SL hit: {pnl_pct*100:.1f}%",
                        }
                    )

        if signals:
            self.last_signal[token_id] = now
        return signals


def clamp_price(price):
    # Polymarket CLOB price bounds are [0.01, 0.99]
    return round(min(0.99, max(0.01, float(price))), 4)


def get_token_balance(client, token_id):
    try:
        params = BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL,
            token_id=token_id,
            signature_type=0,
        )
        r = client.get_balance_allowance(params)
        bal = int(r.get("balance", "0"))
        # conditional token balance is in 1e6 precision
        return bal / 1e6
    except Exception as e:
        print(f"  BALANCE CHECK FAILED ({token_id[:8]}...): {e}")
        return 0.0


def get_usdc_balance(client):
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=0)
        r = client.get_balance_allowance(params)
        return int(r.get("balance", "0")) / 1e6
    except Exception as e:
        print(f"  USDC BALANCE CHECK FAILED: {e}")
        return 0.0


def execute_buy(client, token_id, price, size_usdc):
    try:
        available = get_usdc_balance(client)
        if available <= 0.2:
            print("  BUY SKIP: insufficient USDC available")
            return None, None, 0.0

        # keep 10% cash buffer + never exceed requested size
        safe_size = min(size_usdc, max(0.0, available * 0.90))
        if safe_size < 1.0:
            print(f"  BUY SKIP: size too small after balance cap (${safe_size:.2f})")
            return None, None, safe_size

        px = clamp_price(price)
        shares = round(safe_size / px, 2)
        order_args = OrderArgs(price=px, size=shares, side="BUY", token_id=token_id)
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.GTC)
        return resp, px, safe_size
    except Exception as e:
        print(f"  BUY FAILED: {e}")
        return None, None, 0.0


def execute_sell(client, token_id, price, size_shares):
    try:
        px = clamp_price(price)
        sz = round(size_shares, 2)
        onchain_bal = get_token_balance(client, token_id)
        if onchain_bal <= 0:
            print(f"  SELL SKIP: no token balance for {token_id[:8]}...")
            return None, px
        sell_size = min(sz, round(onchain_bal, 2))
        if sell_size <= 0:
            print(f"  SELL SKIP: computed size 0 for {token_id[:8]}...")
            return None, px

        order_args = OrderArgs(price=px, size=sell_size, side="SELL", token_id=token_id)
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.GTC)
        return resp, px
    except Exception as e:
        print(f"  SELL FAILED: {e}")
        return None, None


async def run_scalper():
    print("=" * 60)
    print("POLYMARKET SCALPER v2 - Amsterdam")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    account = Account.from_key(PRIVATE_KEY)
    print(f"Wallet: {account.address}")

    client = setup_client(funder=account.address)
    tracker = PriceTracker()

    # quick collateral sanity check (USDC)
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=0)
        r = client.get_balance_allowance(params)
        print(f"USDC Balance/Allowance: {r}")
    except Exception as e:
        print(f"USDC balance check failed: {e}")

    print("\nFinding hot markets...")
    hot_markets = find_hot_markets(15)
    if not hot_markets:
        print("No markets found!")
        return

    token_map = {}
    asset_ids = []
    for m in hot_markets:
        token_map[m["yes_token"]] = m
        token_map[m["no_token"]] = m
        asset_ids.extend([m["yes_token"], m["no_token"]])

    print(f"\nMonitoring {len(hot_markets)} markets:")
    for m in hot_markets[:10]:
        q = m["question"][:60]
        print(f"  {q}")
        print(f"    Price: ${m['yes_price']:.2f} | Vol: ${m['volume']:,.0f} | Liq: ${m['liquidity']:,.0f}")

    subscribe_msg = {"assets_ids": asset_ids, "type": "MARKET", "custom_feature_enabled": True}

    while True:
        try:
            async with websockets.connect(WSS_URL, ping_interval=30) as ws:
                print("\nWebSocket connected")
                await ws.send(json.dumps(subscribe_msg))
                print(f"Subscribed to {len(asset_ids)} assets")
                print(f"Warming up ({WARMUP_MESSAGES} msgs)...\n")

                async for raw_msg in ws:
                    try:
                        msgs = json.loads(raw_msg)
                        if not isinstance(msgs, list):
                            msgs = [msgs]

                        for msg in msgs:
                            evt = msg.get("event_type")
                            aid = msg.get("asset_id")
                            tracker.msg_count += 1

                            if tracker.msg_count == WARMUP_MESSAGES:
                                print("\n*** WARMUP COMPLETE - TRADING LIVE ***\n")

                            if tracker.msg_count % 500 == 0:
                                now_s = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                print(
                                    f"[{now_s}] msgs={tracker.msg_count} | pos={len(tracker.positions)} | trades={len(tracker.trades)} | PnL=${tracker.pnl:.4f}"
                                )

                            best_bid = best_ask = None

                            if evt == "book" and aid:
                                bids = msg.get("bids", [])
                                asks = msg.get("asks", [])
                                best_bid = float(bids[0]["price"]) if bids else None
                                best_ask = float(asks[0]["price"]) if asks else None
                                if best_ask:
                                    tracker.update(aid, best_ask, time.time())

                            elif evt == "price_change":
                                for pc in msg.get("price_changes", []):
                                    pc_aid = pc.get("asset_id")
                                    bb = float(pc.get("best_bid") or 0) or None
                                    ba = float(pc.get("best_ask") or 0) or None
                                    if pc_aid and ba:
                                        tracker.update(pc_aid, ba, time.time())
                                    if pc_aid and bb and ba:
                                        aid = pc_aid
                                        best_bid = bb
                                        best_ask = ba

                            elif evt == "last_trade_price" and aid:
                                p = float(msg.get("price", 0))
                                if p > 0:
                                    tracker.update(aid, p, time.time())
                                continue

                            if not (aid and best_bid and best_ask):
                                continue

                            signals = tracker.get_signals(aid, best_bid, best_ask)

                            for sig in signals:
                                minfo = token_map.get(aid, {})
                                mq = minfo.get("question", "?")[:50]
                                now_s = datetime.now(timezone.utc).strftime("%H:%M:%S")

                                if sig["type"] == "DIP_BUY":
                                    print(f"\n  DIP [{now_s}] {mq}")
                                    print(f"     {sig['reason']}")
                                    size = min(MAX_POSITION_USDC, 20.0)
                                    result, px, used_size = execute_buy(client, aid, sig["price"], size)
                                    if result and px:
                                        shares = used_size / px
                                        tracker.positions[aid] = {"entry_price": px, "size": shares, "entry_time": time.time()}
                                        print(f"     BOUGHT {shares:.2f} @ ${px:.4f} = ${used_size:.2f}")
                                        tracker.trades.append({"time": now_s, "type": "BUY", "market": mq, "price": px, "size": used_size})

                                elif sig["type"] == "SPREAD_CAPTURE":
                                    print(f"\n  SPREAD [{now_s}] {mq}")
                                    print(f"     {sig['reason']}")
                                    size = min(MAX_POSITION_USDC, 15.0)
                                    result, px, used_size = execute_buy(client, aid, sig["bid"], size)
                                    if result and px:
                                        shares = used_size / px
                                        tracker.positions[aid] = {"entry_price": px, "size": shares, "entry_time": time.time(), "target": sig["ask"]}
                                        print(f"     LIMIT BUY {shares:.2f} @ ${px:.4f}")
                                        tracker.trades.append({"time": now_s, "type": "SPREAD_BUY", "market": mq, "price": px, "size": used_size})

                                elif sig["type"] in ("TAKE_PROFIT", "STOP_LOSS"):
                                    pos = tracker.positions.get(aid)
                                    if pos:
                                        tag = "PROFIT" if sig["type"] == "TAKE_PROFIT" else "STOP"
                                        print(f"\n  {tag} [{now_s}] {mq}")
                                        print(f"     {sig['reason']}")
                                        result, px = execute_sell(client, aid, sig["exit_price"], pos["size"])
                                        if result and px:
                                            pnl = (px - pos["entry_price"]) * pos["size"]
                                            tracker.pnl += pnl
                                            print(f"     SOLD {pos['size']:.2f} @ ${px:.4f} | PnL: ${pnl:.4f} | Total: ${tracker.pnl:.4f}")
                                            tracker.trades.append({"time": now_s, "type": "SELL", "market": mq, "pnl": pnl})
                                            del tracker.positions[aid]

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"  Error: {e}")

        except Exception as e:
            print(f"\nDisconnected: {e}")
            print("Reconnecting in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_scalper())
