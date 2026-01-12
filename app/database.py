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
