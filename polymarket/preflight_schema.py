#!/usr/bin/env python3
"""Preflight check schema + reason codes (Selene spec)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Literal

ReasonCode = Literal[
    "BOOK_UNVERIFIED",
    "EXIT_DEPTH_INSUFFICIENT",
    "SPREAD_TOO_WIDE",
    "STATE_DIVERGENCE",
    "POSITION_MISMATCH",
    "STALE_BOOK",
    "RISK_LIMIT_EXCEEDED",
    "INSUFFICIENT_DATA",
    "EXECUTION_DISABLED",
    "UNEXITABLE_INVENTORY",
]


@dataclass
class PreflightCheck:
    can_trade: bool
    reason_codes: List[ReasonCode]
    staleness_seconds: int
    spread_cents: float
    exit_depth_multiple: float
    depth_3ticks_multiple: float
    max_exposure_usd: float
    max_loss_usd: float
    time_stop_seconds: int

    orderbook_verification: bool
    exit_depth_sufficient: bool
    spread_within_threshold: bool
    state_reconciliation_recent: bool
    divergence_resolved: bool
