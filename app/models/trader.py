"""
Trader models for whale tracking
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class TraderStats(BaseModel):
    """Statistics for a trader"""
    win_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    roi_30d: float = Field(default=0.0)
    trade_count: int = Field(default=0, ge=0)
    max_drawdown: float = Field(default=0.0, ge=0.0, le=1.0)
    consistency: float = Field(default=0.0, ge=0.0, le=1.0)
    diversity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_trade_size: float = Field(default=0.0)
    total_profit: float = Field(default=0.0)
    
    @property
    def is_reliable(self) -> bool:
        """Check if trader has enough history to be reliable"""
        return self.trade_count >= 20


class Trader(BaseModel):
    """Whale trader model"""
    address: str = Field(..., min_length=42, max_length=42)
    name: Optional[str] = Field(default=None)
    
    # From leaderboard
    rank: Optional[int] = Field(default=None)
    profit: float = Field(default=0.0)
    volume: float = Field(default=0.0)
    
    # Calculated stats
    stats: TraderStats = Field(default_factory=TraderStats)
    
    # Our scoring
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    heat_level: str = Field(default="cold")  # cold, warm, hot
    
    # Status
    is_active: bool = Field(default=True)
    last_trade_at: Optional[datetime] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def update_heat_level(self):
        """Update heat level based on score"""
        if self.score >= 70:
            self.heat_level = "hot"
        elif self.score >= 50:
            self.heat_level = "warm"
        else:
            self.heat_level = "cold"
    
    class Config:
        json_schema_extra = {
            "example": {
                "address": "0x1234567890abcdef1234567890abcdef12345678",
                "name": "Whale Alpha",
                "rank": 1,
                "profit": 50000.0,
                "volume": 100000.0,
                "score": 85.5,
                "heat_level": "hot"
            }
        }


class TraderPosition(BaseModel):
    """A position held by a trader"""
    market_id: str
    market_question: Optional[str] = None
    side: str  # YES or NO
    shares: float
    avg_price: float
    current_price: float
    unrealized_pnl: float = Field(default=0.0)
    
    @property
    def value(self) -> float:
        return self.shares * self.current_price


class TraderActivity(BaseModel):
    """Recent activity of a trader"""
    address: str
    positions: List[TraderPosition] = Field(default_factory=list)
    recent_trades: List["Trade"] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# Avoid circular import
from app.models.trade import Trade
TraderActivity.model_rebuild()
