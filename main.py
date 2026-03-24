#!/usr/bin/env python3
"""
Crypto Trading Bot — Main entry point.
Orchestrates data feed, strategy, order management, and risk controls.

Usage:
    python main.py                    # Uses config.yaml
    python main.py --config my.yaml   # Custom config
    python main.py --mode dry-run     # Override mode
"""
import argparse
import importlib
import signal
import sys
import time
import yaml
import logging

from core.data_feed import DataFeed
from core.order_manager import OrderManager
from core.risk_manager import RiskManager
from core.utils import setup_logging, TradeJournal
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger("main")


class TradingBot:
    """Main bot orchestrator."""
    
    def __init__(self, config: dict):
        self.config = config
        self.running = False
        
        # Initialize components
        self.data_feed = DataFeed(config)
        self.risk_manager = RiskManager(config)
        self.order_manager = OrderManager(config, exchange=None)
        self.strategy = self._load_strategy(config)
        self.journal = TradeJournal(config) if config.get("logging", {}).get("trade_journal") else None
        
        # Wire up callbacks
        self.order_manager.on_fill = self._handle_fill
        self.order_manager.on_cancel = self.strategy.on_cancel
        
        self.poll_interval = config.get("trading", {}).get("poll_interval", 1.0)
    
    def _load_strategy(self, config: dict) -> BaseStrategy:
        """Dynamically load strategy module."""
        strategy_name = config.get("trading", {}).get("strategy", "momentum")
        
        try:
            module = importlib.import_module(f"strategies.{strategy_name}")
        except ModuleNotFoundError:
            logger.error(f"Strategy '{strategy_name}' not found in strategies/")
            sys.exit(1)
        
        # Find the strategy class (first BaseStrategy subclass in module)
        strategy_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) 
                and issubclass(attr, BaseStrategy) 
                and attr is not BaseStrategy):
                strategy_class = attr
                break
        
        if not strategy_class:
            logger.error(f"No BaseStrategy subclass found in strategies/{strategy_name}.py")
            sys.exit(1)
        
        logger.info(f"Loaded strategy: {strategy_class.__name__}")
        return strategy_class(config, risk_manager=self.risk_manager)
    
    def _handle_fill(self, order: dict):
        """Handle order fill: update risk manager, log to journal, notify strategy."""
        # Notify strategy
        self.strategy.on_fill(order)
        
        # Log to journal
        if self.journal:
            self.journal.log_trade(
                side=order.get("side", ""),
                size=order.get("amount", 0),
                price=order.get("price", 0),
                daily_pnl=self.risk_manager.daily_pnl,
                total_pnl=self.risk_manager.total_pnl,
            )
    
    def start(self):
        """Connect and start the main trading loop."""
        mode = self.config.get("trading", {}).get("mode", "dry-run")
        symbol = self.config.get("trading", {}).get("symbol", "BTC/USDT")
        
        logger.info("=" * 60)
        logger.info(f"  STARTING BOT — {symbol} — {mode.upper()}")
        logger.info("=" * 60)
        
        # Connect to exchange
        self.data_feed.connect()
        self.order_manager.exchange = self.data_feed.exchange
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
        
        self.running = True
        tick_count = 0
        
        while self.running:
            try:
                self._tick(tick_count)
                tick_count += 1
                time.sleep(self.poll_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Tick error: {e}", exc_info=True)
                time.sleep(5)  # Back off on errors
        
        self._cleanup()
    
    def _tick(self, tick_count: int):
        """Single iteration of the main loop."""
        # Fetch market data
        market_data = self.data_feed.fetch_market_data()
        
        if not market_data.get("ticker"):
            return
        
        current_price = market_data["ticker"].get("last", 0)
        
        # Check existing orders
        self.order_manager.check_orders(current_price)
        
        # Generate strategy signal
        signal_obj = self.strategy.generate_signal(market_data)
        
        if signal_obj:
            # Validate through risk manager
            if self.risk_manager.can_open_position():
                self.order_manager.place_order(signal_obj)
            else:
                logger.debug("Signal rejected by risk manager")
        
        # Periodic stats logging
        if tick_count > 0 and tick_count % 60 == 0:
            self._log_stats(current_price)
    
    def _log_stats(self, price: float):
        """Log periodic status update."""
        risk = self.risk_manager.stats
        orders = self.order_manager.stats
        
        logger.info(
            f"STATUS | price=${price:,.2f} | "
            f"pnl=${risk['daily_pnl']:+.2f} (daily) ${risk['total_pnl']:+.2f} (total) | "
            f"trades={risk['trades']} win={risk['win_rate']}% | "
            f"orders: {orders['open']} open, {orders['filled']} filled"
        )
    
    def _shutdown(self, signum=None, frame=None):
        """Graceful shutdown handler."""
        logger.info("Shutdown signal received...")
        self.running = False
    
    def _cleanup(self):
        """Clean up on exit."""
        logger.info("Cleaning up...")
        self.order_manager.cancel_all()
        self.data_feed.disconnect()
        
        # Final stats
        risk = self.risk_manager.stats
        logger.info("=" * 60)
        logger.info(f"  FINAL STATS")
        logger.info(f"  Total PnL:  ${risk['total_pnl']:+.2f}")
        logger.info(f"  Trades:     {risk['trades']} ({risk['win_rate']}% win rate)")
        logger.info(f"  Wins/Losses: {risk['wins']}/{risk['losses']}")
        logger.info("=" * 60)


def load_config(path: str) -> dict:
    """Load YAML configuration file."""
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Config file not found: {path}")
        print("Copy config.example.yaml to config.yaml and edit it.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Crypto Trading Bot")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--mode", choices=["dry-run", "live"], help="Override trading mode")
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    if args.mode:
        config.setdefault("trading", {})["mode"] = args.mode
    
    setup_logging(config)
    
    bot = TradingBot(config)
    bot.start()


if __name__ == "__main__":
    main()
