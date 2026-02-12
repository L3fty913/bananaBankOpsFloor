"""
Deep dive into the Trump deportation event arbitrage opportunity.
Check actual orderbook depth to see if we can fill.
"""
import requests
import json
import time

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

def get_events(limit=50):
    resp = requests.get(f"{GAMMA_API}/events", params={"limit": limit, "active": "true", "closed": "false"}, timeout=15)
    resp.raise_for_status()
    return resp.json()

def get_orderbook(token_id):
    try:
        resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Error getting orderbook: {e}")
        return None

def analyze_event(event):
    """Analyze an event for arbitrage, checking real orderbook depth"""
    markets = event.get("markets", [])
    if len(markets) < 2:
        return None
    
    print(f"\n{'='*60}")
    print(f"EVENT: {event.get('title', 'Unknown')}")
    print(f"Markets: {len(markets)}")
    print(f"{'='*60}")
    
    total_best_ask = 0
    all_details = []
    
    for m in markets:
        question = m.get("question", "Unknown")
        tokens_raw = m.get("clobTokenIds")
        prices_raw = m.get("outcomePrices")
        
        if isinstance(tokens_raw, str):
            tokens = json.loads(tokens_raw)
        else:
            tokens = tokens_raw
            
        if isinstance(prices_raw, str):
            prices = [float(p) for p in json.loads(prices_raw)]
        else:
            prices = [float(p) for p in prices_raw] if prices_raw else []
        
        if not tokens or len(tokens) < 1:
            continue
        
        yes_token = tokens[0]
        gamma_yes_price = prices[0] if prices else 0
        
        # Get real orderbook
        book = get_orderbook(yes_token)
        
        best_ask = None
        ask_depth = 0
        
        if book and book.get("asks"):
            asks = sorted(book["asks"], key=lambda x: float(x["price"]))
            if asks:
                best_ask = float(asks[0]["price"])
                # Calculate depth at best few price levels
                for ask in asks[:3]:
                    ask_depth += float(ask.get("size", 0))
        
        detail = {
            "question": question[:70],
            "yes_token": yes_token,
            "gamma_price": gamma_yes_price,
            "best_ask": best_ask,
            "ask_depth_shares": ask_depth,
        }
        all_details.append(detail)
        
        effective_price = best_ask if best_ask else gamma_yes_price
        total_best_ask += effective_price
        
        print(f"\n  {question[:70]}")
        print(f"    Gamma price: ${gamma_yes_price:.4f}")
        print(f"    Best ask:    ${best_ask:.4f}" if best_ask else "    Best ask:    N/A (no asks)")
        print(f"    Ask depth:   {ask_depth:.1f} shares (top 3 levels)")
        
        time.sleep(0.3)
    
    print(f"\n  {'─'*40}")
    print(f"  TOTAL (best asks): ${total_best_ask:.4f}")
    if total_best_ask < 1.0:
        profit = 1.0 - total_best_ask
        print(f"  ✅ ARBITRAGE: Buy all for ${total_best_ask:.4f}, guaranteed $1.00 back")
        print(f"  💰 Profit per set: ${profit:.4f} ({(profit/total_best_ask)*100:.2f}%)")
    elif total_best_ask > 1.0:
        excess = total_best_ask - 1.0
        print(f"  📉 Overpriced by ${excess:.4f} — potential short arb")
    else:
        print(f"  ⚖️ Fairly priced")
    
    return {
        "event": event.get("title"),
        "total": total_best_ask,
        "details": all_details,
    }


# Fetch and analyze all events
print("Fetching events...")
events = get_events(limit=50)
print(f"Got {len(events)} events\n")

# Look for multi-outcome events
interesting = []
for e in events:
    markets = e.get("markets", [])
    if len(markets) >= 3:
        # Quick check with Gamma prices
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
        
        if valid:
            interesting.append((e, total, abs(total - 1.0)))

# Sort by how far from 1.0 (most mispriced first)
interesting.sort(key=lambda x: x[2], reverse=True)

print(f"Found {len(interesting)} multi-outcome events")
print(f"Analyzing top opportunities with orderbook depth...\n")

for event, gamma_total, gap in interesting[:5]:
    analyze_event(event)
