from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_maker.config import BotConfig, Environment, Venue
from market_maker.state import HaltedStateStore


def test_live_mode_requires_explicit_acknowledgement_and_credentials():
    with pytest.raises(ValidationError):
        BotConfig(environment=Environment.LIVE, venue=Venue.BINANCE, symbol="BTCUSDT")


def test_halted_state_is_atomic_and_must_be_cleared(tmp_path):
    store = HaltedStateStore(tmp_path / "state.json")
    assert store.load_halted_reason() is None
    store.save_halt("stale book")
    assert store.load_halted_reason() == "stale book"
    store.clear()
    assert store.load_halted_reason() is None
