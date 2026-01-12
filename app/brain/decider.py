"""
Copy Trade Decision Mechanism

Decides whether to copy a whale's trade based on:
1. Whale's current score
2. Consensus (how many whales are on the same side)
3. Market liquidity
4. Current balance and position limits
5. Previous trades on the same market
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

from app.models.trader import Trader
from app.models.trade import TradeSignal, CopyDecision, Trade, TradeStatus
from app.models.market import Market
from app.brain.scorer import TraderScorer
from app.config import get_settings

logger = logging.getLogger(__name__)


class CopyDecider:
    """
    The brain that decides whether to copy a whale's trade.
    """
    
    # Minimum score to consider copying
    MIN_SCORE_TO_COPY = 50
    
    # Consensus bonus (per additional whale)
    CONSENSUS_BONUS = 10
    MAX_CONSENSUS_BONUS = 30
    
    # Score thresholds for trade sizing
    HIGH_CONFIDENCE_SCORE = 90
    MEDIUM_CONFIDENCE_SCORE = 70
    LOW_CONFIDENCE_SCORE = 50
    
    def __init__(self, scorer: Optional[TraderScorer] = None):
        self.scorer = scorer or TraderScorer()
        self.settings = get_settings()
        
        # Track recent decisions to avoid duplicates
        self._recent_decisions: Dict[str, datetime] = {}
        
        # Track open positions per market
        self._open_positions: Dict[str, str] = {}  # market_id -> trade_id
    
    def decide(
        self,
        signal: TradeSignal,
        whale: Trader,
        balance: float,
        market: Optional[Market] = None,
        other_whale_signals: Optional[List[TradeSignal]] = None
    ) -> CopyDecision:
        """
        Main decision method - should we copy this trade?
        
        Args:
            signal: The trade signal from the whale
            whale: The whale trader who made the trade
            balance: Current available balance
            market: Optional market data
            other_whale_signals: Signals from other whales on same market
        
        Returns:
            CopyDecision with copy=True/False and reasoning
        """
        
        # Update signal with whale info
        signal.whale_score = whale.score
        signal.whale_name = whale.name
        
        # Check 1: Is the whale score high enough?
        if whale.score < self.settings.min_whale_score:
            return CopyDecision(
                should_copy=False,
                reason=f"Whale skoru düşük: {whale.score:.0f} < {self.settings.min_whale_score}",
                confidence=whale.score
            )
        
        # Check 2: Do we have enough balance?
        if balance < 1.0:
            return CopyDecision(
                should_copy=False,
                reason="Yetersiz bakiye (min $1)",
                confidence=whale.score
            )
        
        # Check 3: Did we already trade this market recently?
        if self._has_recent_decision(signal.market_id):
            return CopyDecision(
                should_copy=False,
                reason="Bu markette yakın zamanda işlem yapıldı",
                confidence=whale.score
            )
        
        # Check 4: Do we already have an open position on this market?
        if signal.market_id in self._open_positions:
            return CopyDecision(
                should_copy=False,
                reason="Bu markette açık pozisyon var",
                confidence=whale.score
            )
        
        # Check 5: Calculate consensus
        consensus_count = 1  # This whale counts as 1
        if other_whale_signals:
            for other_signal in other_whale_signals:
                if (other_signal.market_id == signal.market_id and 
                    other_signal.side == signal.side and
                    other_signal.whale_address != signal.whale_address):
                    consensus_count += 1
        
        # Calculate final score with consensus bonus
        consensus_bonus = min(
            (consensus_count - 1) * self.CONSENSUS_BONUS,
            self.MAX_CONSENSUS_BONUS
        )
        final_score = min(whale.score + consensus_bonus, 100)
        
        # Check 6: Check market liquidity (if market data available)
        if market and market.liquidity < 1000:
            # Low liquidity warning, reduce confidence
            final_score = min(final_score, 60)
        
        # Final decision threshold
        if final_score < self.MIN_SCORE_TO_COPY:
            return CopyDecision(
                should_copy=False,
                reason=f"Yetersiz güven skoru: {final_score:.0f} < {self.MIN_SCORE_TO_COPY}",
                confidence=final_score,
                consensus_count=consensus_count
            )
        
        # Calculate trade amount
        amount = self._calculate_amount(balance, final_score, consensus_count)
        
        # Build reason string
        reason_parts = [f"Skor: {final_score:.0f}"]
        if consensus_count > 1:
            reason_parts.append(f"{consensus_count} whale onayladı")
        reason_parts.append(f"${amount:.2f} işlem")
        
        # Record decision
        self._recent_decisions[signal.market_id] = datetime.utcnow()
        
        return CopyDecision(
            should_copy=True,
            amount=amount,
            reason=" | ".join(reason_parts),
            confidence=final_score,
            consensus_count=consensus_count
        )
    
    def _calculate_amount(
        self,
        balance: float,
        score: float,
        consensus: int
    ) -> float:
        """
        Calculate trade amount based on score and consensus.
        
        Rules:
        - Max 50% of balance in single trade
        - Score 90+ and 3+ consensus = 50% of balance
        - Score 70-90 = 25% of balance
        - Score 50-70 = 10% of balance
        - Min trade = $1
        """
        max_percent = self.settings.max_trade_percent / 100
        
        if score >= self.HIGH_CONFIDENCE_SCORE and consensus >= 3:
            percent = max_percent  # Full allowed percentage
        elif score >= self.MEDIUM_CONFIDENCE_SCORE:
            percent = max_percent * 0.5  # Half
        else:
            percent = max_percent * 0.2  # 20% of max
        
        amount = balance * percent
        
        # Ensure minimum $1
        amount = max(amount, 1.0)
        
        # Ensure we don't exceed max percent
        amount = min(amount, balance * max_percent)
        
        # Ensure we have enough balance
        amount = min(amount, balance)
        
        return round(amount, 2)
    
    def _has_recent_decision(self, market_id: str, cooldown_minutes: int = 30) -> bool:
        """Check if we made a decision on this market recently"""
        if market_id not in self._recent_decisions:
            return False
        
        last_decision = self._recent_decisions[market_id]
        cooldown = timedelta(minutes=cooldown_minutes)
        
        return datetime.utcnow() - last_decision < cooldown
    
    def register_position(self, market_id: str, trade_id: str) -> None:
        """Register an open position"""
        self._open_positions[market_id] = trade_id
    
    def close_position(self, market_id: str) -> None:
        """Mark a position as closed"""
        if market_id in self._open_positions:
            del self._open_positions[market_id]
    
    def clear_cooldowns(self) -> None:
        """Clear all cooldowns"""
        self._recent_decisions.clear()
    
    def get_consensus_for_market(
        self,
        market_id: str,
        signals: List[TradeSignal]
    ) -> Dict:
        """Get consensus information for a market"""
        yes_count = 0
        no_count = 0
        yes_addresses = []
        no_addresses = []
        
        for signal in signals:
            if signal.market_id != market_id:
                continue
            
            if signal.side.value == "YES":
                yes_count += 1
                yes_addresses.append(signal.whale_address)
            else:
                no_count += 1
                no_addresses.append(signal.whale_address)
        
        total = yes_count + no_count
        if total == 0:
            consensus = "NONE"
            strength = 0
        elif yes_count > no_count:
            consensus = "YES"
            strength = (yes_count / total) * 100
        elif no_count > yes_count:
            consensus = "NO"
            strength = (no_count / total) * 100
        else:
            consensus = "MIXED"
            strength = 50
        
        return {
            "market_id": market_id,
            "consensus": consensus,
            "strength": strength,
            "yes_count": yes_count,
            "no_count": no_count,
            "yes_whales": yes_addresses,
            "no_whales": no_addresses
        }
