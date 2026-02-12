#!/usr/bin/env python3
"""Dry-run reconcile + preflight gate checker (no live order execution)."""
import os
import json
import time
from collections import defaultdict
from dotenv import load_dotenv
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

load_dotenv('/opt/polybot/.env')
PK = os.getenv('POLYGON_WALLET_PRIVATE_KEY')
HOST = 'https://clob.polymarket.com'
CHAIN = 137


def now():
    return int(time.time())


def get_client():
    wallet = Account.from_key(PK).address
    c = ClobClient(HOST, key=PK, chain_id=CHAIN, signature_type=0, funder=wallet)
    c.set_api_creds(c.create_or_derive_api_creds())
    return c, wallet


def preflight_check(state_clean: bool):
    """Dry-run preflight: fetch read-only book snapshot to compute numerics.

    Execution remains disabled; this is purely to replace BOOK_UNVERIFIED with
    specific reason codes (STALE_BOOK/SPREAD_TOO_WIDE/EXIT_DEPTH_INSUFFICIENT).
    """
    reason_codes = []

    # integrity
    state_reconciliation_recent = True
    divergence_resolved = bool(state_clean)
    if not divergence_resolved:
        reason_codes.append('STATE_DIVERGENCE')

    # planned sizing for multiples (shares)
    planned_exit_size = float(os.getenv('PREFLIGHT_SIZE_SHARES', '10'))
    staleness_limit = int(os.getenv('PREFLIGHT_STALENESS_LIMIT', '15'))
    spread_limit_cents = float(os.getenv('PREFLIGHT_SPREAD_LIMIT_CENTS', '1'))
    depth_exit_mult = float(os.getenv('PREFLIGHT_DEPTH_EXIT_MULT', '5'))
    depth_3ticks_mult = float(os.getenv('PREFLIGHT_DEPTH_3TICKS_MULT', '10'))

    # liquidity defaults
    orderbook_verification = False
    exit_depth_sufficient = False
    spread_within_threshold = False
    staleness_seconds = 0
    spread_cents = 0.0
    exit_depth_multiple = 0.0
    depth_3ticks_multiple = 0.0

    # read-only snapshot (best effort)
    snap_path = '/opt/polybot/rag_sources/book_snapshot_latest.json'
    try:
        import subprocess, json as _json
        raw = subprocess.check_output(['env/bin/python3', '/opt/polybot/book_snapshot_dry_run.py'], cwd='/opt/polybot', timeout=25)
        snap = _json.loads(raw.decode('utf-8'))
        with open(snap_path, 'w', encoding='utf-8') as f:
            f.write(_json.dumps(snap, indent=2))

        # choose first row with bid+ask
        row = None
        for r in snap.get('rows', []):
            if isinstance(r, dict) and r.get('best_bid_price') and r.get('best_ask_price'):
                row = r
                break
        if row:
            orderbook_verification = True
            now_s = int(time.time())
            lts = int(row.get('last_trade_ts') or 0)
            staleness_seconds = (now_s - lts) if lts else 999999
            spread_cents = max(0.0, (float(row['best_ask_price']) - float(row['best_bid_price'])) * 100.0)

            # multiples: compare available depth to planned size
            exit_depth_multiple = (float(row.get('best_bid_size') or 0.0) / planned_exit_size) if planned_exit_size > 0 else 0.0
            depth_3ticks_multiple = (float(row.get('depth_3ticks_bid') or 0.0) / planned_exit_size) if planned_exit_size > 0 else 0.0

            # gates
            if staleness_seconds <= staleness_limit:
                # fresh enough
                pass
            else:
                reason_codes.append('STALE_BOOK')

            if spread_cents <= spread_limit_cents:
                spread_within_threshold = True
            else:
                reason_codes.append('SPREAD_TOO_WIDE')

            if exit_depth_multiple >= depth_exit_mult and depth_3ticks_multiple >= depth_3ticks_mult:
                exit_depth_sufficient = True
            else:
                reason_codes.append('EXIT_DEPTH_INSUFFICIENT')
        else:
            reason_codes.append('BOOK_UNVERIFIED')

    except Exception:
        reason_codes.append('BOOK_UNVERIFIED')

    # execution stays disabled in dry-run
    reason_codes.append('EXECUTION_DISABLED')

    can_trade = False

    return {
        'can_trade': can_trade,
        'reason_codes': list(dict.fromkeys(reason_codes)),
        'staleness_seconds': int(staleness_seconds),
        'spread_cents': float(round(spread_cents, 4)),
        'exit_depth_multiple': float(round(exit_depth_multiple, 4)),
        'depth_3ticks_multiple': float(round(depth_3ticks_multiple, 4)),
        'max_exposure_usd': 0.0,
        'max_loss_usd': 0.0,
        'time_stop_seconds': 0,
        'orderbook_verification': bool(orderbook_verification),
        'exit_depth_sufficient': bool(exit_depth_sufficient),
        'spread_within_threshold': bool(spread_within_threshold),
        'state_reconciliation_recent': bool(state_reconciliation_recent),
        'divergence_resolved': bool(divergence_resolved),
    }


