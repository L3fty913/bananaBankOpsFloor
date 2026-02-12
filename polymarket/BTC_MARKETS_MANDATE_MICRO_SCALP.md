# BTC MARKETS MANDATE (MICRO-SCALP)

Source: Morpheus (2026-02-12 05:12 UTC)
Status: ACTIVE / SUPERCEDES conflicting logic

## 1) MARKET UNIVERSE (BTC ONLY)
- BTC above/below X by time T
- BTC range / between X and Y by time T
- BTC touches/doesn’t touch X by time T (if available)
- Any Polymarket markets explicitly keyed to BTC/USD spot level or BTC event outcomes
- Exclude all non-BTC markets

## 2) RANKING + FILTERS
Score = LiquidityScore + SpreadOpportunity + EdgeOpportunity - StalenessPenalty - FillRiskPenalty
Trade only if score >= threshold; otherwise stay flat.

## 3) EDGE RULE
NetEdgeBps = (ExpectedValueAfterSettlement - CostBasis) - (fees + expected_slippage + adverse_selection)
Trade only when NetEdgeBps >= MinEdgeBps.
If NetEdgeBps < MinEdgeBps/2 while in position, exit.

## 4) PLAYBOOKS
A) Spread capture
B) Lag arb
C) Micro-momentum (with strict time-stop)
D) Overreaction fade (small size)

## 5) EXECUTION
- Prefer limit orders
- Idempotent intents (no double-submit)
- Clamp size 1–20 units + MaxPositionPerMarket
- Deterministic cancel/replace with single source of truth
- No trading on stale state (KillSwitchLatencyMs)

## 6) EXIT RULES
Every entry must define:
- profit_take
- time_stop (default 90–240s)
- edge_stop
Exit immediately if any stop hits.

## 7) RISK
Respect MaxTotalExposure, DailyMaxDrawdown, MaxConsecutiveLosses.
If breached:
- flatten
- cancel all
- SAFE MODE
- notify Morpheus immediately

## 8) REPORTING
Instant updates on open/close positions, SAFE MODE, feed/API degradation, bot status.
15-min summaries with:
- PnL delta
- win-rate
- avg hold time
- slippage/fees
- top 3 markets by edge
