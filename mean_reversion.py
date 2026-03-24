"""
Mean reversion strategy.
Buys when price drops significantly below moving average,
sells when it reverts to the mean.
"""
from typing import Optional
from strategies.base_strategy import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    
    def setup(self):
        self.window = self.config.get("lookback", 30)
        self.entry_dev = self.config.get("threshold", 0.015)   # 1.5% below MA to buy
        self.exit_dev = self.config.get("exit_threshold", 0.003)  # 0.3% from MA to exit
        self.in_position = False
        self.entry_price = None
    
    def generate_signal(self, market_data: dict) -> Optional[Signal]:
        candles = market_data.get("candles", [])
        ticker = market_data.get("ticker", {})
        
        if len(candles) < self.window:
            return None
        
        price = ticker.get("last", 0)
        if price <= 0:
            return None
        
        # Simple moving average
        closes = [c["close"] for c in candles[-self.window:]]
        sma = sum(closes) / len(closes)
        deviation = (price - sma) / sma
        
        # Volatility filter: only trade when vol is reasonable
        std = (sum((c - sma) ** 2 for c in closes) / len(closes)) ** 0.5
        vol = std / sma if sma > 0 else 0
        
        if self.in_position:
            # Exit when price reverts toward mean
            if abs(deviation) < self.exit_dev:
                self.in_position = False
                pnl = price - self.entry_price if self.entry_price else 0
                self.log(f"Exit: price=${price:.2f} sma=${sma:.2f} dev={deviation:.4f} pnl=${pnl:.2f}")
                self.entry_price = None
                self.record_signal()
                return Signal(side="sell", price=price, size=self.position_size(price), order_type="market")
        else:
            if not self.can_trade():
                return None
            
            # Entry: price significantly below MA + not too volatile
            if deviation < -self.entry_dev and vol < 0.05:
                self.in_position = True
                self.entry_price = price
                self.log(f"Entry: price=${price:.2f} sma=${sma:.2f} dev={deviation:.4f} vol={vol:.4f}")
                self.record_signal()
                return Signal(
                    side="buy", price=price, size=self.position_size(price),
                    order_type="market",
                    metadata={"deviation": deviation, "volatility": vol, "sma": sma}
                )
        
        return None
    
    def on_fill(self, order: dict):
        self.log(f"Filled: {order['side']} @ ${order['price']:,.2f}")
