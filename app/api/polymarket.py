"""
Polymarket API Client

Endpoints:
- Gamma API: Market data (no auth required)
- Data API: Leaderboard, positions (no auth required)
- CLOB API: Trading (auth required for real trades)
"""
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import logging

from app.models.trader import Trader, TraderStats
from app.models.market import Market, MarketCategory
from app.models.trade import TradeSignal, TradeSide
from app.config import get_settings

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Client for Polymarket APIs"""
    
    # API Base URLs
    GAMMA_BASE = "https://gamma-api.polymarket.com"
    DATA_BASE = "https://data-api.polymarket.com"
    CLOB_BASE = "https://clob.polymarket.com"
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "PolymarketCopyTradeBot/1.0"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "PolymarketCopyTradeBot/1.0"}
            )
        return self._client
    
    # ==================== GAMMA API (Markets) ====================
    
    async def get_markets(
        self,
        limit: int = 100,
        active: bool = True,
        category: Optional[str] = None
    ) -> List[Market]:
        """Get list of markets from Gamma API"""
        try:
            # Sort by volume to get most relevant markets
            params = {
                "limit": limit, 
                "active": str(active).lower(), 
                "order": "volume24hr", 
                "ascending": "false"
            }
            if category:
                params["tag"] = category
            
            response = await self.client.get(
                f"{self.GAMMA_BASE}/markets",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for m in data:
                try:
                    # Parse category from tags
                    tags = m.get("tags", [])
                    cat = self._parse_category(tags)
                    
                    # Get prices from outcomes
                    outcomes = m.get("outcomePrices", "")
                    yes_price, no_price = self._parse_prices(outcomes)
                    
                    market = Market(
                        id=m.get("conditionId", m.get("id", "")),
                        question=m.get("question", "Unknown"),
                        description=m.get("description"),
                        category=cat,
                        yes_price=yes_price,
                        no_price=no_price,
                        volume_24h=float(m.get("volume24hr", 0)),
                        total_volume=float(m.get("volume", 0)),
                        liquidity=float(m.get("liquidity", 0)),
                        is_resolved=m.get("closed", False),
                        end_date=self._parse_datetime(m.get("endDate"))
                    )
                    markets.append(market)
                except Exception as e:
                    logger.warning(f"Error parsing market: {e}")
                    continue
            
            return markets
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    async def get_market(self, market_id: str) -> Optional[Market]:
        """Get single market by ID"""
        try:
            response = await self.client.get(
                f"{self.GAMMA_BASE}/markets/{market_id}"
            )
            response.raise_for_status()
            m = response.json()
            
            tags = m.get("tags", [])
            cat = self._parse_category(tags)
            outcomes = m.get("outcomePrices", "")
            yes_price, no_price = self._parse_prices(outcomes)
            
            return Market(
                id=m.get("conditionId", m.get("id", "")),
                question=m.get("question", "Unknown"),
                description=m.get("description"),
                category=cat,
                yes_price=yes_price,
                no_price=no_price,
                volume_24h=float(m.get("volume24hr", 0)),
                total_volume=float(m.get("volume", 0)),
                liquidity=float(m.get("liquidity", 0)),
                is_resolved=m.get("closed", False),
                end_date=self._parse_datetime(m.get("endDate"))
            )
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None
    
    # ==================== DATA API (Leaderboard, Positions) ====================
    
    async def get_leaderboard(self, limit: int = 50) -> List[Trader]:
        """Get top traders from leaderboard"""
        try:
            response = await self.client.get(
                f"{self.DATA_BASE}/v1/leaderboard",
                params={"window": "all", "limit": limit}
            )
            response.raise_for_status()
            data = response.json()
            
            traders = []
            for i, t in enumerate(data, 1):
                try:
                    # Use correct API field names
                    address = t.get("proxyWallet", f"0x{i:040x}")
                    username = t.get("userName", "")
                    profit = float(t.get("pnl", 0))
                    volume = float(t.get("vol", 0))
                    
                    # Build display name
                    if username and not username.isdigit():
                        name = username
                    else:
                        name = f"{address[:6]}...{address[-4:]}"
                    
                    # Better win rate estimation based on profit and rank
                    base_win_rate = 0.55
                    
                    # Boost based on rank (top 5 get bigger boost)
                    if i <= 5:
                        rank_boost = 0.15
                    elif i <= 10:
                        rank_boost = 0.10
                    elif i <= 20:
                        rank_boost = 0.05
                    else:
                        rank_boost = 0.0
                    
                    # Boost based on ROI
                    roi_boost = 0.0
                    if volume > 0:
                        roi = profit / volume
                        roi_boost = min(roi * 0.5, 0.15)
                    
                    estimated_win_rate = min(base_win_rate + rank_boost + roi_boost, 0.85)
                    
                    # Estimate trade count
                    trade_count = max(50 - i * 2, 10)
                    
                    # Consistency based on profit stability
                    consistency = 0.7 if profit > 0 else 0.3
                    
                    stats = TraderStats(
                        win_rate=estimated_win_rate,
                        roi_30d=profit / max(volume, 1) if volume > 0 else 0,
                        trade_count=trade_count,
                        total_profit=profit,
                        consistency=consistency,
                        diversity_score=0.5,
                        max_drawdown=0.15 if profit > 0 else 0.30
                    )
                    
                    trader = Trader(
                        address=address,
                        name=name,
                        rank=i,
                        profit=profit,
                        volume=volume,
                        stats=stats,
                        is_active=True
                    )
                    traders.append(trader)
                except Exception as e:
                    logger.warning(f"Error parsing trader: {e}")
                    continue
            
            return traders
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            return []
    
    async def get_trader_positions(self, address: str) -> List[Dict[str, Any]]:
        """Get positions for a specific trader"""
        try:
            response = await self.client.get(
                f"{self.DATA_BASE}/v1/positions",
                params={"user": address}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching positions for {address}: {e}")
            return []
    
    async def get_trader_trades(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trades for a specific trader"""
        try:
            response = await self.client.get(
                f"{self.DATA_BASE}/v1/trades",
                params={"maker": address, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching trades for {address}: {e}")
            return []
    
    async def get_market_trades(self, market_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a market"""
        try:
            response = await self.client.get(
                f"{self.DATA_BASE}/v1/trades",
                params={"market": market_id, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching trades for market {market_id}: {e}")
            return []
    
    # ==================== Whale Detection ====================
    
    async def detect_whale_trades(
        self,
        whale_addresses: List[str],
        since_minutes: int = 5
    ) -> List[TradeSignal]:
        """Detect recent trades from tracked whales"""
        signals = []
        
        for address in whale_addresses:
            try:
                trades = await self.get_trader_trades(address, limit=10)
                
                for trade in trades:
                    # Check if trade is recent
                    trade_time = self._parse_datetime(trade.get("timestamp"))
                    if trade_time:
                        age_minutes = (datetime.utcnow() - trade_time).total_seconds() / 60
                        if age_minutes > since_minutes:
                            continue
                    
                    # Parse trade signal
                    signal = TradeSignal(
                        whale_address=address,
                        market_id=trade.get("market", ""),
                        side=TradeSide.YES if trade.get("side") == "buy" else TradeSide.NO,
                        amount=float(trade.get("size", 0)),
                        price=float(trade.get("price", 0.5)),
                        detected_at=datetime.utcnow()
                    )
                    signals.append(signal)
                    
            except Exception as e:
                logger.warning(f"Error detecting trades for {address}: {e}")
                continue
        
        return signals
    
    # ==================== Helper Methods ====================
    
    def _parse_category(self, tags: List[str]) -> MarketCategory:
        """Parse market category from tags"""
        tags_lower = [t.lower() for t in tags]
        
        if any(t in tags_lower for t in ["politics", "election", "trump", "biden"]):
            return MarketCategory.POLITICS
        elif any(t in tags_lower for t in ["crypto", "bitcoin", "ethereum", "btc", "eth"]):
            return MarketCategory.CRYPTO
        elif any(t in tags_lower for t in ["sports", "nfl", "nba", "soccer", "football"]):
            return MarketCategory.SPORTS
        elif any(t in tags_lower for t in ["entertainment", "movies", "music", "celebrity"]):
            return MarketCategory.ENTERTAINMENT
        elif any(t in tags_lower for t in ["science", "tech", "ai", "space"]):
            return MarketCategory.SCIENCE
        else:
            return MarketCategory.OTHER
    
    def _parse_prices(self, outcome_prices: str) -> tuple[float, float]:
        """Parse YES/NO prices from outcome string"""
        try:
            if not outcome_prices:
                return 0.5, 0.5
            
            # Format: "[0.65, 0.35]" or similar
            prices = outcome_prices.strip("[]").split(",")
            if len(prices) >= 2:
                yes_price = float(prices[0].strip())
                no_price = float(prices[1].strip())
                return yes_price, no_price
            elif len(prices) == 1:
                yes_price = float(prices[0].strip())
                return yes_price, 1 - yes_price
        except:
            pass
        return 0.5, 0.5
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string"""
        if not dt_str:
            return None
        try:
            # Try ISO format
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except:
            try:
                # Try timestamp
                return datetime.fromtimestamp(float(dt_str))
            except:
                return None


# Singleton instance
_client: Optional[PolymarketClient] = None


async def get_polymarket_client() -> PolymarketClient:
    """Get or create polymarket client"""
    global _client
    if _client is None:
        _client = PolymarketClient()
        await _client.__aenter__()
    return _client
