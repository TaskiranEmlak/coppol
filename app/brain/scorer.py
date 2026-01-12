"""
Trader Scoring Algorithm (Heat Map Logic)

Puanlama Kriterleri:
- Win Rate (25%): %60+ ideal
- ROI 30 gün (20%): Getiri oranı
- İşlem Sayısı (15%): Min 50+ güvenilir
- Max Drawdown (15%): %-20'den az olmalı
- Tutarlılık (15%): Volatilite düşük olmalı
- Çeşitlilik (10%): Farklı kategorilerde başarı

Skor = 0-100 Heat Map:
- 🔴 0-40: KOPYALANMAZ (cold)
- 🟡 40-70: DİKKATLİ (warm)
- 🟢 70-100: KOPYALA (hot)
"""
from typing import Optional
import logging

from app.models.trader import Trader, TraderStats

logger = logging.getLogger(__name__)


class TraderScorer:
    """
    Heat Map based trader scoring system.
    Calculates a 0-100 score based on multiple metrics.
    """
    
    # Weight configuration
    WEIGHTS = {
        "win_rate": 0.25,
        "roi": 0.20,
        "trade_count": 0.15,
        "max_drawdown": 0.15,
        "consistency": 0.15,
        "diversity": 0.10
    }
    
    # Thresholds for scoring
    WIN_RATE_EXCELLENT = 0.65
    WIN_RATE_GOOD = 0.55
    WIN_RATE_MIN = 0.45
    
    ROI_EXCELLENT = 0.30  # 30%+
    ROI_GOOD = 0.15       # 15%+
    ROI_MIN = 0.05        # 5%+
    
    TRADES_EXCELLENT = 100
    TRADES_GOOD = 50
    TRADES_MIN = 20
    
    DRAWDOWN_EXCELLENT = 0.10  # 10% or less
    DRAWDOWN_GOOD = 0.20       # 20% or less
    DRAWDOWN_MAX = 0.40        # 40% = bad
    
    def __init__(self):
        self._cache = {}
    
    def calculate_score(self, trader: Trader) -> float:
        """
        Calculate overall score for a trader (0-100).
        """
        stats = trader.stats
        
        # Calculate each component
        win_rate_score = self._score_win_rate(stats.win_rate)
        roi_score = self._score_roi(stats.roi_30d)
        trade_count_score = self._score_trade_count(stats.trade_count)
        drawdown_score = self._score_drawdown(stats.max_drawdown)
        consistency_score = self._score_consistency(stats.consistency)
        diversity_score = self._score_diversity(stats.diversity_score)
        
        # Weighted sum
        total_score = (
            win_rate_score * self.WEIGHTS["win_rate"] +
            roi_score * self.WEIGHTS["roi"] +
            trade_count_score * self.WEIGHTS["trade_count"] +
            drawdown_score * self.WEIGHTS["max_drawdown"] +
            consistency_score * self.WEIGHTS["consistency"] +
            diversity_score * self.WEIGHTS["diversity"]
        )
        
        # Clamp to 0-100
        final_score = min(max(total_score, 0), 100)
        
        # Update trader
        trader.score = final_score
        trader.update_heat_level()
        
        logger.debug(
            f"Scored {trader.address[:10]}...: "
            f"WR={win_rate_score:.0f}, ROI={roi_score:.0f}, "
            f"TC={trade_count_score:.0f}, DD={drawdown_score:.0f}, "
            f"CON={consistency_score:.0f}, DIV={diversity_score:.0f} "
            f"=> {final_score:.1f} ({trader.heat_level})"
        )
        
        return final_score
    
    def _score_win_rate(self, win_rate: float) -> float:
        """Score win rate (0-100)"""
        if win_rate >= self.WIN_RATE_EXCELLENT:
            return 100
        elif win_rate >= self.WIN_RATE_GOOD:
            # Linear interpolation between GOOD and EXCELLENT
            return 60 + (win_rate - self.WIN_RATE_GOOD) / (self.WIN_RATE_EXCELLENT - self.WIN_RATE_GOOD) * 40
        elif win_rate >= self.WIN_RATE_MIN:
            return 30 + (win_rate - self.WIN_RATE_MIN) / (self.WIN_RATE_GOOD - self.WIN_RATE_MIN) * 30
        else:
            return win_rate / self.WIN_RATE_MIN * 30
    
    def _score_roi(self, roi: float) -> float:
        """Score ROI (0-100)"""
        if roi <= 0:
            return max(0, 20 + roi * 100)  # Negative ROI = low score
        elif roi >= self.ROI_EXCELLENT:
            return 100
        elif roi >= self.ROI_GOOD:
            return 70 + (roi - self.ROI_GOOD) / (self.ROI_EXCELLENT - self.ROI_GOOD) * 30
        elif roi >= self.ROI_MIN:
            return 40 + (roi - self.ROI_MIN) / (self.ROI_GOOD - self.ROI_MIN) * 30
        else:
            return 20 + roi / self.ROI_MIN * 20
    
    def _score_trade_count(self, count: int) -> float:
        """Score trade count (0-100)"""
        if count >= self.TRADES_EXCELLENT:
            return 100
        elif count >= self.TRADES_GOOD:
            return 60 + (count - self.TRADES_GOOD) / (self.TRADES_EXCELLENT - self.TRADES_GOOD) * 40
        elif count >= self.TRADES_MIN:
            return 30 + (count - self.TRADES_MIN) / (self.TRADES_GOOD - self.TRADES_MIN) * 30
        else:
            return count / self.TRADES_MIN * 30
    
    def _score_drawdown(self, drawdown: float) -> float:
        """Score max drawdown (0-100) - lower is better"""
        if drawdown <= self.DRAWDOWN_EXCELLENT:
            return 100
        elif drawdown <= self.DRAWDOWN_GOOD:
            return 70 + (self.DRAWDOWN_GOOD - drawdown) / (self.DRAWDOWN_GOOD - self.DRAWDOWN_EXCELLENT) * 30
        elif drawdown <= self.DRAWDOWN_MAX:
            return 30 + (self.DRAWDOWN_MAX - drawdown) / (self.DRAWDOWN_MAX - self.DRAWDOWN_GOOD) * 40
        else:
            return max(0, 30 - (drawdown - self.DRAWDOWN_MAX) * 100)
    
    def _score_consistency(self, consistency: float) -> float:
        """Score consistency (0-100)"""
        # Consistency is already 0-1, just scale to 0-100
        return consistency * 100
    
    def _score_diversity(self, diversity: float) -> float:
        """Score diversity (0-100)"""
        # Diversity is already 0-1, just scale to 0-100
        return diversity * 100
    
    def get_heat_level(self, score: float) -> str:
        """Get heat level string from score"""
        if score >= 70:
            return "hot"
        elif score >= 50:
            return "warm"
        else:
            return "cold"
    
    def get_heat_color(self, score: float) -> str:
        """Get CSS color for heat level"""
        if score >= 70:
            return "#22c55e"  # Green
        elif score >= 50:
            return "#eab308"  # Yellow
        else:
            return "#ef4444"  # Red
    
    def get_heat_emoji(self, score: float) -> str:
        """Get emoji for heat level"""
        if score >= 70:
            return "🟢"
        elif score >= 50:
            return "🟡"
        else:
            return "🔴"
