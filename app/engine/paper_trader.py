"""
Paper Trading Engine

Simulates trading with virtual money.
Tracks performance without risking real funds.
"""
from typing import List, Optional, Dict
from datetime import datetime
from uuid import uuid4
import logging

from app.models.trade import Trade, TradeSignal, CopyDecision, TradingStats, TradeSide, TradeStatus
from app.config import get_settings

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    Paper trading engine for simulating trades.
    Uses virtual money to test strategy before going live.
    """
    
    def __init__(self, initial_balance: Optional[float] = None):
        self.settings = get_settings()
        
        # Initialize balance
        self._initial_balance = initial_balance or self.settings.paper_initial_balance
        self._balance = self._initial_balance
        
        # Trading state
        self._positions: Dict[str, Trade] = {}  # trade_id -> Trade
        self._trade_history: List[Trade] = []
        self._stats = TradingStats()
        
        # Balance history for charting
        self._balance_history: List[Dict] = [{
            "timestamp": datetime.utcnow().isoformat(),
            "balance": self._balance,
            "pnl": 0,
            "trade_count": 0
        }]
        
        logger.info(f"Paper trader initialized with ${self._initial_balance:,.2f}")
    
    @property
    def balance(self) -> float:
        """Current available balance"""
        return self._balance
    
    @property
    def total_value(self) -> float:
        """Total value including open positions (estimated)"""
        position_value = sum(
            trade.amount for trade in self._positions.values()
        )
        return self._balance + position_value
    
    @property
    def pnl(self) -> float:
        """Total profit/loss"""
        return self.total_value - self._initial_balance
    
    @property
    def pnl_percent(self) -> float:
        """PnL as percentage"""
        if self._initial_balance == 0:
            return 0
        return (self.pnl / self._initial_balance) * 100
    
    @property
    def stats(self) -> TradingStats:
        """Get trading statistics"""
        return self._stats
    
    @property
    def open_positions(self) -> List[Trade]:
        """Get all open positions"""
        return list(self._positions.values())
    
    @property
    def trade_history(self) -> List[Trade]:
        """Get all historical trades"""
        return self._trade_history
    
    def execute_trade(self, signal: TradeSignal, decision: CopyDecision) -> Optional[Trade]:
        """
        Execute a paper trade based on signal and decision.
        
        Args:
            signal: The trade signal
            decision: The copy decision with amount
        
        Returns:
            Trade object if executed, None if failed
        """
        if not decision.should_copy:
            logger.debug(f"Trade not copied: {decision.reason}")
            return None
        
        amount = decision.amount
        
        # Check balance
        if amount > self._balance:
            logger.warning(f"Insufficient balance: {amount} > {self._balance}")
            return None
        
        # Create trade
        trade = Trade(
            id=str(uuid4()),
            is_paper=True,
            whale_address=signal.whale_address,
            whale_name=signal.whale_name,
            market_id=signal.market_id,
            market_question=signal.market_question,
            category=signal.category,
            side=signal.side,
            amount=amount,
            entry_price=signal.price,
            whale_score_at_entry=signal.whale_score,
            consensus_count=decision.consensus_count,
            decision_reason=decision.reason,
            opened_at=datetime.utcnow()
        )
        
        # Deduct from balance
        self._balance -= amount
        
        # Add to positions
        self._positions[trade.id] = trade
        self._stats.total_trades += 1
        self._stats.open_trades += 1
        
        logger.info(
            f"📝 PAPER TRADE: {trade.side.value} on {trade.market_id[:20]}... "
            f"| Amount: ${amount:.2f} | Price: {trade.entry_price:.2f} "
            f"| Whale: {trade.whale_name or trade.whale_address[:10]}..."
        )
        
        self._record_balance()
        
        return trade
    
    def close_position(
        self,
        trade_id: str,
        final_price: float,
        outcome: Optional[str] = None
    ) -> Optional[Trade]:
        """
        Close an open position.
        
        Args:
            trade_id: The trade to close
            final_price: Exit price (1.0 for YES win, 0.0 for NO win)
            outcome: Optional outcome string (YES/NO)
        
        Returns:
            Updated trade or None if not found
        """
        if trade_id not in self._positions:
            logger.warning(f"Position not found: {trade_id}")
            return None
        
        trade = self._positions[trade_id]
        
        # Set exit price based on outcome
        if outcome == "YES":
            trade.exit_price = 1.0
        elif outcome == "NO":
            trade.exit_price = 0.0
        else:
            trade.exit_price = final_price
        
        # Calculate profit
        trade.calculate_profit()
        
        # Update status
        trade.status = TradeStatus.CLOSED
        trade.closed_at = datetime.utcnow()
        
        # Return funds + profit
        self._balance += trade.amount + (trade.profit or 0)
        
        # Update stats
        self._stats.update(trade)
        self._stats.open_trades -= 1
        
        # Move to history
        del self._positions[trade_id]
        self._trade_history.append(trade)
        
        status = "✅ WIN" if trade.profit and trade.profit > 0 else "❌ LOSS"
        logger.info(
            f"{status}: {trade.side.value} on {trade.market_id[:20]}... "
            f"| Profit: ${trade.profit or 0:+.2f} | New Balance: ${self._balance:.2f}"
        )
        
        self._record_balance()
        
        return trade
    
    def cancel_position(self, trade_id: str) -> Optional[Trade]:
        """Cancel an open position (refund full amount)"""
        if trade_id not in self._positions:
            return None
        
        trade = self._positions[trade_id]
        trade.status = TradeStatus.CANCELLED
        trade.closed_at = datetime.utcnow()
        trade.profit = 0
        
        # Refund
        self._balance += trade.amount
        
        # Update stats
        self._stats.open_trades -= 1
        
        # Move to history
        del self._positions[trade_id]
        self._trade_history.append(trade)
        
        logger.info(f"🚫 CANCELLED: {trade.id}")
        
        return trade
    
    def get_position_by_market(self, market_id: str) -> Optional[Trade]:
        """Get open position for a specific market"""
        for trade in self._positions.values():
            if trade.market_id == market_id:
                return trade
        return None
    
    def reset(self) -> None:
        """Reset paper trader to initial state"""
        self._balance = self._initial_balance
        self._positions.clear()
        self._trade_history.clear()
        self._stats = TradingStats()
        self._balance_history = [{
            "timestamp": datetime.utcnow().isoformat(),
            "balance": self._balance,
            "pnl": 0,
            "trade_count": 0
        }]
        logger.info("Paper trader reset")
    
    def _record_balance(self) -> None:
        """Record current balance for history"""
        self._balance_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "balance": self._balance,
            "pnl": self.pnl,
            "trade_count": len(self._trade_history)
        })
    
    def get_summary(self) -> Dict:
        """Get trading summary for dashboard"""
        return {
            "mode": "paper",
            "initial_balance": self._initial_balance,
            "current_balance": self._balance,
            "total_value": self.total_value,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "total_trades": self._stats.total_trades,
            "open_trades": self._stats.open_trades,
            "closed_trades": self._stats.closed_trades,
            "wins": self._stats.wins,
            "losses": self._stats.losses,
            "win_rate": self._stats.win_rate * 100,
            "best_trade": self._stats.best_trade_profit,
            "worst_trade": self._stats.worst_trade_loss,
            "avg_profit": self._stats.avg_profit_per_trade
        }
    
    def get_balance_history(self) -> List[Dict]:
        """Get balance history for charting"""
        return self._balance_history
    
    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get recent trades for display"""
        trades = sorted(
            self._trade_history,
            key=lambda t: t.opened_at,
            reverse=True
        )[:limit]
        
        result = []
        for trade in trades:
            result.append({
                "id": trade.id[:8],
                "market": trade.market_question or trade.market_id[:20],
                "side": trade.side.value,
                "amount": f"${trade.amount:.2f}",
                "entry_price": f"{trade.entry_price:.2f}",
                "exit_price": f"{trade.exit_price:.2f}" if trade.exit_price else "-",
                "profit": f"${trade.profit:+.2f}" if trade.profit else "-",
                "status": trade.status.value,
                "whale": trade.whale_name or trade.whale_address[:10],
                "opened_at": trade.opened_at.strftime("%Y-%m-%d %H:%M"),
                "is_winner": trade.is_winner
            })
        return result
