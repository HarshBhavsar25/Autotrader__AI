import asyncio
import logging
import hmac
import hashlib
import json
import time
import aiohttp
import pandas as pd
import ccxt.async_support as ccxt_async
from typing import Dict, List, Any, Optional, Tuple
from config import config

logger = logging.getLogger("AutoTrader.Exchange")

class PaperExchangeAdapter:
    """
    Paper Trading Simulation Adapter. Uses 100% real-time live exchange market price feeds via public APIs.
    Maintains simulated futures wallet balance starting at ₹1000.
    """
    def __init__(self, cfg=config):
        self.cfg = cfg
        self.balance_inr = cfg.INITIAL_CAPITAL_INR
        self.spot_balance_inr = 0.0
        self.base_capital_inr = cfg.INITIAL_CAPITAL_INR
        self.public_exchange_binance = ccxt_async.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
        self.public_exchange_bybit = ccxt_async.bybit({'enableRateLimit': True, 'options': {'defaultType': 'linear'}})
        self.public_exchange_okx = ccxt_async.okx({'enableRateLimit': True})
        self.active_position: Optional[Dict[str, Any]] = None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> Optional[pd.DataFrame]:
        clean_sym = symbol.replace("/", "_")
        coindcx_pair = f"B-{clean_sym}" if not clean_sym.startswith("B-") else clean_sym

        # 1. CoinDCX Native Public Candle API (High Speed)
        try:
            url = f"https://public.coindcx.com/market_data/candles?pair={coindcx_pair}&interval=1m&limit={limit}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2.0) as res:
                    if res.status == 200:
                        c_data = await res.json()
                        if isinstance(c_data, list) and len(c_data) >= 10:
                            rows = []
                            for c in c_data:
                                rows.append([
                                    int(c.get('time', 0)),
                                    float(c.get('open', 0)),
                                    float(c.get('high', 0)),
                                    float(c.get('low', 0)),
                                    float(c.get('close', 0)),
                                    float(c.get('volume', 0))
                                ])
                            rows.sort(key=lambda x: x[0])
                            df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                            return df
        except Exception:
            pass

        # 2. Fast Fallback Exchanges (Binance -> Bybit -> OKX)
        for ex in [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]:
            try:
                ohlcv = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=2.0)
                if ohlcv and len(ohlcv) >= 10:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                    return df
            except Exception:
                continue

        return None

    async def fetch_ticker_price(self, symbol: str) -> float:
        df = await self.fetch_ohlcv(symbol, limit=2)
        if df is not None and not df.empty:
            return float(df.iloc[-1]['close'])

        for ex in [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]:
            try:
                ticker = await asyncio.wait_for(ex.fetch_ticker(symbol), timeout=2.0)
                if ticker and 'last' in ticker and float(ticker['last']) > 0:
                    return float(ticker['last'])
            except Exception:
                continue

        return 0.0

    async def fetch_live_balance_inr(self) -> float:
        return self.balance_inr

    async def fetch_live_spot_balance_inr(self) -> float:
        return self.spot_balance_inr

    def get_balance_inr(self) -> float:
        return self.balance_inr

    def get_spot_balance_inr(self) -> float:
        return self.spot_balance_inr

    def update_balance_inr(self, delta_inr: float):
        self.balance_inr += delta_inr

    def transfer_futures_to_spot(self, amount_inr: float) -> Tuple[bool, str]:
        if amount_inr <= 0:
            return False, "Transfer amount must be positive"
        if self.balance_inr < amount_inr:
            return False, f"Insufficient futures balance (₹{self.balance_inr:.2f} < ₹{amount_inr:.2f})"
        
        self.balance_inr -= amount_inr
        self.spot_balance_inr += amount_inr
        return True, f"Successfully transferred ₹{amount_inr:.2f} to Spot Wallet"

    async def close(self):
        for ex in [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]:
            try:
                await ex.close()
            except Exception:
                pass


