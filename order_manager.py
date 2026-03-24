"""
Order manager: handles order placement, tracking, cancellation, and lifecycle events.
"""
import logging
import time
from typing import Optional, Callable
from strategies.base_strategy import Signal

logger = logging.getLogger(__name__)


class Order:
    """Tracks an individual order through its lifecycle."""
    
    def __init__(self, exchange_id: str, signal: Signal, created_at: float = None):
        self.exchange_id = exchange_id
        self.signal = signal
        self.created_at = created_at or time.time()
        self.status = "pending"    # pending -> open -> filled | cancelled | failed
        self.fill_price = None
        self.fill_amount = None
        self.fill_time = None
    
    def __repr__(self):
        return f"Order({self.signal.side} {self.signal.size:.6f} @ {self.signal.price:.2f} [{self.status}])"


class OrderManager:
    """
    Manages the full order lifecycle:
    - Places orders on the exchange (or simulates in dry-run mode)
    - Tracks open orders and polls for fills
    - Handles timeouts and cancellations
    - Calls strategy callbacks on fill/cancel events
    """
    
    def __init__(self, config: dict, exchange=None):
        self.config = config
        self.risk_config = config.get("risk", {})
        self.mode = config.get("trading", {}).get("mode", "dry-run")
        self.exchange = exchange
        self.symbol = config.get("trading", {}).get("symbol", "BTC/USDT")
        
        self.open_orders: list[Order] = []
        self.filled_orders: list[Order] = []
        self.cancelled_orders: list[Order] = []
        
        self.on_fill: Optional[Callable] = None
        self.on_cancel: Optional[Callable] = None
        
        self.order_timeout = self.risk_config.get("order_timeout", 60)
        self.max_open = self.risk_config.get("max_open_orders", 3)
    
    def place_order(self, signal: Signal) -> Optional[Order]:
        """
        Place an order based on a strategy signal.
        Returns the Order object or None if rejected.
        """
        # Check open order limit
        if len(self.open_orders) >= self.max_open:
            logger.warning(f"Max open orders ({self.max_open}) reached, rejecting signal")
            return None
        
        order = Order(exchange_id="", signal=signal)
        
        if self.mode == "dry-run":
            return self._simulate_order(order)
        else:
            return self._live_order(order)
    
    def _simulate_order(self, order: Order) -> Order:
        """Simulate order execution for dry-run mode."""
        signal = order.signal
        
        if signal.order_type == "market":
            # Market orders fill immediately in simulation
            order.status = "filled"
            order.fill_price = signal.price
            order.fill_amount = signal.size
            order.fill_time = time.time()
            order.exchange_id = f"sim_{int(time.time() * 1000)}"
            
            self.filled_orders.append(order)
            logger.info(f"[DRY-RUN] FILLED: {signal.side.upper()} {signal.size:.6f} @ ${signal.price:,.2f}")
            
            if self.on_fill:
                self.on_fill({
                    "id": order.exchange_id,
                    "side": signal.side,
                    "price": order.fill_price,
                    "amount": order.fill_amount,
                    "timestamp": order.fill_time,
                })
        else:
            # Limit orders go to open orders
            order.status = "open"
            order.exchange_id = f"sim_{int(time.time() * 1000)}"
            self.open_orders.append(order)
            logger.info(f"[DRY-RUN] PLACED: {signal.side.upper()} {signal.size:.6f} @ ${signal.price:,.2f}")
        
        return order
    
    def _live_order(self, order: Order) -> Optional[Order]:
        """Place a real order on the exchange."""
        if not self.exchange:
            logger.error("No exchange connection for live trading")
            return None
        
        signal = order.signal
        
        try:
            if signal.order_type == "market":
                result = self.exchange.create_market_order(
                    self.symbol, signal.side, signal.size
                )
            else:
                result = self.exchange.create_limit_order(
                    self.symbol, signal.side, signal.size, signal.price
                )
            
            order.exchange_id = result.get("id", "")
            order.status = "open"
            self.open_orders.append(order)
            
            logger.info(f"PLACED: {signal.side.upper()} {signal.size:.6f} @ ${signal.price:,.2f} (id={order.exchange_id})")
            return order
            
        except Exception as e:
            order.status = "failed"
            logger.error(f"Order placement failed: {e}")
            return None
    
    def check_orders(self, current_price: float = None):
        """
        Poll open orders for fills, handle timeouts.
        Call this on every tick.
        """
        now = time.time()
        still_open = []
        
        for order in self.open_orders:
            # Check timeout
            if now - order.created_at > self.order_timeout:
                self._cancel_order(order, reason="timeout")
                continue
            
            if self.mode == "dry-run":
                # Simulate limit order fills
                if current_price and self._would_fill(order, current_price):
                    order.status = "filled"
                    order.fill_price = order.signal.price
                    order.fill_amount = order.signal.size
                    order.fill_time = now
                    self.filled_orders.append(order)
                    
                    logger.info(f"[DRY-RUN] FILLED: {order.signal.side.upper()} @ ${order.fill_price:,.2f}")
                    
                    if self.on_fill:
                        self.on_fill({
                            "id": order.exchange_id,
                            "side": order.signal.side,
                            "price": order.fill_price,
                            "amount": order.fill_amount,
                            "timestamp": order.fill_time,
                        })
                    continue
            else:
                # Check real order status
                try:
                    result = self.exchange.fetch_order(order.exchange_id, self.symbol)
                    if result["status"] == "closed":
                        order.status = "filled"
                        order.fill_price = result.get("average", result.get("price", 0))
                        order.fill_amount = result.get("filled", 0)
                        order.fill_time = now
                        self.filled_orders.append(order)
                        
                        logger.info(f"FILLED: {order.signal.side.upper()} @ ${order.fill_price:,.2f}")
                        
                        if self.on_fill:
                            self.on_fill({
                                "id": order.exchange_id,
                                "side": order.signal.side,
                                "price": order.fill_price,
                                "amount": order.fill_amount,
                                "timestamp": order.fill_time,
                            })
                        continue
                except Exception as e:
                    logger.warning(f"Order status check failed: {e}")
            
            still_open.append(order)
        
        self.open_orders = still_open
    
    def _would_fill(self, order: Order, price: float) -> bool:
        """Check if a limit order would fill at the current price (simulation)."""
        if order.signal.side == "buy":
            return price <= order.signal.price
        else:
            return price >= order.signal.price
    
    def _cancel_order(self, order: Order, reason: str = "manual"):
        """Cancel an order."""
        if self.mode != "dry-run" and self.exchange:
            try:
                self.exchange.cancel_order(order.exchange_id, self.symbol)
            except Exception as e:
                logger.warning(f"Cancel failed: {e}")
        
        order.status = "cancelled"
        self.cancelled_orders.append(order)
        logger.info(f"CANCELLED ({reason}): {order}")
        
        if self.on_cancel:
            self.on_cancel({
                "id": order.exchange_id,
                "side": order.signal.side,
                "price": order.signal.price,
                "reason": reason,
            })
    
    def cancel_all(self):
        """Cancel all open orders."""
        for order in list(self.open_orders):
            self._cancel_order(order, reason="cancel_all")
        self.open_orders.clear()
    
    @property
    def stats(self) -> dict:
        """Return order statistics."""
        return {
            "open": len(self.open_orders),
            "filled": len(self.filled_orders),
            "cancelled": len(self.cancelled_orders),
        }
