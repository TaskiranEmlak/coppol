"""
Database setup and session management
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum
import os

# Ensure data directory exists
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'copytrade.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TradeSide(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class MarketCategory(str, enum.Enum):
    POLITICS = "politics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    ENTERTAINMENT = "entertainment"
    SCIENCE = "science"
    OTHER = "other"


# Database Models
class WhaleDB(Base):
    """Tracked whale traders"""
    __tablename__ = "whales"
    
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(42), unique=True, index=True)
    name = Column(String(100), nullable=True)  # Optional display name
    
    # Scoring metrics
    score = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    roi_30d = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    max_drawdown = Column(Float, default=0.0)
    consistency = Column(Float, default=0.0)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_trade_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeDB(Base):
    """All trades (paper and real)"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String(36), unique=True, index=True)  # UUID
    
    # Trade info
    is_paper = Column(Boolean, default=True)
    whale_address = Column(String(42), index=True)
    market_id = Column(String(100), index=True)
    market_question = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    
    # Position
    side = Column(SQLEnum(TradeSide))
    amount = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    
    # Results
    status = Column(SQLEnum(TradeStatus), default=TradeStatus.OPEN)
    profit = Column(Float, nullable=True)
    
    # Decision info
    whale_score_at_entry = Column(Float, nullable=True)
    consensus_count = Column(Integer, default=1)
    decision_reason = Column(Text, nullable=True)
    
    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)


class BalanceHistoryDB(Base):
    """Balance history for tracking performance"""
    __tablename__ = "balance_history"
    
    id = Column(Integer, primary_key=True, index=True)
    is_paper = Column(Boolean, default=True)
    balance = Column(Float)
    pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)


class MarketDB(Base):
    """Cached market information"""
    __tablename__ = "markets"
    
    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(String(100), unique=True, index=True)
    question = Column(Text)
    category = Column(SQLEnum(MarketCategory), default=MarketCategory.OTHER)
    
    # Current state
    yes_price = Column(Float, default=0.5)
    no_price = Column(Float, default=0.5)
    volume = Column(Float, default=0.0)
    liquidity = Column(Float, default=0.0)
    
    # Resolution
    is_resolved = Column(Boolean, default=False)
    outcome = Column(String(10), nullable=True)  # YES, NO, or NULL
    
    # Timestamps
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== Helper Functions ====================

def save_trade(trade_data: dict) -> None:
    """Save a trade to database"""
    db = SessionLocal()
    try:
        trade = TradeDB(
            trade_id=trade_data.get("id"),
            is_paper=trade_data.get("is_paper", True),
            whale_address=trade_data.get("whale_address"),
            market_id=trade_data.get("market_id"),
            market_question=trade_data.get("market_question"),
            category=trade_data.get("category"),
            side=TradeSide(trade_data.get("side", "YES")),
            amount=trade_data.get("amount", 0),
            entry_price=trade_data.get("entry_price", 0.5),
            exit_price=trade_data.get("exit_price"),
            status=TradeStatus(trade_data.get("status", "OPEN")),
            profit=trade_data.get("profit"),
            whale_score_at_entry=trade_data.get("whale_score_at_entry"),
            consensus_count=trade_data.get("consensus_count", 1),
            decision_reason=trade_data.get("decision_reason"),
            opened_at=trade_data.get("opened_at", datetime.utcnow()),
            closed_at=trade_data.get("closed_at")
        )
        db.add(trade)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def update_trade(trade_id: str, updates: dict) -> None:
    """Update a trade in database"""
    db = SessionLocal()
    try:
        trade = db.query(TradeDB).filter(TradeDB.trade_id == trade_id).first()
        if trade:
            for key, value in updates.items():
                if hasattr(trade, key):
                    setattr(trade, key, value)
            db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_open_trades(is_paper: bool = True) -> list:
    """Get all open trades"""
    db = SessionLocal()
    try:
        trades = db.query(TradeDB).filter(
            TradeDB.is_paper == is_paper,
            TradeDB.status == TradeStatus.OPEN
        ).all()
        return [
            {
                "id": t.trade_id,
                "whale_address": t.whale_address,
                "market_id": t.market_id,
                "market_question": t.market_question,
                "category": t.category,
                "side": t.side.value,
                "amount": t.amount,
                "entry_price": t.entry_price,
                "whale_score_at_entry": t.whale_score_at_entry,
                "opened_at": t.opened_at
            }
            for t in trades
        ]
    finally:
        db.close()


def get_last_balance(is_paper: bool = True) -> float:
    """Get last recorded balance"""
    db = SessionLocal()
    try:
        record = db.query(BalanceHistoryDB).filter(
            BalanceHistoryDB.is_paper == is_paper
        ).order_by(BalanceHistoryDB.id.desc()).first()
        return record.balance if record else None
    finally:
        db.close()


def save_balance(balance: float, pnl: float, trade_count: int, is_paper: bool = True) -> None:
    """Save balance snapshot"""
    db = SessionLocal()
    try:
        record = BalanceHistoryDB(
            is_paper=is_paper,
            balance=balance,
            pnl=pnl,
            trade_count=trade_count
        )
        db.add(record)
        db.commit()
    finally:
        db.close()

