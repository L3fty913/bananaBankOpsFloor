"""
Polymarket Real-Time Scalping Bot v1
=====================================
Strategy: Monitor high-volume markets via WebSocket for sudden price 
dislocations (large spread widening, panic dumps, news-driven spikes).
Buy the dip, sell the rip. In and out in seconds.

Approach:
1. Track top liquid markets via WebSocket price_change feed
2. Maintain rolling price averages
3. When price drops X% below rolling avg → BUY
4. When price recovers to avg or above → SELL
5. Hard stop-loss to limit downside

Also watches for:
- Spread collapse opportunities (wide spread → place limit buy at bid, flip at ask)
- Cross-pair divergence in related markets
"""

import asyncio
import json
import os
import time
import hmac
import hashlib
import base64
import requests
import websockets
from datetime import datetime, timezone
from collections import deque
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from eth_account import Account

load_dotenv("/home/codespace/.openclaw/workspace/polymarket/.env")

# ============================================================
# CONFIG
# ============================================================
PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
API_KEY = os.getenv("POLYMARKET_API_KEY")
API_SECRET = os.getenv("POLYMARKET_SECRET")
API_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE")

CLOB_HOST = "https://clob.polymarket.com"
WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API = "https://gamma-api.polymarket.com"
CHAIN_ID = 137

# Scalping parameters
PRICE_WINDOW = 20          # Rolling window size for price tracking
DIP_THRESHOLD = 0.03       # Buy when price drops 3% below rolling avg
PROFIT_TARGET = 0.02       # Sell when 2% above entry
STOP_LOSS = 0.04           # Cut loss at 4% below entry
MAX_POSITION_USDC = 25.0   # Max per position
MIN_SPREAD_BPS = 200       # Min spread (bps) to consider spread capture
MIN_LIQUIDITY = 5000       # Min volume to consider a market

# ============================================================
# SETUP CLOB CLIENT
# ============================================================
def setup_client():
    client = ClobClient(
        CLOB_HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client

# ============================================================
# FIND HOT MARKETS (high volume, liquid, active)
# ============================================================
def find_hot_markets(limit=20):
    """Get the most liquid active markets for scalping"""
    all_markets = []
    for offset in range(0, 300, 100):
        resp = requests.get(f"{GAMMA_API}/markets", params={
            "limit": 100, "offset": offset, 
            "active": "true", "closed": "false",
            "order": "volume", "ascending": "false"
        }, timeout=15)
        if resp.status_code == 200:
            all_markets.extend(resp.json())
        time.sleep(0.3)
    
    # Filter for liquid markets with decent spread opportunity
    candidates = []
    for m in all_markets:
        tokens_raw = m.get("clobTokenIds")
        prices_raw = m.get("outcomePrices")
        volume = float(m.get("volume", 0) or 0)
        liquidity = float(m.get("liquidity", 0) or 0)
        
        if volume < MIN_LIQUIDITY:
            continue
            
        if isinstance(tokens_raw, str):
            try:
                tokens = json.loads(tokens_raw)
            except:
                continue
        else:
            tokens = tokens_raw
        
        if isinstance(prices_raw, str):
            try:
                prices = [float(p) for p in json.loads(prices_raw)]
            except:
                continue
        else:
            prices = [float(p) for p in prices_raw] if prices_raw else []
        
        if not tokens or not prices or len(tokens) < 2:
            continue
        
        # Prefer markets with mid-range prices (more volatility)
        yes_price = prices[0]
        if 0.15 <= yes_price <= 0.85:  # mid-range = more movement
            candidates.append({
                "question": m.get("question", ""),
                "condition_id": m.get("conditionId", ""),
                "yes_token": tokens[0],
                "no_token": tokens[1],
                "yes_price": yes_price,
                "volume": volume,
                "liquidity": liquidity,
                "spread": m.get("spread"),
            })
    
    # Sort by volume descending
    candidates.sort(key=lambda x: x["volume"], reverse=True)
    return candidates[:limit]

# ============================================================
# PRICE TRACKER
# ============================================================
class PriceTracker:
    def __init__(self):
        self.prices = {}      # token_id -> deque of (timestamp, price)
        self.positions = {}   # token_id -> {entry_price, size, side}
        self.pnl = 0.0
        self.trades = []
    
    def update(self, token_id, price, timestamp):
        if token_id not in self.prices:
            self.prices[token_id] = deque(maxlen=PRICE_WINDOW)
        self.prices[token_id].append((timestamp, price))
    
    def get_avg(self, token_id):
        if token_id not in self.prices or len(self.prices[token_id]) < 3:
            return None
        prices = [p for _, p in self.prices[token_id]]
        return sum(prices) / len(prices)
    
    def get_signals(self, token_id, current_bid, current_ask):
        """Generate trading signals"""
        signals = []
        avg = self.get_avg(token_id)
        if avg is None:
            return signals
        
        spread = current_ask - current_bid if (current_ask and current_bid) else 0
        spread_pct = spread / current_ask if current_ask else 0
        mid = (current_bid + current_ask) / 2 if (current_bid and current_ask) else 0
        
        # Signal 1: Price dip below rolling average
        if current_ask and avg > 0:
            dip = (avg - current_ask) / avg
            if dip >= DIP_THRESHOLD and token_id not in self.positions:
                signals.append({
                    "type": "DIP_BUY",
                    "token_id": token_id,
                    "price": current_ask,
                    "avg": avg,
                    "dip_pct": dip * 100,
                    "reason": f"Price ${current_ask:.4f} is {dip*100:.1f}% below avg ${avg:.4f}"
                })
        
        # Signal 2: Wide spread capture (place limit buy at bid, sell at ask)
        if spread_pct >= MIN_SPREAD_BPS / 10000 and token_id not in self.positions:
            signals.append({
                "type": "SPREAD_CAPTURE",
                "token_id": token_id,
                "bid": current_bid,
                "ask": current_ask,
                "spread": spread,
                "spread_pct": spread_pct * 100,
                "reason": f"Spread ${spread:.4f} ({spread_pct*100:.1f}%) — buy@bid sell@ask"
            })
        
        # Signal 3: Exit existing position
        if token_id in self.positions:
            pos = self.positions[token_id]
            entry = pos["entry_price"]
            
            if current_bid:
                pnl_pct = (current_bid - entry) / entry
                
                if pnl_pct >= PROFIT_TARGET:
                    signals.append({
                        "type": "TAKE_PROFIT",
                        "token_id": token_id,
                        "entry": entry,
                        "exit_price": current_bid,
                        "pnl_pct": pnl_pct * 100,
                        "reason": f"Profit target hit: +{pnl_pct*100:.1f}%"
                    })
                elif pnl_pct <= -STOP_LOSS:
                    signals.append({
                        "type": "STOP_LOSS",
                        "token_id": token_id,
                        "entry": entry,
                        "exit_price": current_bid,
                        "pnl_pct": pnl_pct * 100,
                        "reason": f"Stop loss hit: {pnl_pct*100:.1f}%"
                    })
        
        return signals

# ============================================================
# ORDER EXECUTION  
# ============================================================
def execute_buy(client, token_id, price, size_usdc):
    """Place a buy order"""
    try:
        shares = size_usdc / price
        order_args = OrderArgs(
            price=price,
            size=shares,
            side="BUY",
            token_id=token_id,
        )
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
        return resp
    except Exception as e:
        print(f"  ❌ Buy order failed: {e}")
        return None

def execute_sell(client, token_id, price, size_shares):
    """Place a sell order"""
    try:
        order_args = OrderArgs(
            price=price,
            size=size_shares,
            side="SELL",
            token_id=token_id,
        )
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.GTC)
        return resp
    except Exception as e:
        print(f"  ❌ Sell order failed: {e}")
        return None

