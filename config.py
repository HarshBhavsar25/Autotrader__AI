import os
from dataclasses import dataclass, field
from typing import List, Dict

# Load .env if present
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

@dataclass
class TradingConfig:
    # Capital and Trade Sizing (in INR)
    INITIAL_CAPITAL_INR: float = 1000.0
    MIN_TRADE_SIZE_INR: float = 100.0
    MAX_RISK_PER_TRADE_PCT: float = 0.15  # Up to 15% risk for high reward opportunity
    DYNAMIC_SIZING_ENABLED: bool = True
    ALLOW_COMPOUNDING: bool = True

    # Profit Targets (in INR)
    TARGET_NET_PROFIT_PER_TRADE_MIN_INR: float = 50.0
    TARGET_NET_PROFIT_PER_TRADE_MAX_INR: float = 100.0
    DAILY_NET_PROFIT_TARGET_INR: float = 500.0

    # Risk Engine & Stops (Ultra-Fast Scalping Mode: Seconds to 1 Min Exits)
    DEFAULT_LEVERAGE: int = 20
    MAX_LEVERAGE: int = 20
    BREAK_EVEN_TRIGGER_PROFIT_INR: float = 10.0  # Trigger breakeven lock once +₹10 net profit reached
    BREAK_EVEN_FEE_BUFFER_INR: float = 3.0      # Extra buffer above entry to guarantee fee coverage
    TRAILING_STOP_ATR_MULT: float = 1.0          # Tight trailing distance in ATR units for quick scalp lock
    HARD_STOP_LOSS_ATR_MULT: float = 1.2          # Tight stop loss distance
    HARD_TAKE_PROFIT_ATR_MULT: float = 1.8       # Fast 1.8x ATR target for 10s to 60s profit closures

    # Signal & Scanner Engine
    MIN_CONFIDENCE_SCORE: float = 35.0           # 35% confidence threshold for ultra-fast trade generation
    SCANNER_INTERVAL_SECONDS: float = 0.01        # 10ms continuous scan poll interval
    POSITION_MONITOR_INTERVAL_SECONDS: float = 0.01 # 10ms ultra high frequency monitoring loop

    # Daily Profit Transfer Settings
    PROFIT_TRANSFER_SCHEDULE_HOUR: int = 7       # 07:00 AM local time
    PROFIT_TRANSFER_SCHEDULE_MINUTE: int = 0
    AUTO_TRANSFER_FUTURES_TO_SPOT: bool = True

    # Fee and Currency Estimation
    MAKER_FEE_RATE: float = 0.0002              # 0.02%
    TAKER_FEE_RATE: float = 0.0005              # 0.05%
    ESTIMATED_SLIPPAGE_RATE: float = 0.0005     # 0.05%
    ESTIMATED_FUNDING_RATE_PER_8H: float = 0.0001 # 0.01%
    USD_INR_RATE: float = 85.0                  # Default exchange rate USD to INR

    # Mode & Exchange (Default PAPER mode; LIVE mode uses client browser localStorage credentials)
    TRADING_MODE: str = "PAPER"
    EXCHANGE_NAME: str = "coindcx"
    API_KEY: str = ""
    API_SECRET: str = ""

    # Bot Control Flags
    IS_BOT_RUNNING: bool = True
    MAX_CONCURRENT_POSITIONS: int = 4           # 4 concurrent position slots (allocating 100% of capital)
    MIN_ADX_TREND_STRENGTH: float = 10.0        # Low ADX filter to capture range breakouts fast
    CONSECUTIVE_LOSS_COOLDOWN_SEC: int = 300    # 5 min cooldown after 2 consecutive losses
    SWAP_LONG_SHORT_SIGNALS: bool = False       # Standard natural signal mapping: Bullish -> LONG, Bearish -> SHORT

    # Supported Pairs (Expanded 24/7 Futures Pairs across High-Vol & High-Return Altcoins)
    WATCHLIST_PAIRS: List[str] = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "PEPE/USDT", "WIF/USDT",
        "DOGE/USDT", "XRP/USDT", "BNB/USDT", "SUI/USDT", "NEAR/USDT",
        "AVAX/USDT", "LINK/USDT", "ADA/USDT", "SHIB/USDT", "FET/USDT",
        "RENDER/USDT", "INJ/USDT", "TIA/USDT", "FLOKI/USDT", "SEI/USDT",
        "RUNE/USDT", "DOT/USDT", "LTC/USDT", "APT/USDT", "FIL/USDT",
        "OP/USDT", "ARB/USDT", "MATIC/USDT", "ATOM/USDT", "FTM/USDT",
        "STX/USDT", "JUP/USDT", "BONK/USDT", "NOT/USDT", "ORDI/USDT"
    ])

    def update_credentials(self, exchange_name: str, api_key: str, api_secret: str, mode: str, usd_inr_rate: float = 85.0):
        self.EXCHANGE_NAME = exchange_name.lower()
        self.API_KEY = api_key.strip()
        self.API_SECRET = api_secret.strip()
        self.TRADING_MODE = mode.upper()
        self.USD_INR_RATE = usd_inr_rate

# Global instance
config = TradingConfig()
