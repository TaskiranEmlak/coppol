"""
Configuration management for Polymarket Copy Trade Bot
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Trading Mode
    trading_mode: Literal["paper", "real"] = Field(default="paper")
    
    # Paper Trade Settings
    paper_initial_balance: float = Field(default=1000.0)
    
    # Real Trade Settings
    real_initial_balance: float = Field(default=10.0)
    
    # Polymarket Authentication
    polymarket_private_key: str = Field(default="")
    polymarket_api_key: str = Field(default="")
    polymarket_api_secret: str = Field(default="")
    polymarket_passphrase: str = Field(default="")
    
    # Network Settings
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com/")
    
    # Bot Settings
    refresh_interval: int = Field(default=10, description="Seconds between whale scans")
    max_whales: int = Field(default=20)
    min_whale_score: float = Field(default=50.0)
    max_trade_percent: float = Field(default=50.0)
    
    # Dashboard Settings
    dashboard_host: str = Field(default="127.0.0.1")
    dashboard_port: int = Field(default=8000)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
