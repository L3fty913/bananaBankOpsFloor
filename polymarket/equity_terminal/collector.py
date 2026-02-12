#!/usr/bin/env python3
import os
import time
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType, TradeParams

DB_PATH = os.getenv("EQUITY_DB_PATH", "/opt/polybot/rag/equity_terminal.db")
CADENCE_SEC = float(os.getenv("EQUITY_CADENCE_SEC", "2"))
CHAIN_ID = 137
HOST = "https://clob.polymarket.com"
ET = ZoneInfo("America/New_York")


def db_init(conn):
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_utc INTEGER NOT NULL,
          timestamp_et TEXT NOT NULL,
          equity_total_usd REAL NOT NULL,
          realized_pnl_usd REAL,
          unrealized_pnl_usd REAL,
          open_exposure_usd REAL,
          latency_ms INTEGER,
          api_ok INTEGER,
          last_trade_ts INTEGER,
          safe_mode INTEGER,
          stale_data INTEGER
        )
        """
    )
    conn.commit()


def get_client():
    load_dotenv("/opt/polybot/.env")
    pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    wallet = Account.from_key(pk).address
    c = ClobClient(HOST, key=pk, chain_id=CHAIN_ID, signature_type=0, funder=wallet)
    c.set_api_creds(c.create_or_derive_api_creds())
    return c, wallet


def get_total_equity(client, wallet):
    t0 = time.time()
    stale = 0
    api_ok = 1
    last_trade_ts = None

    # collateral (USDC)
    params_c = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=0)
    coll = client.get_balance_allowance(params_c)
    usdc = int(coll.get("balance", "0")) / 1e6

    # build open inventory from trades (authoritative flow) then validate with balance endpoint
    trades = client.get_trades(TradeParams(maker_address=wallet, after=int(time.time()) - 14 * 24 * 3600))
    if not isinstance(trades, list):
        trades = []

    lots = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    realized = 0.0
    for t in sorted(trades, key=lambda x: int(x.get("match_time") or 0)):
        try:
            aid = str(t.get("asset_id"))
            side = (t.get("side") or "").upper()
            q = float(t.get("size") or 0)
            p = float(t.get("price") or 0)
            mt = int(t.get("match_time") or 0)
            if mt and (last_trade_ts is None or mt > last_trade_ts):
                last_trade_ts = mt
            if q <= 0:
                continue
            if side == "BUY":
                lots[aid]["qty"] += q
                lots[aid]["cost"] += q * p
            elif side == "SELL":
                have = lots[aid]["qty"]
                if have <= 1e-9:
                    continue
                avg = lots[aid]["cost"] / have
                close_q = min(have, q)
                realized += (p - avg) * close_q
                lots[aid]["qty"] -= close_q
                lots[aid]["cost"] -= avg * close_q
                if lots[aid]["qty"] < 1e-9:
                    lots[aid] = {"qty": 0.0, "cost": 0.0}
        except Exception:
            continue

    unreal = 0.0
    open_exposure = 0.0
    for aid, pos in lots.items():
        q = pos["qty"]
        if q <= 1e-9:
            continue

        # authoritative current token balance check
        try:
            balp = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=aid, signature_type=0)
            br = client.get_balance_allowance(balp)
            q_bal = int(br.get("balance", "0")) / 1e6
            q = min(q, q_bal)
        except Exception:
            pass

        if q <= 1e-9:
            continue

        avg = pos["cost"] / pos["qty"] if pos["qty"] > 0 else 0.0
        try:
            lp = client.get_last_trade_price(aid)
            mark = float(lp.get("price") if isinstance(lp, dict) else lp)
            if mark <= 0:
                stale = 1
                mark = avg
        except Exception:
            api_ok = 0
            stale = 1
            mark = avg

        open_exposure += q * mark
        unreal += (mark - avg) * q

    equity = usdc + open_exposure
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "equity_total_usd": equity,
        "realized_pnl_usd": realized,
        "unrealized_pnl_usd": unreal,
        "open_exposure_usd": open_exposure,
        "latency_ms": latency_ms,
        "api_ok": api_ok,
        "last_trade_ts": last_trade_ts,
        "stale_data": stale,
    }


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    db_init(conn)

    while True:
        ts = int(time.time())
        et = datetime.fromtimestamp(ts, timezone.utc).astimezone(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
        safe_mode = 1 if os.path.exists("/opt/polybot/safe_mode.flag") else 0

        try:
            client, wallet = get_client()
            snap = get_total_equity(client, wallet)
        except Exception:
            snap = {
                "equity_total_usd": 0.0,
                "realized_pnl_usd": 0.0,
                "unrealized_pnl_usd": 0.0,
                "open_exposure_usd": 0.0,
                "latency_ms": None,
                "api_ok": 0,
                "last_trade_ts": None,
                "stale_data": 1,
            }

        conn.execute(
            """
            INSERT INTO equity_snapshots (
              ts_utc, timestamp_et, equity_total_usd, realized_pnl_usd, unrealized_pnl_usd, open_exposure_usd,
              latency_ms, api_ok, last_trade_ts, safe_mode, stale_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                et,
                snap["equity_total_usd"],
                snap["realized_pnl_usd"],
                snap["unrealized_pnl_usd"],
                snap["open_exposure_usd"],
                snap["latency_ms"],
                snap["api_ok"],
                snap["last_trade_ts"],
                safe_mode,
                snap["stale_data"],
            ),
        )
        conn.commit()
        time.sleep(CADENCE_SEC)


if __name__ == "__main__":
    main()
