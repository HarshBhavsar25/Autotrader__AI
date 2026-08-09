import asyncio
import logging
from typing import Dict, List, Any, Optional
from config import config
from risk_engine import risk_engine, TradeOrderCalculation
from ai_signal_engine import ai_signal_engine
from database import db_manager

logger = logging.getLogger("AutoTrader.PositionManager")

class ActivePosition:
    def __init__(self, db_trade_id: int, opp, trade_calc: TradeOrderCalculation):
        self.db_trade_id = db_trade_id
        self.symbol = opp.symbol
        self.side = opp.signal  # "LONG" or "SHORT"
        self.entry_price = opp.entry_price
        self.current_price = opp.entry_price
        self.peak_price = opp.entry_price
        self.stop_loss = trade_calc.stop_loss_price
        self.take_profit = trade_calc.take_profit_price
        self.trailing_stop_distance = trade_calc.trailing_stop_distance
        self.leverage = trade_calc.leverage
        self.position_size_inr = trade_calc.position_size_inr
        self.position_size_usdt = trade_calc.position_size_usdt
        self.confidence_score = opp.confidence_score
        self.entry_time = asyncio.get_event_loop().time()
        self.is_breakeven = False
        self.max_profit_reached_inr = 0.0

SECTOR_MAP = {
    "MEME": ["PEPE/USDT", "WIF/USDT", "BONK/USDT", "FLOKI/USDT", "DOGE/USDT", "SHIB/USDT"],
    "MAJOR": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
    "L1_L2": ["AVAX/USDT", "LINK/USDT", "ADA/USDT", "SUI/USDT", "NEAR/USDT", "ARB/USDT", "OP/USDT", "MATIC/USDT", "APT/USDT", "SEI/USDT", "FTM/USDT", "DOT/USDT"],
    "ALT_HIGH": ["FET/USDT", "RENDER/USDT", "INJ/USDT", "TIA/USDT", "RUNE/USDT", "LTC/USDT", "FIL/USDT", "STX/USDT", "JUP/USDT", "NOT/USDT", "ORDI/USDT"]
}

