"""
Momentum / velocity-based trading strategy.
Enters when short-term price velocity exceeds a threshold,
exits on mean reversion or timeout.
"""
from typing import Optional
from strategies.base_strategy import BaseStrategy, Signal
import time


class MomentumStrategy(BaseStrategy):
    
    def setup(self):
        self.lookback = self.config.get("lookback", 10)
        self.entry_threshold = self.config.get("threshold", 0.003)  # 0.3% move
        self.exit_threshold = self.config.get("exit_threshold", 0.001)
        self.max_hold_seconds = self.config.get("max_hold_seconds", 300)
        
        self.entry_price = None
        self.entry_side = None
        self.entry_time = None
        self.in_position = False
    
    def generate_signal(self, market_data: dict) -> Optional[Signal]:
        candles = market_data.get("candles", [])
        ticker = market_data.get("ticker", {})
        
        if len(candles) < self.lookback:
            return None
        
        current_price = ticker.get("last", 0)
        if current_price <= 0:
            return None
        
        # If in position, check exit conditions
        if self.in_position:
            return self._check_exit(current_price)
        
        # Check entry conditions
        if not self.can_trade():
            return None
        
        return self._check_entry(candles, current_price)
    
    def _check_entry(self, candles: list, price: float) -> Optional[Signal]:
        """Look for momentum breakout."""
        recent = candles[-self.lookback:]
        
        # Calculate velocity: price change over lookback period
        start_price = recent[0]["close"]
        velocity = (price - start_price) / start_price
        
        # Volume confirmation: current volume vs average
        avg_volume = sum(c["volume"] for c in recent) / len(recent)
        current_volume = recent[-1]["volume"]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # Entry: strong move + above-average volume
        if abs(velocity) > self.entry_threshold and volume_ratio > 1.2:
            side = "buy" if velocity > 0 else "sell"
            size = self.position_size(price)
            
            if size <= 0:
                return None
            
            self.log(f"Entry signal: {side} | velocity={velocity:.4f} | vol_ratio={volume_ratio:.2f}")
            self.record_signal()
            
            return Signal(
                side=side,
                price=price,
                size=size,
                order_type="market",
                metadata={"velocity": velocity, "volume_ratio": volume_ratio}
            )
        
        return None
    
    def _check_exit(self, price: float) -> Optional[Signal]:
        """Check if we should exit the current position."""
        if not self.entry_price:
            return None
        
        pnl_pct = (price - self.entry_price) / self.entry_price
        if self.entry_side == "sell":
            pnl_pct = -pnl_pct
        
        elapsed = time.time() - (self.entry_time or 0)
        
        # Exit conditions: profit target, stop loss, or timeout
        should_exit = (
            pnl_pct >= self.exit_threshold or      # Take profit
            pnl_pct <= -self.entry_threshold or     # Stop loss
            elapsed >= self.max_hold_seconds         # Timeout
        )
        
        if should_exit:
            exit_side = "sell" if self.entry_side == "buy" else "buy"
            reason = "TP" if pnl_pct > 0 else "SL" if pnl_pct < -self.entry_threshold else "TIMEOUT"
            
            self.log(f"Exit signal: {exit_side} | pnl={pnl_pct:.4f} | reason={reason}")
            
            return Signal(
                side=exit_side,
                price=price,
                size=self.position_size(price),  # Close full position
                order_type="market",
                metadata={"reason": reason, "pnl_pct": pnl_pct}
            )
        
        return None
    
    def on_fill(self, order: dict):
        """Track position state on fills."""
        if not self.in_position:
            # Entry fill
            self.in_position = True
            self.entry_price = order.get("price", 0)
            self.entry_side = order.get("side", "buy")
            self.entry_time = time.time()
            self.log(f"Position opened: {self.entry_side} @ {self.entry_price}")
        else:
            # Exit fill
            exit_price = order.get("price", 0)
            pnl = (exit_price - self.entry_price) if self.entry_side == "buy" else (self.entry_price - exit_price)
            self.log(f"Position closed: PnL ${pnl:.2f}")
            
            self.in_position = False
            self.entry_price = None
            self.entry_side = None
            self.entry_time = None
