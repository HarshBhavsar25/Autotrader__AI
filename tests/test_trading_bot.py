import pytest
import pandas as pd
import numpy as np
from config import config
from risk_engine import risk_engine
from ai_signal_engine import ai_signal_engine
from database import db_manager
from exchange_adapter import PaperExchangeAdapter
from wallet_manager import WalletManager

def test_config_defaults():
    assert config.INITIAL_CAPITAL_INR == 1000.0
    assert config.MIN_TRADE_SIZE_INR == 100.0
    assert config.DAILY_NET_PROFIT_TARGET_INR == 500.0
    assert config.MIN_CONFIDENCE_SCORE == 35.0
    assert config.SWAP_LONG_SHORT_SIGNALS is False

def test_risk_engine_position_sizing_and_leverage():
    calc = risk_engine.calculate_trade_parameters(
        symbol="BTC/USDT",
        side="LONG",
        entry_price=60000.0,
        atr=500.0,
        confidence_score=85.0,
        current_balance_inr=1000.0,
        active_positions_count=0
    )

    assert calc.position_size_inr >= 200.0
    assert calc.leverage == config.MAX_LEVERAGE  # Full leverage allocation for standard setups
    assert calc.stop_loss_price < 60000.0
    assert calc.take_profit_price > 60000.0
    assert calc.expected_fees_inr > 0.0
    assert calc.expected_net_profit_inr > 0.0

def test_dynamic_full_capital_allocation():
    # Single remaining slot out of 4 should take 100% of available capital
    calc_last_slot = risk_engine.calculate_trade_parameters(
        symbol="ETH/USDT",
        side="LONG",
        entry_price=3000.0,
        atr=30.0,
        confidence_score=80.0,
        current_balance_inr=500.0,
        active_positions_count=3 # 3 open, 1 remaining slot
    )
    assert calc_last_slot.position_size_inr == 500.0

def test_risk_engine_actual_pnl():
    raw_pnl, fees, net_pnl = risk_engine.calculate_actual_pnl(
        side="LONG",
        entry_price=60000.0,
        exit_price=61200.0, # +2% move
        position_size_inr=250.0,
        leverage=10
    )
    assert raw_pnl > 0.0
    assert fees > 0.0
    assert net_pnl == raw_pnl - fees

def test_breakeven_trigger():
    # Long position moving in profit
    is_be = risk_engine.is_breakeven_triggered(
        side="LONG",
        entry_price=60000.0,
        current_price=60800.0,
        position_size_inr=250.0,
        leverage=10
    )
    assert is_be is True

def test_ai_signal_engine_indicators():
    # Generate 100 sample candles
    np.random.seed(42)
    prices = 60000.0 + np.cumsum(np.random.randn(100) * 100)
    data = []
    for i in range(100):
        data.append([
            1700000000000 + i * 300000,
            prices[i],
            prices[i] + 50.0,
            prices[i] - 50.0,
            prices[i] + 10.0,
            100.0 + np.random.rand() * 50
        ])
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    res = ai_signal_engine.analyze_candles("BTC/USDT", df)
    assert res.symbol == "BTC/USDT"
    assert 0.0 <= res.confidence_score <= 100.0
    assert res.signal in ["LONG", "SHORT", "NONE"]
    assert hasattr(res, "relative_strength_score")

def test_wallet_manager_transfer():
    adapter = PaperExchangeAdapter()
    adapter.balance_inr = 1600.0 # ₹600 profit over ₹1000 base
    wm = WalletManager(adapter)

    summary = wm.get_wallet_summary()
    assert summary["futures_balance_inr"] == 1600.0
    assert summary["base_capital_inr"] == 1000.0
    assert summary["current_profit_above_base_inr"] == 600.0

    success, msg, amount = wm.execute_daily_profit_transfer()
    assert success is True
    assert amount == 600.0
    assert adapter.get_balance_inr() == 1000.0
    assert adapter.get_spot_balance_inr() == 600.0
