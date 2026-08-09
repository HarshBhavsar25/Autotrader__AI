import asyncio
import logging
import sys
import io
import os
import uvicorn
from config import config
from database import db_manager
from exchange_adapter import get_exchange_adapter, PaperExchangeAdapter
from ai_signal_engine import ai_signal_engine
from risk_engine import risk_engine
from market_scanner import MarketScanner
from wallet_manager import WalletManager
from position_manager import PositionManager
from web_dashboard import app, system_components

# Configure logging with UTF-8 support for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AutoTrader.Main")

async def dynamic_pair_discovery(adapter):
    """
    Dynamically fetches all active trading pairs from the exchange.
    """
    try:
        if hasattr(adapter, "exchange") and hasattr(adapter.exchange, "load_markets"):
            logger.info("Dynamically fetching all available exchange market pairs...")
            markets = await adapter.exchange.load_markets()
            active_pairs = []
            for symbol, market in markets.items():
                if market.get('active', True) and (market.get('swap', False) or market.get('future', False) or market.get('spot', False)):
                    if symbol.endswith("/USDT") or symbol.endswith("/INR") or symbol.endswith(":USDT"):
                        active_pairs.append(symbol)
            if active_pairs:
                logger.info(f"Discovered {len(active_pairs)} active trading pairs on exchange!")
                combined = list(dict.fromkeys(config.WATCHLIST_PAIRS + active_pairs))
                config.WATCHLIST_PAIRS = combined[:100] # Expand watchlist up to top 100 liquid pairs
                logger.info(f"Updated Watchlist: Active scanning across {len(config.WATCHLIST_PAIRS)} pairs!")
    except Exception as e:
        logger.warning(f"Could not load dynamic markets, falling back to default watchlist: {e}")

async def autotrader_engine_loop():
    """
    Main 24/7 continuous multi-position trading execution loop.
    Supports up to MAX_CONCURRENT_POSITIONS (4) simultaneous open trades.
    Dynamically references updated system_components when user updates credentials or switches modes.
    """
    logger.info("Starting 24/7 AutoTrader_AI Engine Loop (Multi-Position Concurrent Mode)...")
    db_manager.log_event("INFO", "SYSTEM", "24/7 AutoTrader_AI Multi-Position Engine Started.")

    while True:
        try:
            # Dynamically read current active system components
            wallet_mgr = system_components.get("wallet_mgr")
            pos_mgr = system_components.get("position_mgr")
            scanner = system_components.get("scanner")

            if not wallet_mgr or not pos_mgr or not scanner:
                await asyncio.sleep(1.0)
                continue

            # Check if bot engine is paused by user
            if not config.IS_BOT_RUNNING:
                await asyncio.sleep(1.0)
                continue

            current_balance = await wallet_mgr.adapter.fetch_live_balance_inr() if hasattr(wallet_mgr.adapter, "fetch_live_balance_inr") else wallet_mgr.adapter.get_balance_inr()

            available_capital = current_balance if current_balance >= 10.0 else float(config.INITIAL_CAPITAL_INR)

            # 1. High-frequency monitoring loop across all open active positions
            if pos_mgr.get_active_count() > 0:
                closed_trades = await pos_mgr.monitor_active_positions()
                if closed_trades:
                    for closed_trade in closed_trades:
                        db_manager.log_event("INFO", "TRADE_EVENT", f"Trade completed on {closed_trade['symbol']}. Net PnL: ₹{closed_trade['net_pnl_inr']:.2f}")


            # 2. Check if we have available slots and balance to open new trade positions
            if pos_mgr.can_open_new_position(available_capital):
                active_cnt = pos_mgr.get_active_count()
                opportunities = await scanner.scan_for_all_opportunities(
                    current_balance_inr=available_capital,
                    active_positions_count=active_cnt
                )
                
                for opportunity in opportunities:
                    if not pos_mgr.can_open_new_position(available_capital, opportunity.symbol):
                        continue

                    if not pos_mgr.is_symbol_open(opportunity.symbol):
                        msg = (f"Executing Concurrent Trade ({pos_mgr.get_active_count() + 1}/{config.MAX_CONCURRENT_POSITIONS})! "
                               f"Pair: {opportunity.symbol} | Signal: {opportunity.signal} | Confidence: {opportunity.confidence_score}% | "
                               f"Size: ₹{opportunity.trade_calc.position_size_inr} | Leverage: {opportunity.trade_calc.leverage}x | Exp Profit: ₹{opportunity.trade_calc.expected_net_profit_inr}")
                        logger.info(msg)
                        db_manager.log_event("INFO", "ENTRY_SIGNAL", msg)

                        # Open position concurrently
                        await pos_mgr.open_position(opportunity)


            # Pause briefly before next scan cycle
            await asyncio.sleep(config.SCANNER_INTERVAL_SECONDS)

        except Exception as e:
            logger.error(f"Error in autotrader loop: {e}", exc_info=True)
            await asyncio.sleep(2.0)

async def main():
    logger.info("Initializing AutoTrader_AI System...")

    # 1. Initialize Exchange Adapter (Paper or Live)
    adapter = get_exchange_adapter(config)
    try:
        await dynamic_pair_discovery(adapter)

        # 2. Initialize Managers
        wallet_mgr = WalletManager(adapter, config)
        pos_mgr = PositionManager(adapter, wallet_mgr, config)
        scanner = MarketScanner(adapter, config)

        # Populate references for Web Dashboard REST/WebSocket API
        system_components["scanner"] = scanner
        system_components["position_mgr"] = pos_mgr
        system_components["wallet_mgr"] = wallet_mgr
        system_components["exchange"] = adapter

        # 3. Launch 07:00 AM Daily Profit Transfer Background Task
        asyncio.create_task(wallet_mgr.start_0700_scheduler())

        # 4. Launch 24/7 Trading Engine Loop
        asyncio.create_task(autotrader_engine_loop())

        # 5. Launch FastAPI Web Server on http://0.0.0.0:$PORT
        port = int(os.environ.get("PORT", 8000))
        server_config = uvicorn.Config(app=app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(server_config)
        
        logger.info(f"Web Dashboard starting on http://0.0.0.0:{port}")
        await server.serve()
    finally:
        logger.info("Shutting down AutoTrader_AI and closing CCXT exchange resources...")
        if adapter and hasattr(adapter, "close"):
            try:
                await adapter.close()
                logger.info("CCXT exchange connection closed cleanly.")
            except Exception as e:
                logger.debug(f"Error closing exchange: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("AutoTrader_AI shutdown gracefully.")
