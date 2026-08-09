import asyncio
import os
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List
from config import config
from database import db_manager

from contextlib import asynccontextmanager

logger = logging.getLogger("AutoTrader.Web")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Clean shutdown of exchange connections
    try:
        adapter = system_components.get("exchange")
        if adapter and hasattr(adapter, "close"):
            logger.info("Lifespan shutdown: closing exchange connection cleanly...")
            await adapter.close()
    except Exception as e:
        logger.debug(f"Lifespan shutdown exchange error: {e}")

app = FastAPI(title="AutoTrader_AI Dashboard", lifespan=lifespan)

# Serve static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# Global state references populated by main.py
system_components = {
    "scanner": None,
    "position_mgr": None,
    "wallet_mgr": None,
    "exchange": None
}

@app.get("/")
async def get_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>AutoTrader_AI API Running</h2>")

@app.get("/api/state")
async def get_state():
    pos_mgr = system_components.get("position_mgr")
    wallet_mgr = system_components.get("wallet_mgr")
    scanner = system_components.get("scanner")

    active_positions = pos_mgr.get_active_positions_list() if pos_mgr else []
    wallet_summary = await wallet_mgr.async_get_wallet_summary() if wallet_mgr else {}
    rankings = scanner.get_rankings() if scanner else []
    recent_trades = db_manager.get_recent_trades(20)
    recent_transfers = db_manager.get_transfers(10)

    return JSONResponse({
        "status": "RUNNING" if config.IS_BOT_RUNNING else "PAUSED",
        "is_bot_running": config.IS_BOT_RUNNING,
        "trading_mode": config.TRADING_MODE,
        "exchange_name": config.EXCHANGE_NAME,
        "has_api_key": bool(config.API_KEY),
        "wallet": wallet_summary,
        "active_positions": active_positions,
        "active_position": active_positions[0] if active_positions else None,
        "pair_rankings": rankings,
        "recent_trades": recent_trades,
        "recent_transfers": recent_transfers
    })

@app.get("/api/market-predictions")
async def get_market_predictions():
    scanner = system_components.get("scanner")
    if not scanner or not scanner.latest_rankings:
        return JSONResponse({"status": "SCANNERS_INITIALIZING", "message": "Market analysis scanner starting..."})

    rankings = scanner.latest_rankings
    long_candidates = [r for r in rankings if r.get("signal") == "LONG" or r.get("trend_score", 0) > 15]
    short_candidates = [r for r in rankings if r.get("signal") == "SHORT" or r.get("trend_score", 0) < 10]
    
    # Market Regime Calculation
    bull_count = sum(1 for r in rankings if r.get("signal") == "LONG")
    bear_count = sum(1 for r in rankings if r.get("signal") == "SHORT")
    
    if bull_count > bear_count + 3:
        regime = "STRONG_BULLISH_TREND"
    elif bear_count > bull_count + 3:
        regime = "STRONG_BEARISH_TREND"
    else:
        regime = "CONSOLIDATION_NEUTRAL"

    top_longs = sorted(rankings, key=lambda x: (x.get("signal") == "LONG", x.get("confidence_score", 0)), reverse=True)[:5]
    top_shorts = sorted(rankings, key=lambda x: (x.get("signal") == "SHORT", x.get("confidence_score", 0)), reverse=True)[:5]

    return JSONResponse({
        "timestamp": db_manager._get_timestamp(),
        "market_regime": regime,
        "scanned_pairs_count": len(rankings),
        "bullish_signals_count": bull_count,
        "bearish_signals_count": bear_count,
        "top_predicted_longs": top_longs,
        "top_predicted_shorts": top_shorts,
        "all_rankings": rankings[:25]
    })

