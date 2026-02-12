#!/usr/bin/env python3
"""Typed reconcile_state schema + helpers (Selene spec)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Literal

BookStatus = Literal["OK", "STALE_OR_EMPTY", "404_OR_ERROR", "UNVERIFIED"]


@dataclass
class TokenState:
    token_id: str
    wallet_balance: float
    sell_reserved: float
    free_balance: float
    book_status: BookStatus


@dataclass
class ReconcileState:
    ts: int
    state_version: int
    wallet_usdc: float
    buy_reserved_usdc: float
    free_usdc: float
    tokens: List[TokenState]
    state_clean: bool
    issues: List[str]
