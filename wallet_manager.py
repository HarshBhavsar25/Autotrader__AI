import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Any, Tuple, Optional
from config import config
from database import db_manager

logger = logging.getLogger("AutoTrader.Wallet")

class WalletManager:
    def __init__(self, exchange_adapter, cfg=config):
        self.adapter = exchange_adapter
        self.cfg = cfg
        self.base_capital_inr = cfg.INITIAL_CAPITAL_INR
        self.daily_pnl_accumulator_inr = 0.0
        self.total_transferred_inr = 0.0

    async def async_get_wallet_summary(self) -> Dict[str, Any]:
        """
        Fetches actual real-time Futures & Spot balance directly from exchange API if in LIVE mode.
        """
        if hasattr(self.adapter, "fetch_live_balance_inr"):
            futures_bal = await self.adapter.fetch_live_balance_inr()
            spot_bal = await self.adapter.fetch_live_spot_balance_inr()
        else:
            futures_bal = self.adapter.get_balance_inr()
            spot_bal = self.adapter.get_spot_balance_inr()

        is_live = self.cfg.TRADING_MODE.upper() == "LIVE"
        auth_error = getattr(self.adapter, "last_auth_error", "")
        insufficient_balance = bool(auth_error)

        if is_live and auth_error:
            warning_msg = f"⚠️ Connection Failed: {auth_error}. Please check your API Key and Secret on {self.cfg.EXCHANGE_NAME.upper()}!"
        else:
            warning_msg = ""

        current_profit_above_base = max(0.0, futures_bal - self.base_capital_inr)
        daily_target = self.cfg.DAILY_NET_PROFIT_TARGET_INR
        progress_pct = min(100.0, (self.daily_pnl_accumulator_inr / daily_target) * 100.0) if daily_target > 0 else 0.0

        return {
            "trading_mode": self.cfg.TRADING_MODE,
            "futures_balance_inr": round(futures_bal, 2),
            "spot_balance_inr": round(spot_bal, 2),
            "total_account_inr": round(futures_bal + spot_bal, 2),
            "base_capital_inr": round(self.base_capital_inr, 2),
            "current_profit_above_base_inr": round(current_profit_above_base, 2),
            "daily_net_pnl_inr": round(self.daily_pnl_accumulator_inr, 2),
            "daily_target_inr": round(daily_target, 2),
            "daily_target_progress_pct": round(progress_pct, 1),
            "total_transferred_inr": round(self.total_transferred_inr, 2),
            "usd_inr_rate": self.cfg.USD_INR_RATE,
            "insufficient_balance": insufficient_balance,
            "balance_warning_msg": warning_msg
        }


    def get_wallet_summary(self) -> Dict[str, Any]:
        """
        Returns cached breakdown of Futures balance, Spot balance, base capital, net profit today.
        """
        futures_bal = self.adapter.get_balance_inr()
        spot_bal = self.adapter.get_spot_balance_inr()

        is_live = self.cfg.TRADING_MODE.upper() == "LIVE"
        insufficient_balance = (futures_bal < self.cfg.MIN_TRADE_SIZE_INR)

        current_profit_above_base = max(0.0, futures_bal - self.base_capital_inr)
        daily_target = self.cfg.DAILY_NET_PROFIT_TARGET_INR
        progress_pct = min(100.0, (self.daily_pnl_accumulator_inr / daily_target) * 100.0) if daily_target > 0 else 0.0

        return {
            "trading_mode": self.cfg.TRADING_MODE,
            "futures_balance_inr": round(futures_bal, 2),
            "spot_balance_inr": round(spot_bal, 2),
            "total_account_inr": round(futures_bal + spot_bal, 2),
            "base_capital_inr": round(self.base_capital_inr, 2),
            "current_profit_above_base_inr": round(current_profit_above_base, 2),
            "daily_net_pnl_inr": round(self.daily_pnl_accumulator_inr, 2),
            "daily_target_inr": round(daily_target, 2),
            "daily_target_progress_pct": round(progress_pct, 1),
            "total_transferred_inr": round(self.total_transferred_inr, 2),
            "usd_inr_rate": self.cfg.USD_INR_RATE,
            "insufficient_balance": insufficient_balance,
            "balance_warning_msg": f"⚠️ Insufficient Futures Balance (₹{futures_bal:.2f} < ₹100). Please deposit funds or switch to Paper Mode!" if (is_live and insufficient_balance) else ""
        }

    def record_completed_trade(self, net_pnl_inr: float):
        """
        Updates account balance and daily PnL accumulator upon trade completion.
        """
        self.daily_pnl_accumulator_inr += net_pnl_inr
        if hasattr(self.adapter, "update_balance_inr"):
            self.adapter.update_balance_inr(net_pnl_inr)
        db_manager.log_event("INFO", "WALLET", f"Recorded trade PnL: ₹{net_pnl_inr:.2f} | New Daily Total: ₹{self.daily_pnl_accumulator_inr:.2f}")

    def reset_paper_balance(self, amount_inr: float = 1000.0) -> Tuple[bool, str]:
        """
        Resets simulated Paper Trading balance back to initial ₹1000 capital.
        """
        if hasattr(self.adapter, "balance_inr"):
            self.adapter.balance_inr = amount_inr
            self.adapter.spot_balance_inr = 0.0
            self.daily_pnl_accumulator_inr = 0.0
            msg = f"Reset Paper Trading balance to ₹{amount_inr:.2f}."
            db_manager.log_event("INFO", "WALLET_RESET", msg)
            return True, msg
        return False, "Cannot reset balance in Live Trading Mode."

    def execute_daily_profit_transfer(self) -> Tuple[bool, str, float]:
        """
        Executes the 07:00 AM daily profit transfer from Futures Wallet to Spot Wallet.
        Transfers realized profits exceeding base capital (₹1000).
        """
        futures_bal = self.adapter.get_balance_inr() if hasattr(self.adapter, "get_balance_inr") else self.base_capital_inr
        transferable_profit = futures_bal - self.base_capital_inr

        if transferable_profit <= 10.0: # Minimum ₹10 to transfer
            msg = f"No profits to transfer at 07:00 AM. Current Futures Balance: ₹{futures_bal:.2f} (Base: ₹{self.base_capital_inr:.2f})"
            logger.info(msg)
            db_manager.log_event("INFO", "TRANSFER", msg)
            return False, msg, 0.0

        amount_inr = round(transferable_profit, 2)
        amount_usdt = round(amount_inr / self.cfg.USD_INR_RATE, 4)

        if hasattr(self.adapter, "transfer_futures_to_spot"):
            success, message = self.adapter.transfer_futures_to_spot(amount_inr)
        else:
            success, message = True, f"Simulated transfer of ₹{amount_inr:.2f} (USDT {amount_usdt}) to Spot Wallet"

        if success:
            self.total_transferred_inr += amount_inr
            db_manager.record_transfer(
                amount_inr=amount_inr,
                amount_usdt=amount_usdt,
                status="SUCCESS",
                tx_id=f"TX-{int(datetime.now().timestamp())}",
                details=message
            )
            db_manager.log_event("INFO", "TRANSFER_SUCCESS", f"Transferred ₹{amount_inr:.2f} from Futures to Spot Wallet.")
            logger.info(f"07:00 AM Profit Transfer Success: Transferred ₹{amount_inr:.2f} to Spot Wallet.")
            return True, message, amount_inr
        else:
            db_manager.record_transfer(
                amount_inr=amount_inr,
                amount_usdt=amount_usdt,
                status="FAILED",
                details=message
            )
            db_manager.log_event("ERROR", "TRANSFER_FAILED", f"Failed to transfer profit: {message}")
            return False, message, 0.0

    def generate_withdrawal_instruction(self, amount_inr: float) -> Dict[str, Any]:
        """
        Generates automated external bank withdrawal instruction format requiring final user confirmation.
        """
        amount_usdt = round(amount_inr / self.cfg.USD_INR_RATE, 2)
        return {
            "title": "Manual / Automated Bank Withdrawal Instruction",
            "amount_inr": amount_inr,
            "amount_usdt": amount_usdt,
            "status": "REQUIRES_USER_CONFIRMATION",
            "instruction": (
                f"To withdraw ₹{amount_inr:.2f} (${amount_usdt} USDT) from your Spot Wallet to your linked bank account:\n"
                f"1. Open Exchange Spot Wallet -> P2P / INR Express Cashout.\n"
                f"2. Select Amount: ${amount_usdt} USDT (approx ₹{amount_inr:.2f}).\n"
                f"3. Confirm payout account and authorize withdrawal."
            ),
            "created_at": datetime.now().isoformat()
        }

    async def start_0700_scheduler(self):
        """
        24/7 Background loop checking for 07:00 AM local time daily profit transfer schedule.
        """
        logger.info("07:00 AM Daily Profit Transfer Scheduler Started.")
        last_transferred_day = -1

        while True:
            now = datetime.now()
            if now.hour == self.cfg.PROFIT_TRANSFER_SCHEDULE_HOUR and now.minute == self.cfg.PROFIT_TRANSFER_SCHEDULE_MINUTE:
                if now.day != last_transferred_day:
                    logger.info("Triggering 07:00 AM Daily Profit Transfer...")
                    self.execute_daily_profit_transfer()
                    last_transferred_day = now.day
            await asyncio.sleep(20) # Check every 20 seconds