@app.post("/api/toggle-bot")
async def toggle_bot():
    config.IS_BOT_RUNNING = not config.IS_BOT_RUNNING
    status_str = "STARTED" if config.IS_BOT_RUNNING else "PAUSED"
    
    closed_msg = ""
    if not config.IS_BOT_RUNNING:
        pos_mgr = system_components.get("position_mgr")
        if pos_mgr and pos_mgr.has_active_position():
            closed_list = await pos_mgr.close_all_positions("CLOSED_PAUSED", "Engine paused by user - All open positions exited.")
            closed_msg = f" Closed {len(closed_list)} active position(s) on exchange."

    msg = f"AutoTrader_AI engine is now {status_str}.{closed_msg}"
    db_manager.log_event("INFO", "BOT_CONTROL", f"User toggled bot state to: {status_str}.{closed_msg}")
    
    return JSONResponse({
        "success": True,
        "is_bot_running": config.IS_BOT_RUNNING,
        "message": msg
    })

@app.post("/api/close-single-position")
async def close_single_position(request: Request):
    try:
        body = await request.json()
        symbol = body.get("symbol", "")
        pos_mgr = system_components.get("position_mgr")
        if not pos_mgr or not symbol:
            return JSONResponse({"success": False, "message": "Invalid position symbol or manager not ready"})
        
        result = await pos_mgr.close_single_position(symbol, "CLOSED_MANUAL", f"Manual exit requested for {symbol} via web dashboard")
        if result:
            return JSONResponse({"success": True, "message": f"Successfully closed position for {symbol}!", "result": result})
        return JSONResponse({"success": False, "message": f"Position for {symbol} not found or already closed."})
    except Exception as e:
        logger.error(f"Error in close_single_position: {e}", exc_info=True)
        return JSONResponse({"success": False, "message": f"Failed to close position: {str(e)}"})

@app.post("/api/reset-paper-balance")
async def reset_paper_balance():
    wallet_mgr = system_components.get("wallet_mgr")
    if not wallet_mgr:
        return JSONResponse({"success": False, "message": "Wallet manager not ready"})
    
    success, msg = wallet_mgr.reset_paper_balance(1000.0)
    return JSONResponse({"success": success, "message": msg})

@app.post("/api/set-trading-mode")
async def set_trading_mode(request: Request):
    body = await request.json()
    new_mode = body.get("mode", "PAPER").upper()
    
    if new_mode == "LIVE" and (not config.API_KEY or not config.API_SECRET):
        return JSONResponse({
            "success": False,
            "requires_keys": True,
            "message": "Cannot switch to LIVE mode without Exchange API Keys! Please click 'Connect Wallet' to enter your API Key & Secret."
        })

    # Re-initialize exchange adapter
    from exchange_adapter import get_exchange_adapter
    from wallet_manager import WalletManager
    from position_manager import PositionManager
    from market_scanner import MarketScanner

    temp_cfg = config
    temp_cfg.TRADING_MODE = new_mode
    new_adapter = get_exchange_adapter(temp_cfg)

    if new_mode == "LIVE" and hasattr(new_adapter, "validate_credentials"):
        is_valid, validation_msg = await new_adapter.validate_credentials()
        if not is_valid:
            db_manager.log_event("ERROR", "MODE_SWITCH_FAILED", f"Could not switch to LIVE mode: {validation_msg}")
            return JSONResponse({
                "success": False,
                "requires_keys": True,
                "message": f"⚠️ Connection Failed: {validation_msg}. Please check your API Key & Secret."
            })

    config.TRADING_MODE = new_mode

    # Write updated mode to .env on disk
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"TRADING_MODE={new_mode}\nEXCHANGE_NAME={config.EXCHANGE_NAME}\nEXCHANGE_API_KEY={config.API_KEY}\nEXCHANGE_API_SECRET={config.API_SECRET}\n")

    system_components["exchange"] = new_adapter
    system_components["wallet_mgr"] = WalletManager(new_adapter, config)
    system_components["position_mgr"] = PositionManager(new_adapter, system_components["wallet_mgr"], config)
    system_components["scanner"] = MarketScanner(new_adapter, config)

    db_manager.log_event("INFO", "MODE_SWITCH", f"Switched Trading Mode to {new_mode}")
    return JSONResponse({
        "success": True,
        "mode": new_mode,
        "message": f"Trading Mode switched to {new_mode}!"
    })

