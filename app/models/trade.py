"""
Trade models
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class TradeSide(str, Enum):
    YES = "YES"
    NO = "NO"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TradeSignal(BaseModel):
    """A signal detected from a whale trade"""
    whale_address: str
    whale_name: Optional[str] = None
    whale_score: float = Field(default=0.0)
    
    market_id: str
    market_question: Optional[str] = None
    category: Optional[str] = None
    
    side: TradeSide
    amount: float
    price: float
    
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "whale_address": "0x1234567890abcdef1234567890abcdef12345678",
                "whale_name": "Whale Alpha",
                "whale_score": 85.0,
                "market_id": "0xabc123",
                "market_question": "Will BTC hit $100k in 2024?",
                "category": "crypto",
                "side": "YES",
                "amount": 5000.0,
                "price": 0.65
            }
        }


class CopyDecision(BaseModel):
    """Decision whether to copy a trade"""
    should_copy: bool
    amount: float = Field(default=0.0)
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    consensus_count: int = Field(default=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "copy": True,
                "amount": 5.0,
                "reason": "Skor: 85, 3 whale onayladı",
                "confidence": 85.0,
                "consensus_count": 3
            }
        }


class Trade(BaseModel):
    """A trade (paper or real)"""
    id: str  # UUID
    is_paper: bool = Field(default=True)
    
    # Source
    whale_address: str
    whale_name: Optional[str] = None
    
    # Market
    market_id: str
    market_question: Optional[str] = None
    category: Optional[str] = None
    
    # Position
    side: TradeSide
    amount: float
    entry_price: float
    exit_price: Optional[float] = None
    
    # Status
    status: TradeStatus = Field(default=TradeStatus.OPEN)
    profit: Optional[float] = None
    profit_percent: Optional[float] = None
    
    # Decision context
    whale_score_at_entry: float = Field(default=0.0)
    consensus_count: int = Field(default=1)
    decision_reason: Optional[str] = None
    
    # Timestamps
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    
    @property
    def is_winner(self) -> Optional[bool]:
        """Check if trade was profitable"""
        if self.profit is None:
            return None
        return self.profit > 0
    
    def calculate_profit(self):
        """Calculate profit based on binary option logic"""
        if self.exit_price is None:
            return
        
        # Binary outcome: YES wins = exit_price=1, NO wins = exit_price=0
        if self.side == TradeSide.YES:
            if self.exit_price >= 0.99:  # YES won
                self.profit = self.amount * (1.0 / self.entry_price - 1)
            else:  # YES lost
                self.profit = -self.amount
        else:  # NO side
            if self.exit_price <= 0.01:  # NO won (YES price = 0)
                self.profit = self.amount * (1.0 / (1 - self.entry_price) - 1)
            else:  # NO lost
                self.profit = -self.amount
        
        if self.amount > 0:
            self.profit_percent = (self.profit / self.amount) * 100


class TradingStats(BaseModel):
    """Overall trading statistics"""
    total_trades: int = Field(default=0)
    open_trades: int = Field(default=0)
    closed_trades: int = Field(default=0)
    
    wins: int = Field(default=0)
    losses: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    
    total_profit: float = Field(default=0.0)
    total_invested: float = Field(default=0.0)
    roi: float = Field(default=0.0)
    
    best_trade_profit: float = Field(default=0.0)
    worst_trade_loss: float = Field(default=0.0)
    avg_profit_per_trade: float = Field(default=0.0)
    
    def update(self, trade: Trade):
        """Update stats with a closed trade"""
        if trade.status != TradeStatus.CLOSED or trade.profit is None:
            return
        
        self.closed_trades += 1
        self.total_invested += trade.amount
        self.total_profit += trade.profit
        
        if trade.profit > 0:
            self.wins += 1
            if trade.profit > self.best_trade_profit:
                self.best_trade_profit = trade.profit
        else:
            self.losses += 1
            if trade.profit < self.worst_trade_loss:
                self.worst_trade_loss = trade.profit
        
        if self.closed_trades > 0:
            self.win_rate = self.wins / self.closed_trades
            self.avg_profit_per_trade = self.total_profit / self.closed_trades
        
        if self.total_invested > 0:
            self.roi = self.total_profit / self.total_invested
