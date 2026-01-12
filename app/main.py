"""
Polymarket Copy Trade Bot - Main Application

FastAPI server with:
- REST API for dashboard
- WebSocket for real-time updates
- Background task for whale monitoring
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import get_settings
from app.database import init_db
from app.api.polymarket import PolymarketClient, get_polymarket_client
from app.brain.scorer import TraderScorer
from app.brain.ranker import TraderRanker
from app.brain.decider import CopyDecider
from app.engine.paper_trader import PaperTrader
from app.models.trade import TradeSignal, TradeSide, CopyDecision

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Global state
settings = get_settings()
scorer = TraderScorer()
ranker = TraderRanker(scorer)
decider = CopyDecider(scorer)
paper_trader = PaperTrader()

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# Background task handle
monitor_task: Optional[asyncio.Task] = None


async def broadcast(message: dict):
    """Send message to all connected WebSocket clients"""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except:
            disconnected.append(connection)
    
    for conn in disconnected:
        active_connections.remove(conn)


async def load_whales():
    """Load initial whale data from Polymarket"""
    try:
        client = await get_polymarket_client()
        traders = await client.get_leaderboard(limit=settings.max_whales)
        
        if traders:
            ranker.add_traders(traders)
            logger.info(f"Loaded {len(traders)} whales from leaderboard")
            
            # Score all traders
            ranker.update_scores()
            
            summary = ranker.get_rankings_summary()
            logger.info(
                f"Whale Summary: {summary['hot_count']} hot, "
                f"{summary['warm_count']} warm, {summary['cold_count']} cold"
            )
        else:
            logger.warning("No whales loaded from leaderboard")
            
    except Exception as e:
        logger.error(f"Error loading whales: {e}")


async def monitor_whales():
    """Background task to monitor whale activity"""
    logger.info("Starting whale monitor...")
    
    client = await get_polymarket_client()
    
    while True:
        try:
            # Get hot whale addresses
            hot_whales = ranker.get_hot_traders()
            if not hot_whales:
                logger.debug("No hot whales to monitor")
                await asyncio.sleep(settings.refresh_interval)
                continue
            
            addresses = [w.address for w in hot_whales]
            
            # Detect recent trades
            logger.info(f"🔍 Scanning {len(addresses)} whales for new trades...")
            await broadcast({"type": "scanning", "count": len(addresses)})
            signals = await client.detect_whale_trades(addresses, since_minutes=5)
            
            if not signals:
                logger.info("... No new trades found.")
            else:
                logger.info(f"!!! Found {len(signals)} new signals!")
            
            for signal in signals:
                whale = ranker.get_trader(signal.whale_address)
                if not whale:
                    continue
                
                # Make copy decision
                decision = decider.decide(
                    signal=signal,
                    whale=whale,
                    balance=paper_trader.balance
                )
                
                if decision.should_copy:
                    # Execute paper trade
                    trade = paper_trader.execute_trade(signal, decision)
                    
                    if trade:
                        # Register position with decider
                        decider.register_position(trade.market_id, trade.id)
                        
                        # Broadcast to dashboard
                        await broadcast({
                            "type": "new_trade",
                            "data": {
                                "trade_id": trade.id,
                                "market": trade.market_question or trade.market_id[:30],
                                "side": trade.side.value,
                                "amount": trade.amount,
                                "whale": whale.name or whale.address[:10],
                                "whale_score": whale.score,
                                "reason": decision.reason
                            }
                        })
                else:
                    logger.debug(f"Skipped trade: {decision.reason}")
            
            # Broadcast status update
            await broadcast({
                "type": "status_update",
                "data": paper_trader.get_summary()
            })
            
        except Exception as e:
            logger.error(f"Error in whale monitor: {e}")
        
        await asyncio.sleep(settings.refresh_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    global monitor_task
    
    # Startup
    logger.info("🚀 Starting Polymarket Copy Trade Bot...")
    init_db()
    
    # Load initial data
    await load_whales()
    
    # Start background monitor
    monitor_task = asyncio.create_task(monitor_whales())
    
    logger.info(f"📊 Dashboard: http://{settings.dashboard_host}:{settings.dashboard_port}")
    logger.info(f"💰 Mode: {'PAPER' if settings.trading_mode == 'paper' else 'REAL'}")
    logger.info(f"💵 Balance: ${paper_trader.balance:,.2f}")
    
    yield
    
    # Shutdown
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    
    logger.info("👋 Bot stopped")


# Create FastAPI app
app = FastAPI(
    title="Polymarket Copy Trade Bot",
    description="Copy trade yap, para kazan",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ==================== REST API Routes ====================

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve main dashboard"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Dashboard not found</h1>")


@app.get("/api/status")
async def get_status():
    """Get bot status and summary"""
    return {
        "mode": settings.trading_mode,
        "trading": paper_trader.get_summary(),
        "whales": ranker.get_rankings_summary(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/whales")
async def get_whales():
    """Get whale leaderboard"""
    return {
        "whales": ranker.export_leaderboard(),
        "summary": ranker.get_rankings_summary()
    }


@app.get("/api/trades")
async def get_trades(limit: int = 20):
    """Get trade history"""
    return {
        "open_positions": [
            {
                "id": t.id[:8],
                "market": t.market_question or t.market_id[:30],
                "side": t.side.value,
                "amount": t.amount,
                "entry_price": t.entry_price,
                "whale": t.whale_name or t.whale_address[:10]
            }
            for t in paper_trader.open_positions
        ],
        "history": paper_trader.get_recent_trades(limit),
        "stats": paper_trader.get_summary()
    }


@app.get("/api/markets")
async def get_markets(category: Optional[str] = None, limit: int = 50):
    """Get active markets"""
    try:
        client = await get_polymarket_client()
        markets = await client.get_markets(limit=limit, category=category)
        
        # Group by category
        by_category = {}
        for market in markets:
            cat = market.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append({
                "id": market.id,
                "question": market.question[:100],
                "category": cat,
                "yes_price": market.yes_price,
                "no_price": market.no_price,
                "volume_24h": market.volume_24h,
                "liquidity": market.liquidity
            })
        
        return {
            "markets": [m.__dict__ for m in markets[:limit]],
            "by_category": by_category,
            "total": len(markets)
        }
    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balance-history")
async def get_balance_history():
    """Get balance history for charting"""
    return {
        "history": paper_trader.get_balance_history()
    }


@app.post("/api/refresh-whales")
async def refresh_whales():
    """Manually refresh whale data"""
    await load_whales()
    return {"status": "ok", "whales": len(ranker.traders)}


@app.post("/api/simulate")
async def simulate_trade():
    """Simulate a trade for testing"""
    import random
    from uuid import uuid4
    
    # Get a random whale
    whales = ranker.get_top(20)
    if not whales:
        return {"status": "error", "message": "No whales found"}
    
    whale = random.choice(whales)
    
    # Create fake signal
    signal = TradeSignal(
        whale_address=whale.address,
        market_id=f"0x{uuid4()}",
        market_question=f"Test Market: Will Bitcoin hit ${random.randint(50000, 100000)}?",
        category="crypto",
        side=random.choice([TradeSide.YES, TradeSide.NO]),
        amount=random.uniform(100, 5000),
        price=random.uniform(0.3, 0.7),
        detected_at=datetime.utcnow(),
        whale_score=whale.score,
        whale_name=whale.name
    )
    
    # Force decision
    decision = CopyDecision(
        should_copy=True,
        amount=paper_trader.balance * 0.1,
        reason="⚡ TEST SİMÜLASYONU",
        confidence=95,
        consensus_count=1
    )
    
    # Execute
    trade = paper_trader.execute_trade(signal, decision)
    
    if trade:
        decider.register_position(trade.market_id, trade.id)
        await broadcast({
            "type": "new_trade",
            "data": {
                "trade_id": trade.id,
                "market": trade.market_question,
                "side": trade.side.value,
                "amount": trade.amount,
                "whale": whale.name or whale.address[:10],
                "whale_score": whale.score,
                "reason": decision.reason
            }
        })
        return {"status": "ok", "trade": trade.id}
    
    return {"status": "error", "message": "Trade failed"}


@app.post("/api/reset")
async def reset_paper_trading():
    """Reset paper trading"""
    paper_trader.reset()
    decider.clear_cooldowns()
    return {"status": "ok", "balance": paper_trader.balance}


# ==================== WebSocket ====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    logger.info(f"WebSocket connected. Total: {len(active_connections)}")
    
    # Send initial status
    await websocket.send_json({
        "type": "connected",
        "data": {
            "status": paper_trader.get_summary(),
            "whales": ranker.get_rankings_summary()
        }
    })
    
    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "status":
                await websocket.send_json({
                    "type": "status_update",
                    "data": paper_trader.get_summary()
                })
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(active_connections)}")


# ==================== Main Entry Point ====================

def main():
    """Run the application"""
    uvicorn.run(
        "app.main:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