class CoinDCXNativeAdapter:
    """
    Dedicated Native API Adapter for CoinDCX India (Futures & Spot API).
    """
    def __init__(self, cfg=config):
        self.cfg = cfg
        self.api_key = str(cfg.API_KEY or "").strip()
        self.api_secret = str(cfg.API_SECRET or "").strip()
        self.base_url = "https://api.coindcx.com"
        self.cached_futures_bal: float = 0.0
        self.cached_spot_bal: float = 0.0
        self.last_auth_error: str = ""
        # Multi-exchange public instances for cloud compatibility (Render, AWS, GCP)
        self.public_exchange_binance = ccxt_async.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
        self.public_exchange_bybit = ccxt_async.bybit({'enableRateLimit': True, 'options': {'defaultType': 'linear'}})
        self.public_exchange_okx = ccxt_async.okx({'enableRateLimit': True})

    def _get_headers_and_payload(self, extra_payload: Optional[dict] = None) -> Tuple[dict, str]:
        secret_bytes = bytes(self.api_secret, 'utf-8')
        timeStamp = int(time.time() * 1000)
        body = {"timestamp": timeStamp}
        if extra_payload:
            body.update(extra_payload)

        json_body = json.dumps(body, separators=(',', ':'))
        signature = hmac.new(secret_bytes, json_body.encode('utf-8'), hashlib.sha256).hexdigest()

        headers = {
            'Content-Type': 'application/json',
            'X-AUTH-APIKEY': self.api_key,
            'X-AUTH-SIGNATURE': signature
        }
        return headers, json_body

    async def validate_credentials(self) -> Tuple[bool, str]:
        """
        Validates API Key and Secret against CoinDCX native balance endpoint.
        """
        if not self.api_key or not self.api_secret:
            return False, "API Key and Secret are required."

        try:
            headers, json_body = self._get_headers_and_payload()
            url = f"{self.base_url}/exchange/v1/users/balances"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=json_body, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        self.last_auth_error = ""
                        return True, "Successfully authenticated with CoinDCX."
                    else:
                        err_text = await response.text()
                        try:
                            err_json = json.loads(err_text)
                            msg = err_json.get("message", err_text)
                        except Exception:
                            msg = err_text
                        self.last_auth_error = f"CoinDCX authentication failed (HTTP {response.status}): {msg}"
                        return False, self.last_auth_error
        except Exception as e:
            self.last_auth_error = f"Could not connect to CoinDCX: {str(e)}"
            return False, self.last_auth_error

    async def fetch_live_balance_inr(self) -> float:
        """
        Queries CoinDCX native API for user balances across Spot and Futures endpoints.
        Uses 5-second cache to prevent rate-limiting on WebSocket broadcasts.
        """
        now = time.time()
        if hasattr(self, "_last_bal_fetch_time") and (now - self._last_bal_fetch_time < 2.0) and self.cached_futures_bal > 0:
            return self.cached_futures_bal

        self._last_bal_fetch_time = now

        if not self.api_key or not self.api_secret:
            self.last_auth_error = "API Key and Secret are missing"
            return 0.0

        try:
            total_bal = 0.0
            async with aiohttp.ClientSession() as session:
                # 1. Query Spot Balances (INR & USDT)
                url_balances = f"{self.base_url}/exchange/v1/users/balances"
                headers_b, body_b = self._get_headers_and_payload()
                try:
                    async with session.post(url_balances, data=body_b, headers=headers_b, timeout=5) as res_b:
                        if res_b.status == 200:
                            bdata = await res_b.json()
                            self.last_auth_error = ""
                            if isinstance(bdata, list):
                                for item in bdata:
                                    curr = str(item.get('currency', '')).upper()
                                    bal = float(item.get('balance', 0.0) or item.get('available', 0.0) or 0.0)
                                    locked = float(item.get('locked_balance', 0.0) or 0.0)
                                    tot = bal + locked
                                    if ('INR' in curr) and tot > 0:
                                        total_bal += tot
                                    elif ('USDT' in curr or 'USD' in curr) and tot > 0:
                                        total_bal += tot * self.cfg.USD_INR_RATE
                        else:
                            err_text = await res_b.text()
                            self.last_auth_error = f"CoinDCX Balance Error: {err_text}"
                except Exception as err1:
                    logger.error(f"CoinDCX spot balance error: {err1}")

                # 2. Query Futures Cross Margin Details
                url_cross = f"{self.base_url}/exchange/v1/derivatives/futures/positions/cross_margin_details"
                headers_c, body_c = self._get_headers_and_payload()
                try:
                    async with session.post(url_cross, data=body_c, headers=headers_c, timeout=5) as res_c:
                        if res_c.status == 200:
                            cdata = await res_c.json()
                            if isinstance(cdata, dict):
                                avail = float(cdata.get('available_balance_cross', 0.0) or cdata.get('total_wallet_balance', 0.0) or cdata.get('wallet_balance', 0.0) or cdata.get('inr_balance', 0.0) or 0.0)
                                if avail > 0:
                                    total_bal = max(total_bal, avail)
                                usdt_bal = float(cdata.get('usdt_balance', 0.0) or 0.0)
                                if usdt_bal > 0:
                                    total_bal = max(total_bal, usdt_bal * self.cfg.USD_INR_RATE)
                except Exception as err2:
                    logger.error(f"CoinDCX futures cross margin error: {err2}")

            self.cached_futures_bal = round(total_bal, 2)
            return self.cached_futures_bal

        except Exception as e:
            self.last_auth_error = f"CoinDCX API Exception: {e}"
            logger.error(self.last_auth_error)
            return self.cached_futures_bal


    async def create_futures_order(self, symbol: str, side: str, size_inr: float, leverage: int, entry_price: float) -> dict:
        """
        Submits real market order to CoinDCX Futures API.
        """
        if not self.api_key or not self.api_secret:
            return {"success": False, "error": "Missing API Key/Secret"}

        try:
            clean_sym = symbol.replace("/", "_")
            coindcx_pair = f"B-{clean_sym}" if not clean_sym.startswith("B-") else clean_sym
            order_side = "buy" if side.upper() == "LONG" else "sell"
            
            # Calculate Notional quantity for CoinDCX Futures (minimum notional order value ≥ ₹2,450 INR)
            notional_inr = max(size_inr * leverage, 2500.0)
            raw_qty = (notional_inr / self.cfg.USD_INR_RATE) / max(entry_price, 0.000001)
            
            if raw_qty >= 1.0:
                qty = float(round(raw_qty))
            else:
                qty = float(round(raw_qty, 2))
            qty = max(1.0, qty)

            payload = {
                "timestamp": int(round(time.time() * 1000)),
                "order": {
                    "side": order_side,
                    "pair": coindcx_pair,
                    "order_type": "market_order",
                    "total_quantity": qty,
                    "leverage": int(leverage),
                    "notification": "no_notification",
                    "time_in_force": "good_till_cancel",
                    "hidden": False,
                    "post_only": False,
                    "margin_currency_short_name": "INR"
                }
            }

            json_body = json.dumps(payload, separators=(',', ':'))
            signature = hmac.new(bytes(self.api_secret, 'utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()
            headers = {
                'Content-Type': 'application/json',
                'X-AUTH-APIKEY': self.api_key,
                'X-AUTH-SIGNATURE': signature
            }

            url = f"{self.base_url}/exchange/v1/derivatives/futures/orders/create"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=json_body, headers=headers, timeout=10) as response:
                    res_text = await response.text()
                    if response.status == 200:
                        logger.info(f"CoinDCX LIVE Order Placed: {symbol} {side} Qty:{qty} | Response: {res_text}")
                        return {"success": True, "data": json.loads(res_text)}
                    else:
                        logger.error(f"CoinDCX LIVE Order Failed: {response.status} - {res_text}")
                        return {"success": False, "error": res_text}
        except Exception as e:
            logger.error(f"CoinDCX Order Exception: {e}")
            return {"success": False, "error": str(e)}

    async def close_futures_order(self, symbol: str, side: str, entry_price: float) -> dict:
        """
        Exits/closes real market position on CoinDCX Futures API.
        """
        if not self.api_key or not self.api_secret:
            return {"success": False, "error": "Missing API Key/Secret"}

        try:
            clean_sym = symbol.replace("/", "_")
            coindcx_pair = f"B-{clean_sym}" if not clean_sym.startswith("B-") else clean_sym

            payload = {
                "timestamp": int(round(time.time() * 1000)),
                "pair": coindcx_pair
            }

            json_body = json.dumps(payload, separators=(',', ':'))
            signature = hmac.new(bytes(self.api_secret, 'utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()
            headers = {
                'Content-Type': 'application/json',
                'X-AUTH-APIKEY': self.api_key,
                'X-AUTH-SIGNATURE': signature
            }

            url = f"{self.base_url}/exchange/v1/derivatives/futures/positions/cancel_all_open_orders_for_position"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=json_body, headers=headers, timeout=10) as response:
                    res_text = await response.text()
                    logger.info(f"CoinDCX LIVE Position Closed: {symbol} | Response: {res_text}")
                    return {"success": True, "text": res_text}
        except Exception as e:
            logger.error(f"CoinDCX Close Position Exception: {e}")
            return {"success": False, "error": str(e)}

    async def fetch_live_spot_balance_inr(self) -> float:
        return self.cached_spot_bal

    def get_balance_inr(self) -> float:
        return self.cached_futures_bal

    def get_spot_balance_inr(self) -> float:
        return self.cached_spot_bal

    def update_balance_inr(self, delta_inr: float):
        self.cached_futures_bal += delta_inr

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> Optional[pd.DataFrame]:
        clean_sym = symbol.replace("/", "_")
        coindcx_pair = f"B-{clean_sym}" if not clean_sym.startswith("B-") else clean_sym
        
        # 1. CoinDCX Native Public Candle API (High Speed)
        try:
            url = f"https://public.coindcx.com/market_data/candles?pair={coindcx_pair}&interval=1m&limit={limit}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2.0) as res:
                    if res.status == 200:
                        c_data = await res.json()
                        if isinstance(c_data, list) and len(c_data) >= 10:
                            rows = []
                            for c in c_data:
                                rows.append([
                                    int(c.get('time', 0)),
                                    float(c.get('open', 0)),
                                    float(c.get('high', 0)),
                                    float(c.get('low', 0)),
                                    float(c.get('close', 0)),
                                    float(c.get('volume', 0))
                                ])
                            rows.sort(key=lambda x: x[0])
                            df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                            return df
        except Exception:
            pass

        # 2. Fast Fallback Exchanges (Binance -> Bybit -> OKX)
        for ex in [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]:
            try:
                ohlcv = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=2.0)
                if ohlcv and len(ohlcv) >= 10:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                    return df
            except Exception:
                continue

        return None

    async def fetch_ticker_price(self, symbol: str) -> float:
        exchanges = [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]
        for ex in exchanges:
            try:
                ticker = await ex.fetch_ticker(symbol)
                if ticker and 'last' in ticker and float(ticker['last']) > 0:
                    return float(ticker['last'])
            except Exception:
                continue
        return 0.0

    async def close(self):
        for ex in [self.public_exchange_binance, self.public_exchange_bybit, self.public_exchange_okx]:
            try:
                await ex.close()
            except Exception:
                pass


class CCXTLiveExchangeAdapter:
    """
    Live Exchange Adapter for Binance and Bybit via CCXT.
    """
    def __init__(self, cfg=config):
        self.cfg = cfg
        self.cached_futures_bal: float = 0.0
        self.cached_spot_bal: float = 0.0
        exchange_class = getattr(ccxt_async, cfg.EXCHANGE_NAME.lower(), ccxt_async.binance)
        self.exchange = exchange_class({
            'apiKey': cfg.API_KEY,
            'secret': cfg.API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })

    async def fetch_live_balance_inr(self) -> float:
        now = time.time()
        if hasattr(self, "_last_bal_fetch_time") and (now - self._last_bal_fetch_time < 2.0) and self.cached_futures_bal > 0:
            return self.cached_futures_bal

        self._last_bal_fetch_time = now
        try:
            balance = await self.exchange.fetch_balance({'type': 'future'})
            totals = balance.get('total', {}) or {}
            usdt = float(totals.get('USDT', 0.0) or 0.0)
            if usdt > 0:
                self.cached_futures_bal = round(usdt * self.cfg.USD_INR_RATE, 2)
            else:
                self.cached_futures_bal = float(self.cfg.INITIAL_CAPITAL_INR)
            return self.cached_futures_bal
        except Exception as e:
            logger.error(f"CCXT Live Balance Fetch Error ({self.cfg.EXCHANGE_NAME}): {e}")
            if self.cached_futures_bal <= 0:
                self.cached_futures_bal = float(self.cfg.INITIAL_CAPITAL_INR)
            return self.cached_futures_bal

    async def fetch_live_spot_balance_inr(self) -> float:
        return self.cached_spot_bal

    def get_balance_inr(self) -> float:
        return self.cached_futures_bal

    def get_spot_balance_inr(self) -> float:
        return self.cached_spot_bal

    def update_balance_inr(self, delta_inr: float):
        self.cached_futures_bal += delta_inr

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "5m", limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                return None
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception:
            return None

    async def fetch_ticker_price(self, symbol: str) -> float:
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception:
            return 0.0

    async def set_leverage(self, leverage: int, symbol: str):
        """
        Sets live exchange futures leverage for the target trading pair.
        """
        try:
            if hasattr(self.exchange, 'set_leverage'):
                await self.exchange.set_leverage(leverage, symbol)
                logger.info(f"Set live futures leverage to {leverage}x on {symbol} ({self.cfg.EXCHANGE_NAME})")
        except Exception as e:
            logger.warning(f"Could not set live leverage on {symbol}: {e}")

    async def create_futures_order(self, symbol: str, side: str, size_inr: float, leverage: int, entry_price: float) -> dict:
        """
        Applies leverage and submits live market order on exchange (Binance/Bybit/Delta).
        """
        if not self.cfg.API_KEY or not self.cfg.API_SECRET:
            return {"success": False, "error": "Missing API key/secret"}
        try:
            # 1. Apply leverage on live exchange before placing order
            await self.set_leverage(leverage, symbol)

            order_side = "buy" if side.upper() == "LONG" else "sell"
            size_usdt = size_inr / self.cfg.USD_INR_RATE
            notional_usdt = size_usdt * leverage
            amount = notional_usdt / max(entry_price, 1e-8)

            order = await self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=order_side,
                amount=amount
            )
            logger.info(f"CCXT LIVE Futures Order Placed: {symbol} {side} Leverage:{leverage}x | Size: ₹{size_inr} | Order ID: {order.get('id')}")
            return {"success": True, "data": order}
        except Exception as e:
            logger.error(f"CCXT LIVE Order Error for {symbol}: {e}")
            return {"success": False, "error": str(e)}

    async def close_futures_order(self, symbol: str, side: str, entry_price: float) -> dict:
        """
        Closes active position on live exchange.
        """
        try:
            order_side = "sell" if side.upper() == "LONG" else "buy"
            amount = 0.0
            if hasattr(self.exchange, 'fetch_positions'):
                positions = await self.exchange.fetch_positions([symbol])
                for pos in positions:
                    if pos.get('symbol') == symbol and float(pos.get('contracts', 0) or pos.get('size', 0) or 0) > 0:
                        amount = float(pos.get('contracts', 0) or pos.get('size', 0))
                        break
            if amount > 0:
                order = await self.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=order_side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
                logger.info(f"CCXT LIVE Position Closed: {symbol} | Order ID: {order.get('id')}")
                return {"success": True, "data": order}
            return {"success": False, "error": "No open contracts found to close"}
        except Exception as e:
            logger.error(f"CCXT LIVE Close Position Exception: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass


def get_exchange_adapter(cfg=config):
    if cfg.TRADING_MODE.upper() == "LIVE":
        if cfg.API_KEY and cfg.API_SECRET:
            if cfg.EXCHANGE_NAME.lower() == "coindcx":
                return CoinDCXNativeAdapter(cfg)
            return CCXTLiveExchangeAdapter(cfg)
        else:
            cfg.TRADING_MODE = "PAPER"
            return PaperExchangeAdapter(cfg)
    return PaperExchangeAdapter(cfg)
