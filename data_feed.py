"""
Exchange data feed handler.
Manages connectivity, data polling, and market data aggregation.
"""
import ccxt
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DataFeed:
    """Connects to an exchange and provides normalized market data."""
    
    def __init__(self, config: dict):
        self.exchange_config = config.get("exchange", {})
        self.trading_config = config.get("trading", {})
        self.symbol = self.trading_config.get("symbol", "BTC/USDT")
        self.exchange: Optional[ccxt.Exchange] = None
        self._candle_cache = []
        self._max_candles = 200
    
    def connect(self):
        """Initialize exchange connection."""
        exchange_id = self.exchange_config.get("id", "binance")
        
        exchange_class = getattr(ccxt, exchange_id, None)
        if not exchange_class:
            raise ValueError(f"Exchange '{exchange_id}' not supported by CCXT")
        
        params = {
            "apiKey": self.exchange_config.get("api_key", ""),
            "secret": self.exchange_config.get("secret", ""),
            "enableRateLimit": True,
        }
        
        # Filter out empty credentials for public-only access
        params = {k: v for k, v in params.items() if v}
        
        self.exchange = exchange_class(params)
        
        if self.exchange_config.get("sandbox", True):
            self.exchange.set_sandbox_mode(True)
            logger.info(f"Connected to {exchange_id} (SANDBOX)")
        else:
            logger.info(f"Connected to {exchange_id} (LIVE)")
        
        # Load markets
        self.exchange.load_markets()
        if self.symbol not in self.exchange.symbols:
            available = [s for s in self.exchange.symbols if "BTC" in s][:5]
            raise ValueError(f"Symbol {self.symbol} not found. Try: {available}")
        
        logger.info(f"Trading {self.symbol}")
    
    def fetch_market_data(self) -> dict:
        """
        Fetch current market snapshot.
        Returns normalized dict with ticker, orderbook, trades, candles.
        """
        if not self.exchange:
            raise RuntimeError("Not connected. Call connect() first.")
        
        data = {}
        
        # Ticker
        try:
            raw = self.exchange.fetch_ticker(self.symbol)
            data["ticker"] = {
                "bid": raw.get("bid", 0),
                "ask": raw.get("ask", 0),
                "last": raw.get("last", 0),
                "volume": raw.get("baseVolume", 0),
                "timestamp": raw.get("timestamp", int(time.time() * 1000)),
            }
        except Exception as e:
            logger.warning(f"Ticker fetch failed: {e}")
            data["ticker"] = {}
        
        # Orderbook (top 20 levels)
        try:
            raw = self.exchange.fetch_order_book(self.symbol, limit=20)
            data["orderbook"] = {
                "bids": raw.get("bids", []),
                "asks": raw.get("asks", []),
            }
        except Exception as e:
            logger.warning(f"Orderbook fetch failed: {e}")
            data["orderbook"] = {"bids": [], "asks": []}
        
        # Recent trades
        try:
            raw = self.exchange.fetch_trades(self.symbol, limit=50)
            data["recent_trades"] = [
                {
                    "price": t["price"],
                    "amount": t["amount"],
                    "side": t["side"],
                    "timestamp": t["timestamp"],
                }
                for t in raw
            ]
        except Exception as e:
            logger.warning(f"Trades fetch failed: {e}")
            data["recent_trades"] = []
        
        # Candles (1-minute)
        try:
            raw = self.exchange.fetch_ohlcv(self.symbol, timeframe="1m", limit=100)
            data["candles"] = [
                {
                    "timestamp": c[0],
                    "open": c[1],
                    "high": c[2],
                    "low": c[3],
                    "close": c[4],
                    "volume": c[5],
                }
                for c in raw
            ]
        except Exception as e:
            logger.warning(f"Candles fetch failed: {e}")
            data["candles"] = self._candle_cache
        
        return data
    
    def fetch_balance(self) -> dict:
        """Fetch account balances. Requires API credentials."""
        if not self.exchange:
            raise RuntimeError("Not connected.")
        
        try:
            raw = self.exchange.fetch_balance()
            # Return non-zero balances
            balances = {}
            for currency, amount in raw.get("total", {}).items():
                if amount and amount > 0:
                    balances[currency] = {
                        "total": amount,
                        "free": raw["free"].get(currency, 0),
                        "used": raw["used"].get(currency, 0),
                    }
            return balances
        except Exception as e:
            logger.error(f"Balance fetch failed: {e}")
            return {}
    
    def disconnect(self):
        """Clean up exchange connection."""
        if self.exchange:
            logger.info("Disconnected from exchange")
            self.exchange = None