def reconcile_state():
    c, wallet = get_client()
    issues = []

    # USDC
    coll = c.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id='', signature_type=0))
    wallet_usdc = int(coll.get('balance', '0')) / 1e6

    # Open orders
    orders = c.get_orders()
    olist = orders.get('orders', orders) if isinstance(orders, dict) else (orders or [])

    sell_reserved = defaultdict(float)
    buy_reserved_usdc = 0.0
    tracked_token_ids = set()

    # Conservative reservation set (Selene): LIVE + PARTIALLY_FILLED
    reserve_status = {'LIVE', 'PARTIALLY_FILLED'}

    for o in olist:
        status = str(o.get('status') or '').upper()
        if status not in reserve_status:
            continue
        token_id = str(o.get('asset_id') or '')
        side = str(o.get('side') or '').upper()
        try:
            orig = float(o.get('original_size') or 0)
            matched = float(o.get('size_matched') or 0)
            rem = max(0.0, orig - matched)
            px = float(o.get('price') or 0)
        except Exception:
            continue

        if token_id:
            tracked_token_ids.add(token_id)

        if side == 'SELL' and token_id:
            sell_reserved[token_id] += rem
        elif side == 'BUY':
            buy_reserved_usdc += rem * px

    free_usdc = wallet_usdc - buy_reserved_usdc
    if free_usdc < -0.01:
        issues.append('BUY_USDC_OVERCOMMIT')

    token_rows = []
    for token_id in sorted(tracked_token_ids):
        try:
            br = c.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id, signature_type=0))
            wallet_bal = int(br.get('balance', '0')) / 1e6
        except Exception:
            wallet_bal = 0.0

        reserved = sell_reserved[token_id]
        free_bal = wallet_bal - reserved
        if free_bal < -0.01:
            issues.append(f'POSITION_MISMATCH:{token_id[:10]}')

        # verify orderbook exists (no trade action)
        book_status = 'OK'
        try:
            ob = c.get_order_book(token_id)
            bids = getattr(ob, 'bids', []) or []
            asks = getattr(ob, 'asks', []) or []
            if not bids and not asks:
                book_status = 'STALE_OR_EMPTY'
        except Exception:
            book_status = '404_OR_ERROR'
            if wallet_bal > 0:
                issues.append(f'UNEXITABLE_INVENTORY:{token_id[:10]}')

        token_rows.append({
            'token_id': token_id,
            'wallet_balance': round(wallet_bal, 6),
            'sell_reserved': round(reserved, 6),
            'free_balance': round(free_bal, 6),
            'book_status': book_status,
        })

    state_clean = len([x for x in issues if x.startswith('POSITION_MISMATCH') or x.startswith('UNEXITABLE_INVENTORY') or x=='BUY_USDC_OVERCOMMIT']) == 0

    # Selene reconcile_state schema (verbatim)
    state = {
        'ts': now(),
        'state_version': 1,
        'wallet_usdc': round(wallet_usdc, 6),
        'buy_reserved_usdc': round(buy_reserved_usdc, 6),
        'free_usdc': round(free_usdc, 6),
        'tokens': token_rows,
        'state_clean': state_clean,
        'issues': issues,
    }
    return state


if __name__ == '__main__':
    state = reconcile_state()
    pf = preflight_check(state.get('state_clean', False))
    print(json.dumps({'reconcile_state': state, 'preflight_check': pf}, indent=2))