# ============================================================
# MAIN WEBSOCKET LOOP
# ============================================================
async def run_scalper():
    print("="*60)
    print("POLYMARKET SCALPER v1")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("="*60)
    
    # Setup
    client = setup_client()
    tracker = PriceTracker()
    
    account = Account.from_key(PRIVATE_KEY)
    print(f"Wallet: {account.address}")
    
    # Find hot markets
    print("\nFinding liquid markets to monitor...")
    hot_markets = find_hot_markets(limit=15)
    
    if not hot_markets:
        print("No suitable markets found!")
        return
    
    # Build token -> market lookup
    token_to_market = {}
    asset_ids = []
    for m in hot_markets:
        token_to_market[m["yes_token"]] = m
        token_to_market[m["no_token"]] = m
        asset_ids.append(m["yes_token"])
        # Also track NO token for spread analysis
        asset_ids.append(m["no_token"])
    
    print(f"\nMonitoring {len(hot_markets)} markets:")
    for m in hot_markets[:10]:
        print(f"  📊 {m['question'][:60]}")
        print(f"     Price: ${m['yes_price']:.4f} | Vol: ${m['volume']:,.0f} | Liq: ${m['liquidity']:,.0f}")
    
    # Connect to WebSocket
    print(f"\n🔌 Connecting to WebSocket...")
    
    subscribe_msg = {
        "assets_ids": asset_ids,
        "type": "MARKET",
        "custom_feature_enabled": True,
    }
    
    reconnect_delay = 1
    max_reconnect = 30
    
    while True:
        try:
            async with websockets.connect(WSS_URL, ping_interval=30) as ws:
                print("✅ WebSocket connected")
                reconnect_delay = 1
                
                # Subscribe
                await ws.send(json.dumps(subscribe_msg))
                print(f"📡 Subscribed to {len(asset_ids)} assets")
                
                signal_count = 0
                msg_count = 0
                
                async for raw_msg in ws:
                    try:
                        msgs = json.loads(raw_msg)
                        if not isinstance(msgs, list):
                            msgs = [msgs]
                        
                        for msg in msgs:
                            event_type = msg.get("event_type")
                            asset_id = msg.get("asset_id")
                            
                            msg_count += 1
                            if msg_count % 100 == 0:
                                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                print(f"  [{now}] {msg_count} messages processed | Signals: {signal_count} | PnL: ${tracker.pnl:.4f}")
                            
                            if event_type == "book" and asset_id:
                                bids = msg.get("bids", [])
                                asks = msg.get("asks", [])
                                
                                best_bid = float(bids[0]["price"]) if bids else None
                                best_ask = float(asks[0]["price"]) if asks else None
                                
                                if best_ask:
                                    tracker.update(asset_id, best_ask, time.time())
                                
                                # Check for signals
                                if best_bid and best_ask:
                                    signals = tracker.get_signals(asset_id, best_bid, best_ask)
                                    
                                    for sig in signals:
                                        signal_count += 1
                                        market_info = token_to_market.get(asset_id, {})
                                        market_q = market_info.get("question", "Unknown")[:50]
                                        
                                        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                        
                                        if sig["type"] == "DIP_BUY":
                                            print(f"\n  🔥 [{now}] DIP BUY SIGNAL: {market_q}")
                                            print(f"     {sig['reason']}")
                                            
                                            # Execute buy
                                            size = min(MAX_POSITION_USDC, 20.0)
                                            result = execute_buy(client, asset_id, sig["price"], size)
                                            if result:
                                                shares = size / sig["price"]
                                                tracker.positions[asset_id] = {
                                                    "entry_price": sig["price"],
                                                    "size": shares,
                                                    "side": "BUY",
                                                    "entry_time": time.time(),
                                                }
                                                print(f"     ✅ Bought {shares:.2f} shares @ ${sig['price']:.4f} = ${size:.2f}")
                                                tracker.trades.append({
                                                    "time": now, "type": "BUY",
                                                    "market": market_q, "price": sig["price"],
                                                    "size": size
                                                })
                                        
                                        elif sig["type"] == "SPREAD_CAPTURE":
                                            print(f"\n  📐 [{now}] SPREAD SIGNAL: {market_q}")
                                            print(f"     {sig['reason']}")
                                            # For spread capture, place limit buy at bid
                                            size = min(MAX_POSITION_USDC, 15.0)
                                            result = execute_buy(client, asset_id, sig["bid"], size)
                                            if result:
                                                shares = size / sig["bid"]
                                                tracker.positions[asset_id] = {
                                                    "entry_price": sig["bid"],
                                                    "size": shares,
                                                    "side": "BUY",
                                                    "entry_time": time.time(),
                                                    "target_sell": sig["ask"],
                                                }
                                                print(f"     ✅ Limit buy {shares:.2f} @ ${sig['bid']:.4f}")
                                                tracker.trades.append({
                                                    "time": now, "type": "SPREAD_BUY",
                                                    "market": market_q, "price": sig["bid"],
                                                    "size": size
                                                })
                                        
                                        elif sig["type"] in ("TAKE_PROFIT", "STOP_LOSS"):
                                            pos = tracker.positions.get(asset_id)
                                            if pos:
                                                emoji = "💰" if sig["type"] == "TAKE_PROFIT" else "🛑"
                                                print(f"\n  {emoji} [{now}] {sig['type']}: {market_q}")
                                                print(f"     {sig['reason']}")
                                                
                                                result = execute_sell(client, asset_id, sig["exit_price"], pos["size"])
                                                if result:
                                                    pnl = (sig["exit_price"] - pos["entry_price"]) * pos["size"]
                                                    tracker.pnl += pnl
                                                    print(f"     ✅ Sold {pos['size']:.2f} @ ${sig['exit_price']:.4f} | Trade PnL: ${pnl:.4f} | Total: ${tracker.pnl:.4f}")
                                                    tracker.trades.append({
                                                        "time": now, "type": "SELL",
                                                        "market": market_q, "price": sig["exit_price"],
                                                        "pnl": pnl
                                                    })
                                                    del tracker.positions[asset_id]
                            
                            elif event_type == "price_change" and msg.get("price_changes"):
                                for pc in msg["price_changes"]:
                                    pc_asset = pc.get("asset_id")
                                    best_bid = float(pc.get("best_bid", 0)) if pc.get("best_bid") else None
                                    best_ask = float(pc.get("best_ask", 0)) if pc.get("best_ask") else None
                                    
                                    if pc_asset and best_ask:
                                        tracker.update(pc_asset, best_ask, time.time())
                                    
                                    if pc_asset and best_bid and best_ask:
                                        signals = tracker.get_signals(pc_asset, best_bid, best_ask)
                                        for sig in signals:
                                            signal_count += 1
                                            market_info = token_to_market.get(pc_asset, {})
                                            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                            print(f"  ⚡ [{now}] {sig['type']}: {sig['reason']}")
                            
                            elif event_type == "last_trade_price":
                                price = float(msg.get("price", 0))
                                if asset_id and price > 0:
                                    tracker.update(asset_id, price, time.time())
                    
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"  Error processing message: {e}")
                        continue
        
        except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
            print(f"\n⚠️ WebSocket disconnected: {e}")
            print(f"   Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_scalper())
