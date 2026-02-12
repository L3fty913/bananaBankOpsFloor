"""
Polymarket Arbitrage Scanner v2
Faster, more robust — uses Gamma API for pricing where possible
to avoid hammering the CLOB endpoint.
"""

import requests
import json
import time
from datetime import datetime, timezone

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

def get_active_markets(limit=100, offset=0):
    """Fetch active markets from Gamma API"""
    params = {
        "limit": limit,
        "offset": offset,
        "active": "true",
        "closed": "false",
    }
    resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def get_all_active_markets(max_markets=500):
    """Paginate through all active markets"""
    all_markets = []
    offset = 0
    limit = 100
    while offset < max_markets:
        try:
            markets = get_active_markets(limit=limit, offset=offset)
            if not markets:
                break
            all_markets.extend(markets)
            if len(markets) < limit:
                break
            offset += limit
            time.sleep(0.5)
        except Exception as e:
            print(f"  Error fetching markets at offset {offset}: {e}")
            break
    return all_markets

def get_events(limit=50, offset=0):
    """Fetch events (groups of related markets)"""
    params = {
        "limit": limit,
        "offset": offset,
        "active": "true",
        "closed": "false",
    }
    try:
        resp = requests.get(f"{GAMMA_API}/events", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Error fetching events: {e}")
        return []

def parse_tokens(market):
    """Extract token IDs from market data"""
    tokens = market.get("clobTokenIds")
    if not tokens:
        return None
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except:
            return None
    if isinstance(tokens, list) and len(tokens) >= 2:
        return tokens
    return None

def parse_outcome_prices(market):
    """Extract outcome prices from Gamma market data"""
    prices_str = market.get("outcomePrices")
    if not prices_str:
        return None
    if isinstance(prices_str, str):
        try:
            prices = json.loads(prices_str)
            return [float(p) for p in prices]
        except:
            return None
    if isinstance(prices_str, list):
        return [float(p) for p in prices_str]
    return None

def scan_binary_arbitrage(markets):
    """
    Scan binary markets for arbitrage using Gamma's cached prices.
    In a properly priced binary market, YES + NO = 1.00
    If YES + NO < 1.00 at ask prices → buy both → guaranteed profit on resolution
    """
    opportunities = []
    
    for market in markets:
        try:
            tokens = parse_tokens(market)
            if not tokens or len(tokens) != 2:
                continue
            
            prices = parse_outcome_prices(market)
            if not prices or len(prices) != 2:
                continue
            
            yes_price = prices[0]
            no_price = prices[1]
            
            if yes_price <= 0 or no_price <= 0:
                continue
            
            total = yes_price + no_price
            
            # Look for markets where prices don't sum to 1.0
            # Underpriced: total < 1.0 (buy both sides = free money)
            if total < 0.98:
                profit_per_share = 1.0 - total
                profit_pct = (profit_per_share / total) * 100
                
                opportunities.append({
                    "type": "binary_underpriced",
                    "market": market.get("question", "Unknown"),
                    "market_id": market.get("id", ""),
                    "condition_id": market.get("conditionId", ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "total": total,
                    "profit_per_share": profit_per_share,
                    "profit_pct": profit_pct,
                    "yes_token": tokens[0],
                    "no_token": tokens[1],
                    "volume": market.get("volume", 0),
                    "liquidity": market.get("liquidity", 0),
                    "spread": market.get("spread", "N/A"),
                    "end_date": market.get("endDate", "N/A"),
                })
            
            # Overpriced: total > 1.0 (sell both sides if you hold them, or short)
            elif total > 1.02:
                excess = total - 1.0
                opportunities.append({
                    "type": "binary_overpriced",
                    "market": market.get("question", "Unknown"),
                    "market_id": market.get("id", ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "total": total,
                    "excess": excess,
                    "excess_pct": (excess / total) * 100,
                    "yes_token": tokens[0],
                    "no_token": tokens[1],
                    "volume": market.get("volume", 0),
                    "liquidity": market.get("liquidity", 0),
                })
                
        except Exception as e:
            continue
    
    return sorted(opportunities, key=lambda x: x.get("profit_pct", x.get("excess_pct", 0)), reverse=True)

def scan_high_probability_bonds(markets):
    """
    Find markets priced at 90-99¢ that are very likely to resolve YES.
    Small profit per share but high confidence = consistent returns.
    """
    bonds = []
    
    for market in markets:
        try:
            prices = parse_outcome_prices(market)
            if not prices or len(prices) < 2:
                continue
            
            tokens = parse_tokens(market)
            if not tokens:
                continue
            
            yes_price = prices[0]
            no_price = prices[1]
            
            # High probability YES (cheap NO shares)
            if 0.90 <= yes_price <= 0.99:
                profit_if_yes = 1.0 - yes_price
                roi = (profit_if_yes / yes_price) * 100
                bonds.append({
                    "side": "YES",
                    "market": market.get("question", "Unknown"),
                    "market_id": market.get("id", ""),
                    "price": yes_price,
                    "profit_per_share": profit_if_yes,
                    "roi_pct": roi,
                    "token": tokens[0],
                    "volume": market.get("volume", 0),
                    "liquidity": market.get("liquidity", 0),
                    "end_date": market.get("endDate", "N/A"),
                })
            
            # High probability NO (cheap YES shares to short, or buy NO)
            if 0.90 <= no_price <= 0.99:
                profit_if_no = 1.0 - no_price
                roi = (profit_if_no / no_price) * 100
                bonds.append({
                    "side": "NO",
                    "market": market.get("question", "Unknown"),
                    "market_id": market.get("id", ""),
                    "price": no_price,
                    "profit_per_share": profit_if_no,
                    "roi_pct": roi,
                    "token": tokens[1],
                    "volume": market.get("volume", 0),
                    "liquidity": market.get("liquidity", 0),
                    "end_date": market.get("endDate", "N/A"),
                })
                
        except Exception:
            continue
    
    return sorted(bonds, key=lambda x: x["roi_pct"], reverse=True)

def scan_event_arbitrage(events_data):
    """
    Scan multi-outcome events.
    If all outcomes in an event sum to < 1.0, buy all = guaranteed profit.
    """
    opportunities = []
    
    for event in events_data:
        markets = event.get("markets", [])
        if not markets or len(markets) < 2:
            continue
        
        total_yes = 0
        valid = True
        details = []
        
        for m in markets:
            prices = parse_outcome_prices(m)
            if not prices:
                valid = False
                break
            
            tokens = parse_tokens(m)
            yes_price = prices[0]
            
            if yes_price <= 0:
                valid = False
                break
            
            total_yes += yes_price
            details.append({
                "question": m.get("question", ""),
                "yes_price": yes_price,
                "token": tokens[0] if tokens else None,
            })
        
        if not valid or total_yes <= 0:
            continue
        
        # Multi-outcome: all YES should sum to ~1.0
        if total_yes < 0.95:
            opportunities.append({
                "type": "event_underpriced",
                "event": event.get("title", event.get("slug", "Unknown")),
                "num_outcomes": len(markets),
                "total_yes_cost": total_yes,
                "profit_per_set": 1.0 - total_yes,
                "profit_pct": ((1.0 - total_yes) / total_yes) * 100,
                "details": details,
            })
        elif total_yes > 1.05:
            opportunities.append({
                "type": "event_overpriced",
                "event": event.get("title", event.get("slug", "Unknown")),
                "num_outcomes": len(markets),
                "total_yes_cost": total_yes,
                "excess": total_yes - 1.0,
                "excess_pct": ((total_yes - 1.0) / total_yes) * 100,
                "details": details,
            })
    
    return sorted(opportunities, key=lambda x: x.get("profit_pct", x.get("excess_pct", 0)), reverse=True)


def run_scan():
    """Main scan function"""
    print(f"{'='*60}")
    print(f"POLYMARKET ARBITRAGE SCANNER v2")
    print(f"Scan time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")
    
    # 1. Fetch markets
    print("\n[1/4] Fetching active markets...")
    markets = get_all_active_markets(max_markets=500)
    print(f"  Found {len(markets)} active markets")
    
    # 2. Binary arbitrage scan (uses Gamma cached prices — fast)
    print("\n[2/4] Scanning binary markets for mispricing...")
    binary_opps = scan_binary_arbitrage(markets)
    
    underpriced = [o for o in binary_opps if o["type"] == "binary_underpriced"]
    overpriced = [o for o in binary_opps if o["type"] == "binary_overpriced"]
    
    print(f"\n  Underpriced (buy both sides): {len(underpriced)}")
    for opp in underpriced[:10]:
        print(f"\n  💰 {opp['market']}")
        print(f"     YES: ${opp['yes_price']:.4f} | NO: ${opp['no_price']:.4f} | Sum: ${opp['total']:.4f}")
        print(f"     Profit/share: ${opp['profit_per_share']:.4f} ({opp['profit_pct']:.2f}%)")
        print(f"     Vol: {opp['volume']} | Liq: {opp['liquidity']}")
    
    print(f"\n  Overpriced (sell opportunity): {len(overpriced)}")
    for opp in overpriced[:5]:
        print(f"\n  📉 {opp['market']}")
        print(f"     YES: ${opp['yes_price']:.4f} | NO: ${opp['no_price']:.4f} | Sum: ${opp['total']:.4f}")
        print(f"     Excess: ${opp['excess']:.4f} ({opp['excess_pct']:.2f}%)")
    
    # 3. High probability bonds
    print(f"\n[3/4] Scanning for high-probability bonds (90-99¢)...")
    bonds = scan_high_probability_bonds(markets)
    print(f"  Found {len(bonds)} bond opportunities")
    for bond in bonds[:10]:
        print(f"\n  🏦 [{bond['side']}] {bond['market']}")
        print(f"     Price: ${bond['price']:.4f} | Profit: ${bond['profit_per_share']:.4f} | ROI: {bond['roi_pct']:.1f}%")
        print(f"     Ends: {bond['end_date']}")
    
    # 4. Event-level arbitrage
    print(f"\n[4/4] Fetching events for cross-outcome arbitrage...")
    events = get_events(limit=50)
    print(f"  Fetched {len(events)} events")
    event_opps = scan_event_arbitrage(events)
    
    print(f"\n  Event arbitrage opportunities: {len(event_opps)}")
    for opp in event_opps[:10]:
        print(f"\n  📊 {opp['event']}")
        print(f"     Outcomes: {opp['num_outcomes']} | Sum: ${opp['total_yes_cost']:.4f}")
        ptype = opp['type']
        if 'profit_pct' in opp:
            print(f"     Profit/set: ${opp['profit_per_set']:.4f} ({opp['profit_pct']:.2f}%)")
        else:
            print(f"     Excess: ${opp['excess']:.4f} ({opp['excess_pct']:.2f}%)")
        for d in opp.get("details", [])[:5]:
            print(f"       - {d['question'][:60]}: ${d['yes_price']:.4f}")
    
    # Save results
    results = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "total_markets": len(markets),
        "binary_underpriced": underpriced[:20],
        "binary_overpriced": overpriced[:20],
        "high_prob_bonds": bonds[:20],
        "event_opportunities": event_opps[:20],
    }
    
    with open("/home/codespace/.openclaw/workspace/polymarket/last_scan.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"Scan complete. Results saved to polymarket/last_scan.json")
    print(f"{'='*60}")
    
    return results


if __name__ == "__main__":
    run_scan()
