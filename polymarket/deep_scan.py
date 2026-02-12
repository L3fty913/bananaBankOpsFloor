"""
Deep scan: Focus on REAL arbitrage vs false signals.
The Macron/UK events look like cascading date markets (not mutually exclusive).
Need to find TRUE mutually exclusive multi-outcome events.

Also scan for: cross-market price discrepancies, stale prices.
"""
import requests
import json
import time
from datetime import datetime, timezone

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

def get_markets(limit=100, offset=0):
    resp = requests.get(f"{GAMMA_API}/markets", params={
        "limit": limit, "offset": offset, "active": "true", "closed": "false"
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()

def get_events(limit=100, offset=0):
    resp = requests.get(f"{GAMMA_API}/events", params={
        "limit": limit, "offset": offset, "active": "true", "closed": "false"
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()

def get_orderbook(token_id):
    try:
        resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def analyze_orderbook_spread(token_id):
    """Get bid/ask spread for a token"""
    book = get_orderbook(token_id)
    if not book:
        return None
    
    best_bid = None
    best_ask = None
    bid_depth = 0
    ask_depth = 0
    
    if book.get("bids"):
        bids = sorted(book["bids"], key=lambda x: float(x["price"]), reverse=True)
        if bids:
            best_bid = float(bids[0]["price"])
            for b in bids[:5]:
                bid_depth += float(b.get("size", 0))
    
    if book.get("asks"):
        asks = sorted(book["asks"], key=lambda x: float(x["price"]))
        if asks:
            best_ask = float(asks[0]["price"])
            for a in asks[:5]:
                ask_depth += float(a.get("size", 0))
    
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": (best_ask - best_bid) if (best_ask and best_bid) else None,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
    }

# ============================================================
# STRATEGY 1: Find mutually exclusive events where buying 
# all YES outcomes costs < $1.00
# Key: outcomes must be MUTUALLY EXCLUSIVE (only one can be true)
# ============================================================

print("="*60)
print("DEEP ARBITRAGE SCAN")
print(f"Time: {datetime.now(timezone.utc).isoformat()}")
print("="*60)

print("\n[1] Fetching events...")
all_events = []
for offset in range(0, 200, 50):
    evts = get_events(limit=50, offset=offset)
    if not evts:
        break
    all_events.extend(evts)
    time.sleep(0.5)
print(f"  Got {len(all_events)} events")

# Look for events with "groupItemTitle" patterns that suggest
# mutually exclusive outcomes (like "Who will win X?" with multiple candidates)
print("\n[2] Identifying mutually exclusive multi-outcome events...")

promising_events = []
for event in all_events:
    title = (event.get("title") or "").lower()
    markets = event.get("markets", [])
    
    if len(markets) < 2:
        continue
    
    # These keywords suggest mutually exclusive outcomes
    exclusive_keywords = [
        "who will win", "winner of", "next president", "next prime minister",
        "how many", "what will", "which", "where will", "when will",
        "how much", "price of", "between"
    ]
    
    is_exclusive = any(kw in title for kw in exclusive_keywords)
    
    # Also check if market questions suggest ranges (mutually exclusive)
    questions = [m.get("question", "").lower() for m in markets]
    has_ranges = any("between" in q or "less than" in q or "more than" in q for q in questions)
    
    if is_exclusive or has_ranges:
        # Get total YES prices
        total = 0
        valid = True
        for m in markets:
            prices_raw = m.get("outcomePrices")
            if isinstance(prices_raw, str):
                try:
                    prices = [float(p) for p in json.loads(prices_raw)]
                except:
                    valid = False
                    break
            elif prices_raw:
                prices = [float(p) for p in prices_raw]
            else:
                valid = False
                break
            total += prices[0]
        
        if valid and total > 0:
            promising_events.append({
                "title": event.get("title", "Unknown"),
                "num_markets": len(markets),
                "total_yes": total,
                "gap": abs(total - 1.0),
                "markets": markets,
                "is_under": total < 0.98,
                "is_over": total > 1.02,
            })

# Sort by gap size
promising_events.sort(key=lambda x: x["gap"], reverse=True)

print(f"  Found {len(promising_events)} mutually exclusive events")
print(f"  Underpriced: {sum(1 for e in promising_events if e['is_under'])}")
print(f"  Overpriced: {sum(1 for e in promising_events if e['is_over'])}")

for pe in promising_events[:15]:
    tag = "💰 UNDER" if pe["is_under"] else ("📉 OVER" if pe["is_over"] else "⚖️ FAIR")
    print(f"\n  {tag} | {pe['title']}")
    print(f"    Markets: {pe['num_markets']} | Total YES: ${pe['total_yes']:.4f} | Gap: ${pe['gap']:.4f}")

# ============================================================
# STRATEGY 2: Deep dive on best underpriced events with orderbook
# ============================================================

underpriced = [e for e in promising_events if e["is_under"]]
print(f"\n\n{'='*60}")
print(f"DEEP DIVE: {len(underpriced)} underpriced events")
print(f"{'='*60}")

for upe in underpriced[:5]:
    print(f"\n📊 {upe['title']}")
    print(f"   Gamma total: ${upe['total_yes']:.4f}")
    
    real_total = 0
    fillable = True
    min_depth = float('inf')
    
    for m in upe["markets"]:
        tokens_raw = m.get("clobTokenIds")
        if isinstance(tokens_raw, str):
            tokens = json.loads(tokens_raw)
        else:
            tokens = tokens_raw
        
        if not tokens:
            fillable = False
            continue
        
        yes_token = tokens[0]
        ob = analyze_orderbook_spread(yes_token)
        
        q = m.get("question", "")[:60]
        
        if ob and ob["best_ask"]:
            real_total += ob["best_ask"]
            min_depth = min(min_depth, ob["ask_depth"])
            print(f"   {q}")
            print(f"     Bid: ${ob['best_bid']:.4f} | Ask: ${ob['best_ask']:.4f} | Spread: ${ob['spread']:.4f} | Depth: {ob['ask_depth']:.0f}")
        else:
            # No ask = can't buy = can't arb
            prices_raw = m.get("outcomePrices")
            if isinstance(prices_raw, str):
                prices = [float(p) for p in json.loads(prices_raw)]
            else:
                prices = [float(p) for p in prices_raw]
            real_total += prices[0]
            print(f"   {q}")
            print(f"     NO ORDERBOOK — using Gamma price: ${prices[0]:.4f}")
            if prices[0] > 0.01:
                fillable = False
        
        time.sleep(0.3)
    
    print(f"\n   Real total (best asks): ${real_total:.4f}")
    if real_total < 1.0 and fillable:
        print(f"   ✅ EXECUTABLE ARB: Profit ${1.0 - real_total:.4f} per set")
        print(f"   Max sets at min depth: {min_depth:.0f}")
        print(f"   Max investment: ${min_depth * real_total:.2f}")
    elif real_total < 1.0:
        print(f"   ⚠️ Theoretical arb but NOT FILLABLE (missing orderbooks)")
    else:
        print(f"   ❌ Not profitable at real ask prices")

# ============================================================
# STRATEGY 3: High-confidence bonds with good liquidity
# ============================================================
print(f"\n\n{'='*60}")
print(f"HIGH-CONFIDENCE BONDS (quick resolution, good liquidity)")
print(f"{'='*60}")

print("\nFetching all markets for bond scan...")
all_markets = []
for offset in range(0, 500, 100):
    mkts = get_markets(limit=100, offset=offset)
    if not mkts:
        break
    all_markets.extend(mkts)
    time.sleep(0.5)
print(f"Got {len(all_markets)} markets")

bonds = []
for m in all_markets:
    prices_raw = m.get("outcomePrices")
    if isinstance(prices_raw, str):
        try:
            prices = [float(p) for p in json.loads(prices_raw)]
        except:
            continue
    elif prices_raw:
        prices = [float(p) for p in prices_raw]
    else:
        continue
    
    tokens_raw = m.get("clobTokenIds")
    if isinstance(tokens_raw, str):
        try:
            tokens = json.loads(tokens_raw)
        except:
            continue
    else:
        tokens = tokens_raw
    
    if not tokens or len(tokens) < 2:
        continue
    
    end_date = m.get("endDate", "")
    volume = float(m.get("volume", 0) or 0)
    liquidity = float(m.get("liquidity", 0) or 0)
    
    # We want: high probability, decent volume, resolves soon
    for side_idx, side_name in [(0, "YES"), (1, "NO")]:
        price = prices[side_idx]
        if 0.88 <= price <= 0.97 and volume > 1000 and liquidity > 500:
            profit = 1.0 - price
            roi = (profit / price) * 100
            bonds.append({
                "side": side_name,
                "question": m.get("question", ""),
                "price": price,
                "profit": profit,
                "roi": roi,
                "volume": volume,
                "liquidity": liquidity,
                "end_date": end_date,
                "token": tokens[side_idx],
            })

bonds.sort(key=lambda x: (x["roi"], x["liquidity"]), reverse=True)

print(f"\nFound {len(bonds)} high-quality bonds")
for b in bonds[:15]:
    print(f"\n  🏦 [{b['side']}] {b['question'][:70]}")
    print(f"     Price: ${b['price']:.4f} | Profit: ${b['profit']:.4f} | ROI: {b['roi']:.1f}%")
    print(f"     Volume: ${b['volume']:,.0f} | Liquidity: ${b['liquidity']:,.0f} | Ends: {b['end_date'][:10]}")

# Save everything
results = {
    "scan_time": datetime.now(timezone.utc).isoformat(),
    "promising_events": [{"title": e["title"], "total_yes": e["total_yes"], "gap": e["gap"], 
                          "is_under": e["is_under"], "num_markets": e["num_markets"]} 
                         for e in promising_events[:20]],
    "bonds": bonds[:30],
}

with open("/home/codespace/.openclaw/workspace/polymarket/deep_scan.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*60}")
print("Deep scan complete. Results saved.")
print(f"{'='*60}")
