# Crypto Trading Bot Framework

A modular, production-ready Python framework for building automated cryptocurrency trading bots. Supports 100+ exchanges via CCXT.

## Features

- **Multi-exchange support** — Connect to Binance, Bybit, Coinbase, Kraken, and 100+ other exchanges
- **Real-time data** — WebSocket feeds for orderbook, trades, and ticker data
- **Pluggable strategies** — Simple interface to implement custom trading logic
- **Order management** — Limit/market orders with automatic retry, timeout, and error handling
- **Position tracking** — Real-time P&L, exposure monitoring, and risk limits
- **Configurable risk controls** — Max position size, daily loss limits, cooldown periods
- **Production logging** — Structured logs with trade journal CSV export
- **Dry-run mode** — Paper trade against live data before going live

## Architecture

```
┌─────────────────────────────────────────────┐
│                   main.py                   │
│              (Orchestrator)                 │
├──────────┬──────────┬───────────┬───────────┤
│  Data    │ Strategy │  Order    │   Risk    │
│  Feed    │  Engine  │  Manager  │  Manager  │
│          │          │           │           │
│ WebSocket│ Your     │ Place/    │ Position  │
│ REST API │ Logic    │ Cancel/   │ Limits    │
│ Candles  │ Here     │ Modify    │ P&L Track │
└──────────┴──────────┴───────────┴───────────┘
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot
pip install -r requirements.txt

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your exchange API keys

# Paper trade first
python main.py --mode dry-run

# Go live
python main.py --mode live
```

## Project Structure

```
├── main.py                 # Entry point and orchestrator
├── config.example.yaml     # Configuration template
├── requirements.txt        # Dependencies
├── core/
│   ├── data_feed.py        # Exchange connectivity & data streaming
│   ├── order_manager.py    # Order placement, tracking, and lifecycle
│   ├── risk_manager.py     # Position limits, P&L tracking, kill switches
│   └── utils.py            # Logging, helpers, time utilities
├── strategies/
│   ├── base_strategy.py    # Abstract strategy interface
│   ├── momentum.py         # Example: momentum/velocity strategy
│   └── mean_reversion.py   # Example: mean reversion strategy
└── logs/                   # Trade logs and journals
```

## Writing a Strategy

```python
from strategies.base_strategy import BaseStrategy, Signal

class MyStrategy(BaseStrategy):
    """
    Implement your trading logic by overriding generate_signal().
    Return a Signal with direction, size, and price.
    """
    
    def setup(self):
        """Called once at startup. Initialize indicators, state, etc."""
        self.lookback = self.config.get("lookback", 20)
        self.threshold = self.config.get("threshold", 0.02)
    
    def generate_signal(self, market_data: dict) -> Signal | None:
        """
        Called on every data update. Return a Signal to trade, or None to skip.
        
        market_data contains:
            - ticker: {bid, ask, last, volume}
            - orderbook: {bids, asks}
            - recent_trades: [{price, amount, side, timestamp}, ...]
            - candles: [{open, high, low, close, volume}, ...]
        """
        price = market_data["ticker"]["last"]
        candles = market_data["candles"]
        
        if len(candles) < self.lookback:
            return None
        
        # Your logic here
        avg = sum(c["close"] for c in candles[-self.lookback:]) / self.lookback
        deviation = (price - avg) / avg
        
        if deviation > self.threshold:
            return Signal(side="sell", price=price, size=self.position_size())
        elif deviation < -self.threshold:
            return Signal(side="buy", price=price, size=self.position_size())
        
        return None
    
    def on_fill(self, order: dict):
        """Called when an order fills. Update internal state."""
        self.log(f"Filled: {order['side']} {order['amount']} @ {order['price']}")
    
    def on_cancel(self, order: dict):
        """Called when an order is cancelled."""
        pass
```

## Configuration

```yaml
# config.example.yaml
exchange:
  id: binance            # Any CCXT-supported exchange
  api_key: ""            # Your API key
  secret: ""             # Your secret
  sandbox: true          # Use testnet first

trading:
  symbol: BTC/USDT
  mode: dry-run          # dry-run | live
  strategy: momentum     # Strategy module name

risk:
  max_position_usd: 1000
  max_daily_loss_usd: 50
  max_open_orders: 3
  cooldown_seconds: 30

logging:
  level: INFO
  trade_journal: true    # Export trades to CSV
  log_dir: ./logs
```

## Risk Controls

Built-in safety mechanisms that cannot be overridden by strategies:

| Control | Description |
|---------|-------------|
| Max Position | Hard cap on total exposure in USD |
| Daily Loss Limit | Stops trading after hitting daily loss threshold |
| Order Timeout | Auto-cancels unfilled orders after configurable duration |
| Cooldown | Enforces minimum time between trades |
| Kill Switch | Immediately flattens all positions and stops trading |
| Dry-Run Mode | Full simulation against live data, no real orders |

## Logging & Monitoring

Every trade is logged to both console and a CSV journal:

```
2024-01-15 14:23:01 | BUY  | BTC/USDT | 0.01 @ 42,150.00 | filled
2024-01-15 14:23:45 | SELL | BTC/USDT | 0.01 @ 42,210.00 | filled | PnL: +$0.60
```

## License

MIT — use it however you want.

## Disclaimer

This software is for educational and development purposes. Trading cryptocurrency involves substantial risk. Use at your own risk.
