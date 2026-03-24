"""
Utility functions: logging setup, trade journal, and helpers.
"""
import logging
import os
import csv
import time
from datetime import datetime, timezone


def setup_logging(config: dict) -> logging.Logger:
    """Configure structured logging with console and optional file output."""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_dir = log_config.get("log_dir", "./logs")
    
    os.makedirs(log_dir, exist_ok=True)
    
    # Format
    fmt = "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    
    # Clear existing handlers
    root.handlers.clear()
    
    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(console)
    
    # File handler
    log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(file_handler)
    
    logging.getLogger("ccxt").setLevel(logging.WARNING)  # Quiet CCXT
    
    return root


class TradeJournal:
    """Logs every trade to a CSV file for analysis."""
    
    HEADERS = [
        "timestamp", "side", "symbol", "size", "price", "pnl",
        "daily_pnl", "total_pnl", "strategy", "metadata"
    ]
    
    def __init__(self, config: dict):
        log_dir = config.get("logging", {}).get("log_dir", "./logs")
        os.makedirs(log_dir, exist_ok=True)
        
        self.filepath = os.path.join(log_dir, "trade_journal.csv")
        self.symbol = config.get("trading", {}).get("symbol", "")
        self.strategy = config.get("trading", {}).get("strategy", "")
        
        # Write header if new file
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                csv.writer(f).writerow(self.HEADERS)
    
    def log_trade(self, side: str, size: float, price: float, 
                  pnl: float = 0, daily_pnl: float = 0, total_pnl: float = 0,
                  metadata: dict = None):
        """Append a trade record to the journal."""
        row = [
            datetime.now(timezone.utc).isoformat(),
            side,
            self.symbol,
            f"{size:.8f}",
            f"{price:.2f}",
            f"{pnl:.2f}",
            f"{daily_pnl:.2f}",
            f"{total_pnl:.2f}",
            self.strategy,
            str(metadata or {}),
        ]
        
        with open(self.filepath, "a", newline="") as f:
            csv.writer(f).writerow(row)


def format_usd(amount: float) -> str:
    """Format a dollar amount with sign and commas."""
    if amount >= 0:
        return f"+${amount:,.2f}"
    return f"-${abs(amount):,.2f}"


def timestamp_to_str(ts: float) -> str:
    """Convert Unix timestamp to readable string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
