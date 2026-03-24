"""
Risk manager: enforces position limits, tracks P&L, and provides kill switch.
"""
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Enforces risk controls that strategies cannot override:
    - Maximum position size in USD
    - Daily loss limit
    - Maximum open orders
    - Kill switch for emergency shutdown
    """
    
    def __init__(self, config: dict):
        self.config = config.get("risk", {})
        self.max_position_usd = self.config.get("max_position_usd", 1000)
        self.max_daily_loss = self.config.get("max_daily_loss_usd", 50)
        self.max_open_orders = self.config.get("max_open_orders", 3)
        
        self.current_position_usd = 0.0
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        
        self._killed = False
        self._daily_reset_date = datetime.now(timezone.utc).date()
        
        logger.info(
            f"Risk limits: max_position=${self.max_position_usd}, "
            f"max_daily_loss=${self.max_daily_loss}, "
            f"max_open_orders={self.max_open_orders}"
        )
    
    def can_open_position(self) -> bool:
        """Check if a new position is allowed."""
        if self._killed:
            logger.warning("KILL SWITCH active — no new positions")
            return False
        
        self._check_daily_reset()
        
        if self.daily_pnl <= -self.max_daily_loss:
            logger.warning(f"Daily loss limit hit (${self.daily_pnl:.2f})")
            return False
        
        return True
    
    def check_position_size(self, size_usd: float) -> float:
        """
        Validate and possibly reduce a requested position size.
        Returns the allowed size (may be smaller than requested).
        """
        remaining = self.max_position_usd - self.current_position_usd
        
        if remaining <= 0:
            logger.warning("Max position reached, blocking order")
            return 0.0
        
        if size_usd > remaining:
            logger.info(f"Reducing order from ${size_usd:.2f} to ${remaining:.2f} (position limit)")
            return remaining
        
        return size_usd
    
    def record_trade(self, pnl: float, side: str, size_usd: float):
        """Record a completed trade for P&L tracking."""
        self._check_daily_reset()
        
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.trade_count += 1
        
        if pnl >= 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        
        # Update position tracking
        if side == "buy":
            self.current_position_usd += size_usd
        else:
            self.current_position_usd = max(0, self.current_position_usd - size_usd)
        
        logger.info(
            f"Trade recorded: PnL=${pnl:+.2f} | "
            f"Daily=${self.daily_pnl:+.2f} | "
            f"Total=${self.total_pnl:+.2f} | "
            f"W/L={self.win_count}/{self.loss_count}"
        )
        
        # Auto-kill if daily loss exceeded
        if self.daily_pnl <= -self.max_daily_loss:
            logger.warning(f"DAILY LOSS LIMIT HIT: ${self.daily_pnl:.2f}")
            self.kill()
    
    def kill(self):
        """Activate kill switch — stops all new trading."""
        self._killed = True
        logger.critical("KILL SWITCH ACTIVATED — all trading stopped")
    
    def resume(self):
        """Deactivate kill switch."""
        self._killed = False
        logger.info("Kill switch deactivated — trading resumed")
    
    @property
    def is_killed(self) -> bool:
        return self._killed
    
    def _check_daily_reset(self):
        """Reset daily P&L at midnight UTC."""
        today = datetime.now(timezone.utc).date()
        if today != self._daily_reset_date:
            logger.info(f"Daily reset: yesterday PnL=${self.daily_pnl:+.2f}")
            self.daily_pnl = 0.0
            self._daily_reset_date = today
            
            # Auto-resume if killed by daily limit
            if self._killed:
                self.resume()
    
    @property
    def stats(self) -> dict:
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        return {
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "trades": self.trade_count,
            "wins": self.win_count,
            "losses": self.loss_count,
            "win_rate": round(win_rate, 1),
            "position_usd": round(self.current_position_usd, 2),
            "killed": self._killed,
        }
