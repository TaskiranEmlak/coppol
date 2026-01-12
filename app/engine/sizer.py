"""
Dynamic Trade Sizing

Calculates optimal trade size based on:
- Available balance
- Whale score/confidence
- Consensus count
- Risk settings
"""
from typing import Optional
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class DynamicSizer:
    """
    Dynamic position sizing based on confidence and risk management.
    
    Rules:
    - Never risk more than max_trade_percent of balance in single trade
    - Higher confidence = larger position
    - Consensus from multiple whales = larger position
    - Minimum trade = $1
    """
    
    # Score thresholds
    HIGH_CONFIDENCE = 90
    MEDIUM_CONFIDENCE = 70
    LOW_CONFIDENCE = 50
    
    def __init__(self):
        self.settings = get_settings()
    
    def calculate(
        self,
        balance: float,
        score: float,
        consensus: int = 1,
        min_amount: float = 1.0
    ) -> float:
        """
        Calculate optimal trade amount.
        
        Args:
            balance: Available balance
            score: Whale/decision score (0-100)
            consensus: Number of whales with same position
            min_amount: Minimum trade amount
        
        Returns:
            Trade amount in USD
        """
        max_percent = self.settings.max_trade_percent / 100
        
        # Base percentage based on score
        if score >= self.HIGH_CONFIDENCE:
            base_percent = 0.4  # 40% of max allowed
        elif score >= self.MEDIUM_CONFIDENCE:
            base_percent = 0.25  # 25% of max allowed
        elif score >= self.LOW_CONFIDENCE:
            base_percent = 0.1  # 10% of max allowed
        else:
            base_percent = 0.05  # 5% of max allowed
        
        # Consensus multiplier (up to 1.5x)
        consensus_multiplier = 1.0 + min((consensus - 1) * 0.25, 0.5)
        
        # Calculate amount
        percent = base_percent * consensus_multiplier
        percent = min(percent, max_percent)  # Cap at max
        
        amount = balance * percent
        
        # Apply constraints
        amount = max(amount, min_amount)  # Min $1
        amount = min(amount, balance * max_percent)  # Max percent
        amount = min(amount, balance)  # Can't exceed balance
        
        # Round to 2 decimal places
        amount = round(amount, 2)
        
        logger.debug(
            f"Sizing: balance=${balance:.2f}, score={score:.0f}, "
            f"consensus={consensus} => ${amount:.2f} ({percent*100:.1f}%)"
        )
        
        return amount
    
    def calculate_risk_reward(
        self,
        entry_price: float,
        side: str  # YES or NO
    ) -> dict:
        """
        Calculate potential risk/reward for a trade.
        
        Args:
            entry_price: Entry price (0-1)
            side: YES or NO
        
        Returns:
            Dict with potential_profit, potential_loss, risk_reward_ratio
        """
        if side == "YES":
            # If YES wins, price goes to 1.0
            potential_profit_percent = ((1.0 / entry_price) - 1) * 100
            potential_loss_percent = 100  # Lose entire stake
        else:
            # If NO wins, YES price goes to 0
            potential_profit_percent = ((1.0 / (1 - entry_price)) - 1) * 100
            potential_loss_percent = 100
        
        risk_reward = potential_profit_percent / potential_loss_percent if potential_loss_percent > 0 else 0
        
        return {
            "potential_profit_percent": round(potential_profit_percent, 1),
            "potential_loss_percent": round(potential_loss_percent, 1),
            "risk_reward_ratio": round(risk_reward, 2),
            "entry_price": entry_price,
            "side": side
        }
    
    def get_kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion for optimal bet sizing.
        
        Kelly % = (Win Rate * Avg Win - (1 - Win Rate) * Avg Loss) / Avg Win
        
        Note: We use a fractional Kelly (usually 0.25-0.5) for safety.
        """
        if avg_win <= 0 or avg_loss <= 0:
            return 0.1  # Default 10%
        
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        
        # Use quarter Kelly for safety
        fractional_kelly = kelly * 0.25
        
        # Clamp between 0.05 (5%) and 0.25 (25%)
        return max(0.05, min(fractional_kelly, 0.25))
