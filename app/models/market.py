"""
Market models
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MarketCategory(str, Enum):
    POLITICS = "politics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    ENTERTAINMENT = "entertainment"
    SCIENCE = "science"
    OTHER = "other"


class MarketOutcome(str, Enum):
    YES = "YES"
    NO = "NO"
    PENDING = "PENDING"


class Market(BaseModel):
    """Prediction market model"""
    id: str
    question: str
    description: Optional[str] = None
    category: MarketCategory = Field(default=MarketCategory.OTHER)
    
    # Prices (0.0 to 1.0)
    yes_price: float = Field(default=0.5, ge=0.0, le=1.0)
    no_price: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # Volume and liquidity
    volume_24h: float = Field(default=0.0)
    total_volume: float = Field(default=0.0)
    liquidity: float = Field(default=0.0)
    
    # Resolution
    is_resolved: bool = Field(default=False)
    outcome: Optional[MarketOutcome] = None
    resolution_date: Optional[datetime] = None
    
    # Timestamps
    end_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Whale activity on this market
    whale_positions: int = Field(default=0)
    whale_volume: float = Field(default=0.0)
    
    @property
    def implied_probability_yes(self) -> float:
        """Implied probability of YES outcome"""
        return self.yes_price
    
    @property
    def implied_probability_no(self) -> float:
        """Implied probability of NO outcome"""
        return self.no_price
    
    @property
    def is_active(self) -> bool:
        """Check if market is still tradeable"""
        if self.is_resolved:
            return False
        if self.end_date and self.end_date < datetime.utcnow():
            return False
        return True
    
    @property
    def best_return_yes(self) -> float:
        """Potential return if YES wins (percentage)"""
        if self.yes_price <= 0:
            return 0
        return ((1.0 / self.yes_price) - 1) * 100
    
    @property
    def best_return_no(self) -> float:
        """Potential return if NO wins (percentage)"""
        if self.no_price <= 0:
            return 0
        return ((1.0 / self.no_price) - 1) * 100
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "0xabc123",
                "question": "Will BTC hit $100k in 2024?",
                "category": "crypto",
                "yes_price": 0.65,
                "no_price": 0.35,
                "volume_24h": 50000.0,
                "liquidity": 100000.0
            }
        }


class MarketWithWhales(Market):
    """Market with whale trader information"""
    top_whales_yes: List[str] = Field(default_factory=list)  # Addresses
    top_whales_no: List[str] = Field(default_factory=list)
    consensus: Optional[str] = None  # YES, NO, or MIXED
    consensus_strength: float = Field(default=0.0)  # 0-100