class PositionManager:
    """
    Multi-Position Concurrent Lifecycle Manager.
    Manages up to MAX_CONCURRENT_POSITIONS open trades simultaneously with Sector Correlation Protection.
    """
    def __init__(self, exchange_adapter, wallet_manager, cfg=config):
        self.adapter = exchange_adapter
        self.wallet_mgr = wallet_manager
        self.cfg = cfg
        self.active_positions: Dict[str, ActivePosition] = {}

    def get_active_count(self) -> int:
        return len(self.active_positions)

    def is_symbol_open(self, symbol: str) -> bool:
        return symbol in self.active_positions

    def get_symbol_sector(self, symbol: str) -> str:
        for sector, symbols in SECTOR_MAP.items():
            if symbol in symbols:
                return sector
        return "OTHER"

    def get_sector_position_count(self, sector: str) -> int:
        return sum(1 for sym in self.active_positions if self.get_symbol_sector(sym) == sector)

    def can_open_new_position(self, current_balance_inr: float, symbol: Optional[str] = None) -> bool:
        if len(self.active_positions) >= self.cfg.MAX_CONCURRENT_POSITIONS:
            return False
        if current_balance_inr < self.cfg.MIN_TRADE_SIZE_INR:
            return False
        if symbol:
            sector = self.get_symbol_sector(symbol)
            # Enforce correlation limit: max 2 positions per sector
            if self.get_sector_position_count(sector) >= 2:
                return False
        return True

    async def open_position(self, opp) -> Optional[ActivePosition]:
        """
        Executes trade entry, records in database, and sets up position monitoring.
        """
        trade_calc = opp.trade_calc

        # Submit real futures order on live exchange ONLY when in LIVE mode with a real exchange adapter
        from exchange_adapter import PaperExchangeAdapter
        is_paper_adapter = isinstance(self.adapter, PaperExchangeAdapter)
        if self.cfg.TRADING_MODE.upper() == "LIVE" and not is_paper_adapter and hasattr(self.adapter, "create_futures_order"):
            try:
                res = await self.adapter.create_futures_order(
                    symbol=opp.symbol,
                    side=opp.signal,
                    size_inr=trade_calc.position_size_inr,
                    leverage=trade_calc.leverage,
                    entry_price=opp.entry_price
                )
                if isinstance(res, dict) and not res.get("success", False):
                    err_msg = res.get("error", "Unknown exchange order error")
                    logger.error(f"Live exchange order failed for {opp.symbol}: {err_msg}")
                    db_manager.log_event("WARNING", "LIVE_ORDER_FAILED", f"Live order for {opp.symbol} rejected: {err_msg}")
                    return None
            except Exception as err:
                logger.error(f"Live order submission exception for {opp.symbol}: {err}")
                return None

        trade_id = db_manager.record_trade_entry(
            symbol=opp.symbol,
            side=opp.signal,
            entry_price=opp.entry_price,
            size_inr=trade_calc.position_size_inr,
            size_usdt=trade_calc.position_size_usdt,
            leverage=trade_calc.leverage,
            confidence_score=opp.confidence_score,
            metrics_json=opp.signal_result.details
        )

        pos = ActivePosition(trade_id, opp, trade_calc)
        self.active_positions[opp.symbol] = pos

        msg = (f"OPENED {pos.side} on {pos.symbol} @ ₹{pos.entry_price} | Leverage: {pos.leverage}x | "
               f"Size: ₹{pos.position_size_inr} | SL: {pos.stop_loss} | TP: {pos.take_profit} | Confidence: {pos.confidence_score}%")
        logger.info(msg)
        db_manager.log_event("INFO", "TRADE_OPEN", msg)

        return pos

    async def monitor_active_positions(self) -> List[Dict[str, Any]]:
        """
        High-frequency monitoring loop (0.5s) checking SL, TP, Trailing Stop, Break-even, and Early Exit
        across ALL open concurrent positions. Returns list of closed trade summaries.
        """
        closed_summaries: List[Dict[str, Any]] = []
        symbols_to_check = list(self.active_positions.keys())

        for symbol in symbols_to_check:
            pos = self.active_positions.get(symbol)
            if not pos:
                continue

            current_price = await self.adapter.fetch_ticker_price(pos.symbol)
            if current_price <= 0:
                continue

            pos.current_price = current_price

            # Update peak price
            if pos.side == "LONG":
                pos.peak_price = max(pos.peak_price, current_price)
            else:
                pos.peak_price = min(pos.peak_price, current_price)

            raw_pnl_inr, total_fees_inr, net_pnl_inr = risk_engine.calculate_actual_pnl(
                pos.side, pos.entry_price, current_price, pos.position_size_inr, pos.leverage
            )
            pos.max_profit_reached_inr = max(pos.max_profit_reached_inr, net_pnl_inr)

            # 1. Break-even check (+₹25 net profit)
            if not pos.is_breakeven and net_pnl_inr >= self.cfg.BREAK_EVEN_TRIGGER_PROFIT_INR:
                pos.is_breakeven = True
                if pos.side == "LONG":
                    pos.stop_loss = max(pos.stop_loss, pos.entry_price * 1.001)
                else:
                    pos.stop_loss = min(pos.stop_loss, pos.entry_price * 0.999)
                
                db_manager.log_event("INFO", "BREAKEVEN_ACTIVATED", f"Break-even stop activated for {pos.symbol}! SL moved to {pos.stop_loss}")
                logger.info(f"Break-even stop activated for {pos.symbol} @ {pos.stop_loss}")

            # 2. Update Trailing Stop
            new_sl = risk_engine.update_trailing_stop(
                side=pos.side,
                current_price=current_price,
                peak_price=pos.peak_price,
                current_sl=pos.stop_loss,
                trailing_distance=pos.trailing_stop_distance,
                entry_price=pos.entry_price,
                is_breakeven=pos.is_breakeven
            )
            if new_sl != pos.stop_loss:
                pos.stop_loss = new_sl

            # 3. Check Take Profit Hit
            tp_triggered = (pos.side == "LONG" and current_price >= pos.take_profit) or \
                           (pos.side == "SHORT" and current_price <= pos.take_profit)
            if tp_triggered:
                summary = await self.close_single_position(symbol, "CLOSED_TP", f"Take Profit reached @ {current_price}")
                if summary: closed_summaries.append(summary)
                continue

            # 4. Check Stop Loss / Trailing Stop Hit
            sl_triggered = (pos.side == "LONG" and current_price <= pos.stop_loss) or \
                           (pos.side == "SHORT" and current_price >= pos.stop_loss)
            if sl_triggered:
                status_label = "CLOSED_BREAKEVEN" if pos.is_breakeven and net_pnl_inr >= 0 else ("CLOSED_TRAILING" if pos.is_breakeven else "CLOSED_SL")
                summary = await self.close_single_position(symbol, status_label, f"Stop Loss / Trailing Stop triggered @ {current_price}")
                if summary: closed_summaries.append(summary)
                continue

            # 5. High-Speed Scalp Timer Exit (Seconds to 1 Minute execution)
            elapsed_sec = asyncio.get_event_loop().time() - pos.entry_time
            if elapsed_sec >= 45.0 and net_pnl_inr >= 5.0:
                summary = await self.close_single_position(symbol, "CLOSED_SCALP_PROFIT", f"Fast 45s scalp profit taken (+₹{net_pnl_inr:.2f})")
                if summary: closed_summaries.append(summary)
                continue
            elif elapsed_sec >= 90.0:
                summary = await self.close_single_position(symbol, "CLOSED_SCALP_TIMEOUT", f"Scalp 90s timeout exit @ ₹{current_price} (PnL: ₹{net_pnl_inr:.2f})")
                if summary: closed_summaries.append(summary)
                continue

            # 6. Check Early Exit / Market Deterioration
            try:
                df = await self.adapter.fetch_ohlcv(pos.symbol, timeframe="5m", limit=30)
                if df is not None:
                    deteriorated, reason = ai_signal_engine.check_market_deterioration(pos.side, df)
                    if deteriorated:
                        summary = await self.close_single_position(symbol, "CLOSED_EARLY", f"Market deterioration detected: {reason}")
                        if summary: closed_summaries.append(summary)
            except Exception:
                pass

    def has_active_position(self) -> bool:
        return len(self.active_positions) > 0

    async def close_all_positions(self, status: str = "CLOSED_MANUAL", exit_reason: str = "Manual emergency exit") -> List[Dict[str, Any]]:
        results = []
        symbols = list(self.active_positions.keys())
        for symbol in symbols:
            res = await self.close_single_position(symbol, status, exit_reason)
            if res:
                results.append(res)
        return results

    async def close_single_position(self, symbol: str, status: str, exit_reason: str) -> Optional[Dict[str, Any]]:

        pos = self.active_positions.get(symbol)
        if not pos:
            return None

        exit_price = pos.current_price
        raw_pnl_inr, total_fees_inr, net_pnl_inr = risk_engine.calculate_actual_pnl(
            pos.side, pos.entry_price, exit_price, pos.position_size_inr, pos.leverage
        )

        db_manager.update_trade_exit(
            trade_id=pos.db_trade_id,
            exit_price=exit_price,
            raw_pnl_inr=raw_pnl_inr,
            net_pnl_inr=net_pnl_inr,
            fees_inr=total_fees_inr,
            status=status,
            exit_reason=exit_reason,
            max_profit_reached=pos.max_profit_reached_inr,
            breakeven_triggered=pos.is_breakeven
        )

        self.wallet_mgr.record_completed_trade(net_pnl_inr)

        close_summary = {
            "trade_id": pos.db_trade_id,
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "raw_pnl_inr": raw_pnl_inr,
            "net_pnl_inr": net_pnl_inr,
            "fees_inr": total_fees_inr,
            "status": status,
            "exit_reason": exit_reason,
            "max_profit_reached_inr": pos.max_profit_reached_inr,
            "is_breakeven": pos.is_breakeven
        }

        # Submit live position exit order on live exchange when in LIVE mode
        if self.cfg.TRADING_MODE.upper() == "LIVE" and hasattr(self.adapter, "close_futures_order"):
            try:
                await self.adapter.close_futures_order(
                    symbol=pos.symbol,
                    side=pos.side,
                    entry_price=pos.entry_price
                )
            except Exception as err:
                logger.error(f"Live order exit error for {pos.symbol}: {err}")

        msg = (f"CLOSED {pos.side} on {pos.symbol} | Reason: {exit_reason} | "
               f"Exit Price: ₹{exit_price} | Net PnL: ₹{net_pnl_inr:.2f} (Fees: ₹{total_fees_inr:.2f})")
        logger.info(msg)
        db_manager.log_event("INFO", "TRADE_CLOSE", msg)

        del self.active_positions[symbol]
        return close_summary

    def get_active_positions_list(self) -> List[Dict[str, Any]]:
        result = []
        for symbol, pos in self.active_positions.items():
            raw_pnl, fees, net_pnl = risk_engine.calculate_actual_pnl(
                pos.side, pos.entry_price, pos.current_price, pos.position_size_inr, pos.leverage
            )
            result.append({
                "trade_id": pos.db_trade_id,
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "peak_price": pos.peak_price,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "trailing_stop_distance": pos.trailing_stop_distance,
                "leverage": pos.leverage,
                "position_size_inr": pos.position_size_inr,
                "position_size_usdt": pos.position_size_usdt,
                "confidence_score": pos.confidence_score,
                "raw_pnl_inr": raw_pnl,
                "fees_inr": fees,
                "net_pnl_inr": net_pnl,
                "is_breakeven": pos.is_breakeven,
                "max_profit_reached_inr": pos.max_profit_reached_inr
            })
        return result
