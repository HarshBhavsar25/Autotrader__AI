import math
from dataclasses import dataclass
from typing import Dict, Any, Tuple
from config import config

@dataclass
class TradeOrderCalculation:
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_distance: float
    leverage: int
    position_size_inr: float
    position_size_usdt: float
    notional_size_usdt: float
    expected_gross_profit_inr: float
    expected_fees_inr: float
    expected_net_profit_inr: float
    risk_inr: float
    risk_reward_ratio: float

class RiskEngine:
    def __init__(self, cfg=config):
        self.cfg = cfg

    def calculate_trade_parameters(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr: float,
        confidence_score: float,
        current_balance_inr: float,
        active_positions_count: int = 0
    ) -> TradeOrderCalculation:
        """
        Dynamically calculates optimal leverage, position size, Stop Loss, Take Profit, Trailing Stop distance,
        and expected net profit after accounting for exchange fees, funding, and slippage.
        Fully deploys available wallet capital across open position slots in dynamic sizes with full leverage.
        """
        usd_inr = self.cfg.USD_INR_RATE

        # 1. Full 20x Leverage Application
        leverage = self.cfg.MAX_LEVERAGE

        # 2. Hard Stop Loss & Take Profit Distance with Dynamic Volatility Floor
        volatility_pct = (atr / entry_price * 100.0) if entry_price > 0 else 1.0
        sl_floor_pct = max(0.010, min(0.030, volatility_pct * 0.5 * 0.01))
        sl_distance = max(atr * self.cfg.HARD_STOP_LOSS_ATR_MULT, entry_price * sl_floor_pct)
        tp_distance = max(atr * self.cfg.HARD_TAKE_PROFIT_ATR_MULT, sl_distance * 2.0)  # at least 1:2 R:R

        if side == "LONG":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:  # SHORT
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        trailing_stop_distance = max(atr * self.cfg.TRAILING_STOP_ATR_MULT, entry_price * 0.005)

        # 3. 100% Full Capital Allocation Across Open Slots
        remaining_slots = max(1, self.cfg.MAX_CONCURRENT_POSITIONS - active_positions_count)
        position_size_inr = round(current_balance_inr / remaining_slots, 2)
        position_size_inr = max(self.cfg.MIN_TRADE_SIZE_INR, min(round(current_balance_inr, 2), position_size_inr))

        position_size_usdt = position_size_inr / usd_inr
        notional_size_usdt = position_size_usdt * leverage

        # 4. Expected Fee Calculation (Entry Taker + Exit Taker + Slippage + Funding)
        roundtrip_fee_rate = (self.cfg.TAKER_FEE_RATE * 2.0) + self.cfg.ESTIMATED_SLIPPAGE_RATE + self.cfg.ESTIMATED_FUNDING_RATE_PER_8H
        expected_fees_usdt = notional_size_usdt * roundtrip_fee_rate
        expected_fees_inr = expected_fees_usdt * usd_inr

        # 5. Expected Profit / Loss Calculation
        tp_pct_change = (tp_distance / entry_price)
        expected_gross_profit_usdt = notional_size_usdt * tp_pct_change
        expected_gross_profit_inr = expected_gross_profit_usdt * usd_inr

        expected_net_profit_inr = expected_gross_profit_inr - expected_fees_inr

        # Risk amount if SL is hit
        sl_pct_change = (sl_distance / entry_price)
        raw_risk_usdt = notional_size_usdt * sl_pct_change
        risk_inr = (raw_risk_usdt * usd_inr) + expected_fees_inr

        risk_reward_ratio = expected_net_profit_inr / max(1.0, risk_inr)

        return TradeOrderCalculation(
            symbol=symbol,
            side=side,
            entry_price=round(entry_price, 4),
            stop_loss_price=round(stop_loss, 4),
            take_profit_price=round(take_profit, 4),
            trailing_stop_distance=round(trailing_stop_distance, 4),
            leverage=leverage,
            position_size_inr=round(position_size_inr, 2),
            position_size_usdt=round(position_size_usdt, 4),
            notional_size_usdt=round(notional_size_usdt, 4),
            expected_gross_profit_inr=round(expected_gross_profit_inr, 2),
            expected_fees_inr=round(expected_fees_inr, 2),
            expected_net_profit_inr=round(expected_net_profit_inr, 2),
            risk_inr=round(risk_inr, 2),
            risk_reward_ratio=round(risk_reward_ratio, 2)
        )

    def calculate_actual_pnl(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        position_size_inr: float,
        leverage: int
    ) -> Tuple[float, float, float]:
        """
        Calculates exact raw PnL, total fees, and net PnL in INR upon trade exit.
        Returns: (raw_pnl_inr, total_fees_inr, net_pnl_inr)
        """
        usd_inr = self.cfg.USD_INR_RATE
        position_size_usdt = position_size_inr / usd_inr
        notional_usdt = position_size_usdt * leverage

        if side == "LONG":
            pct_change = (exit_price - entry_price) / entry_price
        else:  # SHORT
            pct_change = (entry_price - exit_price) / entry_price

        raw_pnl_usdt = notional_usdt * pct_change
        raw_pnl_inr = raw_pnl_usdt * usd_inr

        # Taker fee on entry, taker fee on exit + slippage
        roundtrip_fee_rate = (self.cfg.TAKER_FEE_RATE * 2.0) + self.cfg.ESTIMATED_SLIPPAGE_RATE
        total_fees_usdt = notional_usdt * roundtrip_fee_rate
        total_fees_inr = total_fees_usdt * usd_inr

        net_pnl_inr = raw_pnl_inr - total_fees_inr

        return round(raw_pnl_inr, 2), round(total_fees_inr, 2), round(net_pnl_inr, 2)

    def is_breakeven_triggered(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        position_size_inr: float,
        leverage: int
    ) -> bool:
        """
        Checks if current unrealized net profit has reached the Break-even activation threshold (+₹25 net).
        """
        raw_pnl_inr, total_fees_inr, net_pnl_inr = self.calculate_actual_pnl(
            side, entry_price, current_price, position_size_inr, leverage
        )
        return net_pnl_inr >= self.cfg.BREAK_EVEN_TRIGGER_PROFIT_INR

    def update_trailing_stop(
        self,
        side: str,
        current_price: float,
        peak_price: float,
        current_sl: float,
        trailing_distance: float,
        entry_price: float,
        is_breakeven: bool
    ) -> float:
        """
        Updates trailing stop price level to lock in maximum profit.
        """
        if side == "LONG":
            new_peak = max(peak_price, current_price)
            candidate_sl = new_peak - trailing_distance
            
            # If breakeven is active, SL must never drop below (entry_price + fee buffer)
            if is_breakeven:
                candidate_sl = max(candidate_sl, entry_price * 1.001)
                
            return max(current_sl, candidate_sl)
        else: # SHORT
            new_peak = min(peak_price, current_price)
            candidate_sl = new_peak + trailing_distance
            
            if is_breakeven:
                candidate_sl = min(candidate_sl, entry_price * 0.999)
                
            return min(current_sl, candidate_sl)

risk_engine = RiskEngine()
