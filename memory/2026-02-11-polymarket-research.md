# Polymarket Research - 2026-02-11

## What is Polymarket
- World's largest prediction market platform
- Users buy/sell shares representing outcomes of future events
- Shares priced $0.00 - $1.00 USDC (price = implied probability)
- YES + NO shares fully collateralized at $1.00 USDC per pair
- Correct outcome shares pay out $1.00 each on resolution
- Peer-to-peer (no house) — counterparty is another user
- Can sell shares before resolution (lock profits / cut losses)
- Operates on Polygon blockchain, settled in USDC
- Used UMA optimistic oracle for resolution
- Surpassed $10B trading volume in 2025
- Partnered with Dow Jones for data

## Legal Status
- Operates offshore for US election predictions (CFTC regulated domestically)
- 2025 CFTC designation evolving US access through regulated channel (Polymarket US)
- Terms of Service prohibit US persons from trading (via UI & API)
- Data/information viewable globally
- Blocked in several countries
- Faced insider trading scrutiny (2026 Venezuela strikes)

## Technical Architecture (CLOB)
- Hybrid-decentralized Central Limit Order Book (CLOB)
- Off-chain matching/ordering by operator, on-chain settlement
- Custom Exchange contract: atomic swaps between binary Outcome Tokens (CTF ERC1155) and collateral (ERC20 USDC)
- Orders are EIP712-signed structured data
- Maker/taker model, price improvements go to taker
- Operator can't set prices or execute unauthorized trades
- Users can cancel orders on-chain independently
- Exchange contract audited by Chainsecurity

## Fees
- Current: 0 bps maker, 0 bps taker (subject to change)
- Fee formula accounts for min(price, 1-price) × size

## APIs & Tools
### Gamma Markets API
- REST API for market metadata, categorization, indexed volume
- Market discovery, resolution data

### CLOB API  
- REST + WebSocket endpoints
- Create, list, fetch orders
- Market prices, order history
- All orders expressed as limit orders (can be marketable)

### Python Tools
- `py-clob-client` (PyPI) - Official Python client for CLOB
  - Host: https://clob.polymarket.com
  - Chain ID: 137 (Polygon)
  - Requires: private key, funder address
  - Methods: get_last_trade_price, get_trades, create orders, etc.
- `polymarket-apis` (PyPI) - Community wrapper
- `Polymarket/agents` (GitHub) - AI agent framework for trading
  - Python 3.9
  - Integrates with OpenAI for AI-driven trading decisions
  - RAG support, news sourcing, web search
  - CLI interface + autonomous trading script
  - MIT License

## Six Proven Profitable Strategies (from on-chain analysis)
1. **Information Arbitrage** - Trade faster on news/information edge
2. **Cross-Platform Arbitrage** - Exploit price differences between Polymarket and other prediction markets (Kalshi, etc.)
3. **High-Probability Bonds** - Buy shares at 90-99¢ that are very likely to resolve YES — small profit per share but high win rate
4. **Liquidity Provision / Market Making** - Place both buy/sell orders, earn the spread
5. **Domain Specialization** - Become expert in specific categories (politics, crypto, sports) for consistent edge
6. **Speed Trading** - Fast execution on breaking news events

## Arbitrage Types (Academic)
- **Market Rebalancing Arbitrage** - Within single market/condition
- **Combinatorial Arbitrage** - Across multiple markets

## Key Observations
- AI agents are already being used to trade on Polymarket
- Automated bots have documented profits ($764/day on BTC-15m markets with $200 deposit)
- The 0% fee structure makes market making and arbitrage more viable
- Real edge comes from: information speed, domain expertise, or systematic approaches
