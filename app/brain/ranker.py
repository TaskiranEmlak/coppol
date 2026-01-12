"""
Trader Ranking System

Ranks and manages the top whale traders to follow.
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from app.models.trader import Trader
from app.brain.scorer import TraderScorer
from app.config import get_settings

logger = logging.getLogger(__name__)


class TraderRanker:
    """
    Manages and ranks whale traders.
    Keeps track of top performers and updates rankings.
    """
    
    def __init__(self, scorer: Optional[TraderScorer] = None):
        self.scorer = scorer or TraderScorer()
        self.settings = get_settings()
        
        # Tracked traders
        self._traders: Dict[str, Trader] = {}
        self._rankings: List[str] = []  # Ordered list of addresses
        
        # Last update time
        self._last_updated: Optional[datetime] = None
    
    @property
    def traders(self) -> List[Trader]:
        """Get all tracked traders"""
        return list(self._traders.values())
    
    @property
    def top_traders(self) -> List[Trader]:
        """Get top N traders by score"""
        return self.get_top(self.settings.max_whales)
    
    def add_trader(self, trader: Trader) -> None:
        """Add or update a trader"""
        # Calculate score if not set
        if trader.score == 0:
            self.scorer.calculate_score(trader)
        
        self._traders[trader.address] = trader
        self._update_rankings()
    
    def add_traders(self, traders: List[Trader]) -> None:
        """Add multiple traders"""
        for trader in traders:
            if trader.score == 0:
                self.scorer.calculate_score(trader)
            self._traders[trader.address] = trader
        
        self._update_rankings()
    
    def remove_trader(self, address: str) -> bool:
        """Remove a trader from tracking"""
        if address in self._traders:
            del self._traders[address]
            self._update_rankings()
            return True
        return False
    
    def get_trader(self, address: str) -> Optional[Trader]:
        """Get a specific trader by address"""
        return self._traders.get(address)
    
    def get_top(self, n: int = 10) -> List[Trader]:
        """Get top N traders by score"""
        return [
            self._traders[addr] 
            for addr in self._rankings[:n]
            if addr in self._traders
        ]
    
    def get_by_heat_level(self, level: str) -> List[Trader]:
        """Get traders by heat level (hot, warm, cold)"""
        return [
            t for t in self._traders.values()
            if t.heat_level == level
        ]
    
    def get_hot_traders(self) -> List[Trader]:
        """Get all hot (score >= 70) traders"""
        return self.get_by_heat_level("hot")
    
    def get_active_traders(self, within_hours: int = 24) -> List[Trader]:
        """Get traders active within the specified hours"""
        cutoff = datetime.utcnow() - timedelta(hours=within_hours)
        return [
            t for t in self._traders.values()
            if t.last_trade_at and t.last_trade_at > cutoff
        ]
    
    def update_scores(self) -> None:
        """Recalculate scores for all traders"""
        for trader in self._traders.values():
            self.scorer.calculate_score(trader)
        
        self._update_rankings()
        self._last_updated = datetime.utcnow()
        
        logger.info(f"Updated scores for {len(self._traders)} traders")
    
    def _update_rankings(self) -> None:
        """Update the ranking order"""
        # Sort by score (descending)
        sorted_traders = sorted(
            self._traders.values(),
            key=lambda t: t.score,
            reverse=True
        )
        self._rankings = [t.address for t in sorted_traders]
    
    def get_rankings_summary(self) -> Dict:
        """Get a summary of current rankings"""
        hot = len(self.get_by_heat_level("hot"))
        warm = len(self.get_by_heat_level("warm"))
        cold = len(self.get_by_heat_level("cold"))
        
        return {
            "total_tracked": len(self._traders),
            "hot_count": hot,
            "warm_count": warm,
            "cold_count": cold,
            "top_score": self._traders[self._rankings[0]].score if self._rankings else 0,
            "avg_score": sum(t.score for t in self._traders.values()) / len(self._traders) if self._traders else 0,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None
        }
    
    def export_leaderboard(self) -> List[Dict]:
        """Export leaderboard as list of dicts for display"""
        result = []
        for i, addr in enumerate(self._rankings, 1):
            trader = self._traders[addr]
            result.append({
                "rank": i,
                "address": trader.address,
                "name": trader.name or f"Whale #{i}",
                "score": round(trader.score, 1),
                "heat_level": trader.heat_level,
                "heat_emoji": self.scorer.get_heat_emoji(trader.score),
                "heat_color": self.scorer.get_heat_color(trader.score),
                "win_rate": f"{trader.stats.win_rate * 100:.1f}%",
                "profit": f"${trader.profit:,.0f}",
                "trade_count": trader.stats.trade_count,
                "is_active": trader.is_active
            })
        return result