@app.post("/api/save-credentials")
async def save_credentials(request: Request):
    try:
        body = await request.json()
        exchange_name = body.get("exchange_name", "coindcx")
        api_key = str(body.get("api_key", "")).strip()
        api_secret = str(body.get("api_secret", "")).strip()
        mode = body.get("trading_mode", "LIVE").upper()
        usd_inr_rate = float(body.get("usd_inr_rate", 85.0))

        config.update_credentials(exchange_name, api_key, api_secret, mode, usd_inr_rate)

        # Re-initialize exchange adapter live
        from exchange_adapter import get_exchange_adapter
        from wallet_manager import WalletManager
        from position_manager import PositionManager
        from market_scanner import MarketScanner

        new_adapter = get_exchange_adapter(config)

        # Validate LIVE mode credentials with exchange API before confirming connection
        if mode == "LIVE" and hasattr(new_adapter, "validate_credentials"):
            is_valid, validation_msg = await new_adapter.validate_credentials()
            if not is_valid:
                db_manager.log_event("ERROR", "CREDENTIALS_FAILED", f"Exchange Connection Failed: {validation_msg}")
                return JSONResponse({
                    "success": False,
                    "message": f"⚠️ Connection Failed: {validation_msg}. Please check your API Key and Secret on {exchange_name.upper()}!"
                })

        # Safely persist valid credentials to .env file on disk if environment permits
        try:
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"TRADING_MODE={mode}\nEXCHANGE_NAME={exchange_name}\nEXCHANGE_API_KEY={api_key}\nEXCHANGE_API_SECRET={api_secret}\n")
        except Exception as env_err:
            logger.debug(f"Skipping .env disk write in cloud environment: {env_err}")
        
        # Update global system components
        system_components["exchange"] = new_adapter
        system_components["wallet_mgr"] = WalletManager(new_adapter, config)
        system_components["position_mgr"] = PositionManager(new_adapter, system_components["wallet_mgr"], config)
        system_components["scanner"] = MarketScanner(new_adapter, config)

        db_manager.log_event("INFO", "CREDENTIALS", f"Connected to {exchange_name.upper()} in {mode} Trading Mode!")

        return JSONResponse({
            "success": True,
            "message": f"Successfully connected to {exchange_name.upper()} in {mode} Mode! Credentials saved permanently.",
            "mode": mode,
            "exchange": exchange_name.upper()
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Failed to save credentials: {str(e)}"})

@app.post("/api/transfer-now")
async def manual_transfer():
    wallet_mgr = system_components.get("wallet_mgr")
    if not wallet_mgr:
        return JSONResponse({"success": False, "message": "Wallet manager not ready"})
    
    success, msg, amount = wallet_mgr.execute_daily_profit_transfer()
    return JSONResponse({"success": success, "message": msg, "amount": amount})

@app.post("/api/close-position-now")
async def manual_close_position(request: Request):
    try:
        pos_mgr = system_components.get("position_mgr")
        if not pos_mgr or not pos_mgr.has_active_position():
            return JSONResponse({"success": False, "message": "No active positions to close"})
        
        results = await pos_mgr.close_all_positions("CLOSED_MANUAL", "Manual emergency exit requested by user via web dashboard")
        return JSONResponse({"success": True, "message": f"Successfully closed {len(results)} active position(s)!", "results": results})
    except Exception as e:
        logger.error(f"Error in manual_close_position: {e}", exc_info=True)
        return JSONResponse({"success": False, "message": f"Failed to close position: {str(e)}"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send live telemetry every 1 second
            pos_mgr = system_components.get("position_mgr")
            wallet_mgr = system_components.get("wallet_mgr")
            scanner = system_components.get("scanner")

            wallet_summary = await wallet_mgr.async_get_wallet_summary() if wallet_mgr else {}
            payload = {
                "type": "TELEMETRY",
                "wallet": wallet_summary,
                "active_positions": pos_mgr.get_active_positions_list() if pos_mgr else [],
                "active_position": pos_mgr.get_active_positions_list()[0] if pos_mgr and pos_mgr.get_active_positions_list() else None,
                "rankings": scanner.get_rankings() if scanner else [],
                "recent_trades": db_manager.get_recent_trades(10),
                "logs": db_manager.get_logs(15)
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
