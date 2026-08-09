import asyncio
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from config import config
from ai_signal_engine import ai_signal_engine, AISignalResult
from risk_engine import risk_engine, TradeOrderCalculation

logger = logging.getLogger("AutoTrader.Scanner")

@dataclass
class ScannedOpportunity:
    symbol: str
    signal: str
    confidence_score: float
    entry_price: float
    trade_calc: TradeOrderCalculation
    signal_result: AISignalResult

class MarketScanner:
    def __init__(self, exchange_adapter, cfg=config):
        self.adapter = exchange_adapter
        self.cfg = cfg
        self.latest_rankings: List[Dict[str, Any]] = []
        self.is_scanning: bool = False

    async def scan_single_pair(self, symbol: str, current_balance_inr: float, active_positions_count: int = 0) -> Optional[ScannedOpportunity]:
        """
        Scans a single pair, computes AI indicators, confidence score, and risk parameters.
        """
        try:
            df = await self.adapter.fetch_ohlcv(symbol, timeframe="1m", limit=100)
            if df is None or len(df) < 20:
                last_price = await self.adapter.fetch_ticker_price(symbol)
                if last_price > 0:
                    ranking_item = {
                        "symbol": symbol,
                        "signal": "ANALYZING",
                        "confidence_score": 50.0,
                        "price": last_price,
                        "rsi": 50.0,
                        "rvol": 1.0,
                        "trend_score": 0.0,
                        "momentum_score": 0.0,
                        "volume_score": 0.0,
                        "expected_net_pnl": 0.0
                    }
                    self._update_ranking_cache(ranking_item)
                return None

            sig_result = ai_signal_engine.analyze_candles(symbol, df)
            
            # Filter out ultra-low nominal price sub-cent tokens (<$0.005 / ~₹0.40) to prevent tick precision jumps
            if sig_result.entry_price < 0.005:
                return None
            
            # Store ranking entry for UI
            ranking_item = {
                "symbol": symbol,
                "signal": sig_result.signal,
                "confidence_score": sig_result.confidence_score,
                "price": sig_result.entry_price,
                "rsi": sig_result.details.get("rsi", 0),
                "rvol": sig_result.details.get("rvol", 0),
                "trend_score": sig_result.trend_score,
                "momentum_score": sig_result.momentum_score,
                "volume_score": sig_result.volume_score,
                "expected_net_pnl": 0.0
            }

            self._update_ranking_cache(ranking_item)

            if sig_result.signal != "NONE" and sig_result.confidence_score >= self.cfg.MIN_CONFIDENCE_SCORE:
                # Calculate trade risk/reward & expected net profit with dynamic 100% capital allocation
                trade_calc = risk_engine.calculate_trade_parameters(
                    symbol=symbol,
                    side=sig_result.signal,
                    entry_price=sig_result.entry_price,
                    atr=sig_result.atr,
                    confidence_score=sig_result.confidence_score,
                    current_balance_inr=current_balance_inr,
                    active_positions_count=active_positions_count
                )
                ranking_item["expected_net_pnl"] = trade_calc.expected_net_profit_inr

                # Ensure trade meets expected net profit target criteria
                if trade_calc.expected_net_profit_inr >= 5.0:  # Fast execution entry filter
                    return ScannedOpportunity(
                        symbol=symbol,
                        signal=sig_result.signal,
                        confidence_score=sig_result.confidence_score,
                        entry_price=sig_result.entry_price,
                        trade_calc=trade_calc,
                        signal_result=sig_result
                    )
            else:
                # Estimate expected PnL for top potential setups
                est_side = "LONG" if sig_result.details.get("long_score", 0) >= sig_result.details.get("short_score", 0) else "SHORT"
                est_calc = risk_engine.calculate_trade_parameters(
                    symbol=symbol,
                    side=est_side,
                    entry_price=sig_result.entry_price,
                    atr=sig_result.atr,
                    confidence_score=sig_result.confidence_score,
                    current_balance_inr=current_balance_inr,
                    active_positions_count=active_positions_count
                )
                ranking_item["expected_net_pnl"] = est_calc.expected_net_profit_inr

            return None

        except Exception as e:
            logger.error(f"Error scanning pair {symbol}: {e}")
            return None

    def _update_ranking_cache(self, item: Dict[str, Any]):
        # Replace or append item in latest_rankings
        self.latest_rankings = [r for r in self.latest_rankings if r["symbol"] != item["symbol"]]
        self.latest_rankings.append(item)

    async def scan_for_all_opportunities(self, current_balance_inr: float, active_positions_count: int = 0) -> List[ScannedOpportunity]:
        """
        Parallel 24/7 scanning of watchlist futures pairs, returning ALL valid high-confidence opportunities.
        """
        self.is_scanning = True
        valid_opps: List[ScannedOpportunity] = []
        pairs_to_scan = self.cfg.WATCHLIST_PAIRS[:100]

        chunk_size = 30
        for i in range(0, len(pairs_to_scan), chunk_size):
            chunk = pairs_to_scan[i:i + chunk_size]
            tasks = [self.scan_single_pair(sym, current_balance_inr, active_positions_count) for sym in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, ScannedOpportunity) and res is not None:
                    valid_opps.append(res)
            await asyncio.sleep(0.01)

        self.is_scanning = False

        valid_opps.sort(key=lambda x: (x.confidence_score, x.trade_calc.expected_net_profit_inr), reverse=True)
        return valid_opps

    async def scan_all_pairs(self, current_balance_inr: float) -> Optional[ScannedOpportunity]:
        """
        Parallel 24/7 scanning returning top single opportunity.
        """
        valid_opps = await self.scan_for_all_opportunities(current_balance_inr)
        if not valid_opps:
            return None
        return valid_opps[0]


    def get_rankings(self) -> List[Dict[str, Any]]:
        """
        Prioritizes active >=80% confidence signals at top of table, followed by top setup candidates.
        """
        def ranking_key(item):
            is_active_signal = 1 if item["signal"] in ["LONG", "SHORT"] and item["confidence_score"] >= self.cfg.MIN_CONFIDENCE_SCORE else 0
            return (is_active_signal, item["confidence_score"], item["expected_net_pnl"])

        sorted_rankings = sorted(self.latest_rankings, key=ranking_key, reverse=True)
        return sorted_rankings[:15]

