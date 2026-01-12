"""
Paper Trading Engine

Simulates trading with virtual money.
Tracks performance without risking real funds.
Now with DATABASE PERSISTENCE - trades survive restarts!
"""
from typing import List, Optional, Dict
from datetime import datetime
from uuid import uuid4
import logging

from app.models.trade import Trade, TradeSignal, CopyDecision, TradingStats, TradeSide, TradeStatus
from app.config import get_settings
from app.database import save_trade, update_trade, get_open_trades, get_last_balance, save_balance

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
        
        # Try to load last balance from database (RESTART RECOVERY)
        saved_balance = get_last_balance(is_paper=True)
        if saved_balance is not None:
            self._balance = saved_balance
            logger.info(f"💾 Restored balance from database: ${saved_balance:,.2f}")
        else:
            self._balance = self._initial_balance
        
        # Trading state
        self._positions: Dict[str, Trade] = {}  # trade_id -> Trade
        self._trade_history: List[Trade] = []
        self._stats = TradingStats()
        
        # Load open positions from database (RESTART RECOVERY)
        self._load_open_positions_from_db()
        
        # Balance history for charting
        self._balance_history: List[Dict] = [{
            "timestamp": datetime.utcnow().isoformat(),
            "balance": self._balance,
            "pnl": self.pnl,
            "trade_count": len(self._positions)
        }]
        
        logger.info(f"Paper trader initialized with ${self._balance:,.2f} ({len(self._positions)} open positions)")
    
    def _load_open_positions_from_db(self) -> None:
        """Load open positions from database on startup"""
        try:
            open_trades = get_open_trades(is_paper=True)
            for t in open_trades:
                trade = Trade(
                    id=t["id"],
                    is_paper=True,
                    whale_address=t["whale_address"],
                    whale_name=None,
                    market_id=t["market_id"],
                    market_question=t["market_question"],
                    category=t["category"],
                    side=TradeSide(t["side"]),
                    amount=t["amount"],
                    entry_price=t["entry_price"],
                    whale_score_at_entry=t.get("whale_score_at_entry"),
                    opened_at=t.get("opened_at", datetime.utcnow())
                )
                self._positions[trade.id] = trade
                self._stats.total_trades += 1
                self._stats.open_trades += 1
            
            if open_trades:
                logger.info(f"💾 Restored {len(open_trades)} open positions from database")
        except Exception as e:
            logger.warning(f"Could not load positions from database: {e}")
    
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
        
        REALISTIC SIMULATION:
        - Adds slippage (0.5%-3%) to simulate market impact
        - Rejects trades with >10% slippage (too late)
        
        Args:
            signal: The trade signal
            decision: The copy decision with amount
        
        Returns:
            Trade object if executed, None if failed
        """
        import random
        
        if not decision.should_copy:
            logger.debug(f"Trade not copied: {decision.reason}")
            return None
        
        amount = decision.amount
        
        # Check balance
        if amount > self._balance:
            logger.warning(f"Insufficient balance: {amount} > {self._balance}")
            return None
        
        # REALISTIC SLIPPAGE SIMULATION
        # Whale entered at signal.price, but we're late (API delay)
        # Simulating 0.5% - 3% slippage based on amount and delay
        base_slippage = random.uniform(0.005, 0.03)  # 0.5% to 3%
        
        # Larger amounts = more slippage
        size_impact = min(amount / 100, 0.02)  # Up to 2% extra for big orders
        
        total_slippage = base_slippage + size_impact
        
        # Apply slippage in unfavorable direction
        if signal.side == TradeSide.YES:
            # Buying YES = price goes up (worse for us)
            realistic_price = signal.price * (1 + total_slippage)
        else:
            # Buying NO = price goes down (worse for us)  
            realistic_price = signal.price * (1 - total_slippage)
        
        # Reject if slippage too high (>10% = missed opportunity)
        if abs(realistic_price - signal.price) / max(signal.price, 0.01) > 0.10:
            logger.warning(f"⚠️ REJECTED: Slippage too high ({total_slippage*100:.1f}%)")
            return None
        
        # Cap price at valid range
        realistic_price = max(0.01, min(0.99, realistic_price))
        
        # Create trade with REALISTIC price
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
            entry_price=realistic_price,  # SLIPPAGE APPLIED
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
        
        slippage_pct = (realistic_price - signal.price) / max(signal.price, 0.01) * 100
        logger.info(
            f"📝 PAPER TRADE: {trade.side.value} on {trade.market_id[:20]}... "
            f"| Amount: ${amount:.2f} | Whale: {signal.price:.2f} → Real: {realistic_price:.2f} "
            f"(Slippage: {slippage_pct:+.1f}%) | {trade.whale_name or trade.whale_address[:10]}"
        )
        
        # SAVE TO DATABASE for persistence
        try:
            save_trade({
                "id": trade.id,
                "is_paper": True,
                "whale_address": trade.whale_address,
                "market_id": trade.market_id,
                "market_question": trade.market_question,
                "category": trade.category,
                "side": trade.side.value,
                "amount": trade.amount,
                "entry_price": trade.entry_price,
                "whale_score_at_entry": trade.whale_score_at_entry,
                "consensus_count": trade.consensus_count,
                "decision_reason": trade.decision_reason,
                "opened_at": trade.opened_at,
                "status": "OPEN"
            })
            logger.debug(f"💾 Trade saved to database: {trade.id[:8]}")
        except Exception as e:
            logger.warning(f"Could not save trade to DB: {e}")
        
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
