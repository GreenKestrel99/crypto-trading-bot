"""
Abstract base class for trading strategies.
Subclass this and implement generate_signal() to create your own strategy.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import logging
import time


@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    side: str          # "buy" or "sell"
    price: float       # Target price
    size: float        # Order size in base currency
    order_type: str = "limit"  # "limit" or "market"
    metadata: dict = field(default_factory=dict)  # Strategy-specific info


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    
    Lifecycle:
        1. __init__() — receives config and sets up logger
        2. setup() — called once, initialize your indicators/state
        3. generate_signal() — called on every data update, return Signal or None
        4. on_fill() / on_cancel() — called on order events
    """
    
    def __init__(self, config: dict, risk_manager=None):
        self.config = config.get("strategy_params", {})
        self.trading_config = config.get("trading", {})
        self.risk_config = config.get("risk", {})
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self._last_signal_time = 0
        self.setup()
    
    def setup(self):
        """Override to initialize strategy state, indicators, etc."""
        pass
    
    @abstractmethod
    def generate_signal(self, market_data: dict) -> Optional[Signal]:
        """
        Core strategy logic. Called on every data update.
        
        Args:
            market_data: dict with keys:
                - ticker: {bid, ask, last, volume, timestamp}
                - orderbook: {bids: [[price, size], ...], asks: [[price, size], ...]}
                - recent_trades: [{price, amount, side, timestamp}, ...]
                - candles: [{open, high, low, close, volume, timestamp}, ...]
                
        Returns:
            Signal to place an order, or None to do nothing.
        """
        raise NotImplementedError
    
    def on_fill(self, order: dict):
        """Called when an order is filled. Override to update state."""
        pass
    
    def on_cancel(self, order: dict):
        """Called when an order is cancelled. Override to handle."""
        pass
    
    def position_size(self, price: float = None) -> float:
        """
        Calculate position size respecting risk limits.
        Override for custom sizing logic.
        """
        max_usd = self.risk_config.get("max_position_usd", 100)
        if price and price > 0:
            return max_usd / price
        return 0.0
    
    def log(self, msg: str, level: str = "info"):
        """Convenience logging method."""
        getattr(self.logger, level, self.logger.info)(msg)
    
    def can_trade(self) -> bool:
        """Check cooldown and risk limits before generating signals."""
        cooldown = self.risk_config.get("cooldown_seconds", 30)
        if time.time() - self._last_signal_time < cooldown:
            return False
        if self.risk_manager and not self.risk_manager.can_open_position():
            return False
        return True
    
    def record_signal(self):
        """Mark that a signal was generated (for cooldown tracking)."""
        self._last_signal_time = time.time()
