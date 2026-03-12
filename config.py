"""
Configuration module for Chrysalis-μ Autonomous Economic Agent.
Centralizes all configurable parameters with type safety and validation.
"""

from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class BlockchainConfig:
    """Blockchain network and contract configuration."""
    NETWORK: str = "polygon"
    RPC_ENDPOINT: str = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    CHAIN_ID: int = 137
    FLASHBOTS_RPC: str = "https://rpc.flashbots.net"
    
    # Contract addresses (Polygon)
    UNISWAP_V3_FACTORY: str = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    USDC_ADDRESS: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    USDT_ADDRESS: str = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    CHAINLINK_USDC_USD: str = "0xfE4A8cc5b5B2366C1B58Bea3858e81843581b2F7"
    CHAINLINK_USDT_USD: str = "0x0A6513e40db6EB1b165753AD52E80663aeA50545"
    
    # Position parameters
    FEE_TIER: int = 100  # 0.01%
    POSITION_RANGE_BPS: int = 10  # ±0.1%
    MIN_LIQUIDITY: float = 100.0  # $100 minimum
    
@dataclass
class SafetyConfig:
    """Safety thresholds and emergency conditions."""
    DEPEG_THRESHOLD_BPS: int = 30  # 0.3%
    GAS_THRESHOLD_GWEI: int = 50  # Max gas price
    MIN_PROFIT_MARGIN_BPS: int = 20  # 0.2% min profit margin
    HEALTH_SCORE_THRESHOLD: int = 60  # Trigger emergency below this
    
    # Emergency response delays (seconds)
    EMERGENCY_RESPONSE_DELAY: int = 60
    TX_CONFIRMATION_TIMEOUT: int = 300
    
@dataclass
class MonitoringConfig:
    """Monitoring and execution intervals."""
    MAIN_LOOP_INTERVAL_MINUTES: int = 15
    HEALTH_CHECK_INTERVAL_MINUTES: int = 60
    GAS_CHECK_INTERVAL_MINUTES: int = 5
    
    # Data retention
    SNAPSHOT_RETENTION_DAYS: int = 30
    TRANSACTION_RETENTION_DAYS: int = 90
    
@dataclass
class FirebaseConfig:
    """Firebase configuration for state persistence."""
    PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "chrysalis-mu")
    COLLECTION_PREFIX: str = "chrysalis_agents"
    AGENT_ID: str = os.getenv("AGENT_ID", "primary_agent_001")
    
@dataclass
class AgentConfig:
    """Agent behavior and optimization parameters."""
    AUTO_COMPOUND_THRESHOLD_USD: float = 5.0
    MAX_REBALANCE_FREQUENCY_HOURS: int = 24
    MIN_POSITION_VALUE_USD: float = 50.0
    
    # Cross-DEX monitoring
    MONITORED_DEXS: list = None
    
    def __post_init__(self):
        if self.MONITORED_DEXS is None:
            self.MONITORED_DEXS = [
                "uniswap_v3",
                "sushiswap",
                "quickswap"
            ]

# Global configuration instances
BLOCKCHAIN = BlockchainConfig()
SAFETY = SafetyConfig()
MONITORING = MonitoringConfig()
FIREBASE = FirebaseConfig()
AGENT = AgentConfig()

def validate_config() -> tuple[bool, Optional[str]]:
    """Validate all configuration parameters."""
    try:
        # Check required environment variables
        required_env_vars = ["PRIVATE_KEY_ENCRYPTED", "FIREBASE_CREDENTIALS_JSON"]
        missing = [var for var in required_env_vars if not os.getenv(var)]
        if missing:
            return False, f"Missing env vars: {missing}"
        
        # Validate numeric ranges
        if SAFETY.DEPEG_THRESHOLD_BPS <= 0 or SAFETY.DEPEG_THRESHOLD_BPS > 1000:
            return False, "DEPEG_THRESHOLD_BPS must be between 1 and 1000"
        
        if SAFETY.GAS_THRESHOLD_GWEI <= 0 or SAFETY.GAS_THRESHOLD_GWEI > 1000:
            return False, "GAS_THRESHOLD_GWEI must be between 1 and 1000"
        
        if AGENT.AUTO_COMPOUND_THRESHOLD_USD < 0:
            return False, "AUTO_COMPOUND_THRESHOLD_USD must be positive"
        
        return True, None
        
    except Exception as e:
        return False, f"Config validation error: {str(e)}"