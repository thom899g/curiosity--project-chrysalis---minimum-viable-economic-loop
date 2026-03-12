"""
Oracle Monitoring Module - Depeg detection and price validation.
Provides real-time price monitoring from multiple sources with consensus validation.
"""

import logging
import asyncio
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
import time
from web3 import Web3
import requests
from config import BLOCKCHAIN, SAFETY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PriceData:
    """Container for price data from multiple sources."""
    chainlink_usdc: Optional[float] = None
    chainlink_usdt: Optional[float] = None
    dex_usdc_usdt: Optional[float] = None
    dex_timestamp: Optional[float] = None
    confidence_score: float = 0.0
    
    @property
    def chainlink_ratio(self) -> Optional[float]:
        """Calculate USDC/USDT ratio from Chainlink feeds."""
        if self.chainlink_usdc and self.chainlink_usdt and self.chainlink_usdt != 0:
            return self.chainlink_usdc / self.chainlink_usdt
        return None
    
    @property
    def deviation_bps(self) -> Optional[int]:
        """Calculate deviation between Chainlink and DEX in basis points."""
        if self.chainlink_ratio and self.dex_usdc_usdt:
            deviation = abs((self.dex_usdc_usdt / self.chainlink_ratio) - 1) * 10000
            return int(deviation)
        return None

class OracleMonitor:
    """Monitors price feeds for depeg detection and data validation."""
    
    def __init__(self, web3_client: Web3):
        self.web3 = web3_client
        self.last_update = 0
        self.cache_duration = 30  # seconds
        self.cached_data: Optional[PriceData] = None
        
        # Chainlink ABI for price feeds
        self.chainlink_abi = [
            {
                "inputs": [],
                "name": "latestRoundData",
                "outputs": [
                    {"name": "roundId", "type": "uint80"},
                    {"name": "answer", "type": "int256"},
                    {"name": "startedAt", "type": "uint256"},
                    {"name": "updatedAt", "type": "uint256"},
                    {"name": "answeredInRound", "type": "uint80"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Initialize Chainlink contracts
        self.usdc_feed = self.web3.eth.contract(
            address=Web3.to_checksum_address(BLOCKCHAIN.CHAINLINK_USDC_USD),
            abi=self.chainlink_abi
        )
        self.usdt_feed = self.web3.eth.contract(
            address=Web3.to_checksum_address(BLOCKCHAIN.CHAINLINK_USDT_USD),
            abi=self.chainlink_abi
        )
        
    async def get_chainlink_prices(self) -> Tuple[Optional[float], Optional[float]]:
        """Fetch latest prices from Chainlink oracles."""
        try:
            # Get USDC/USD price
            usdc_data = self.usdc_feed.functions.latestRoundData().call()
            usdc_price = usdc_data[1] / 10**8  # Chainlink returns 8 decimals
            
            # Get USDT/USD price
            usdt_data = self.usdt_feed.functions.latestRoundData().call()
            usdt_price = usdt_data[1] / 10**8
            
            # Validate data freshness (within 1 hour)
            current_time = time.time()
            if current_time - usdc_data[3] > 3600 or current_time - usdt_data[3] > 3600:
                logger.warning("Chainlink data stale (older than 1 hour)")
                return None, None
                
            return float(usdc_price), float(usdt_price)
            
        except Exception as e:
            logger.error(f"Chainlink price fetch failed: {str(e)}")
            return None, None
    
    async def get_dex_price(self) -> Tuple[Optional[float], Optional[float]]:
        """Fetch USDC/USDT price from Uniswap V3 pool."""
        try:
            # Uniswap V3 pool address calculation (USDC/USDT 0.01%)
            pool_key = Web3.keccak(
                hexstr=f"{BLOCKCHAIN.USDC_ADDRESS[2:]}{BLOCKCHAIN.USDT_ADDRESS[2:]}000bb8"
            )
            pool_address = Web3.to_checksum_address(
                f"0x{Web3.keccak(hexstr=f'ff{BLOCKCHAIN.UNISWAP_V3_FACTORY[2:]}{pool_key.hex()}a5980742beedc6586e000000')[12:].hex()}"
            )
            
            # Pool ABI for slot0 (contains sqrtPriceX96)
            pool_abi = [
                {
                    "inputs": [],
                    "name": "slot0",
                    "outputs": [
                        {"name": "sqrtPriceX96", "type": "uint160"},
                        {"name": "tick", "type": "int24"},
                        {"name": "observationIndex", "type": "uint16"},
                        {"name": "observationCardinality", "type": "uint16"},
                        {"name": "observationCardinalityNext", "type": "uint16"},
                        {"name": "feeProtocol", "type": "uint8"},
                        {"name": "unlocked", "type": "bool"}
                    ],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            
            pool = self.web3.eth.contract(address=pool_address, abi=pool_abi)
            slot0 = pool.functions.slot0().call()
            sqrt_price = slot0[0]
            
            # Convert sqrtPriceX96 to actual price
            # For USDC (6 decimals) / USDT (6 decimals)
            price = (sqrt_price ** 2) / (2 ** 192)
            
            return float(price), time.time()
            
        except Exception as e:
            logger.error(f"DEX price fetch failed: {str(e)}")
            return None, None
    
    def is_depeg_detected(self, deviation_bps: int) -> bool:
        """Check if price deviation exceeds safety threshold."""
        return deviation_bps > SAFETY.DEPEG_THRESHOLD_BPS
    
    async def get_current_prices(self) -> PriceData:
        """Get current prices from all sources with consensus validation."""
        # Use cache if recent
        current_time = time.time()
        if self.cached_data and (current_time - self.last_update) < self.cache_duration:
            return self.cached_data
        
        # Fetch from all sources in parallel
        tasks = [
            self.get_chainlink_prices(),
            self.get_dex_price()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        price_data = PriceData()
        
        # Process Chainlink results
        if not isinstance(results[0], Exception) and results[0][0] and results[0][1]:
            price_data.chainlink_usdc, price_data.chainlink_usdt = results[0]
        
        # Process DEX results
        if not isinstance(results[1], Exception) and results[1][0]:
            price_data.dex_usdc_usdt, price_data.dex_timestamp = results[1]
        
        # Calculate confidence score (0.0 to 1.0)
        confidence_factors = []
        if price_data.chainlink_usdc and price_data.chainlink_usdt:
            confidence_factors.append(0.4)  # Chainlink available
        if price_data.dex_usdc_usdt:
            confidence_factors.append(0.4)  # DEX available
        if price_data.deviation_bps and price_data.deviation_bps < 10:
            confidence_factors.append(0.2)  # Low deviation
        
        price_data.confidence_score = sum(confidence_factors)
        
        # Cache the result
        self.cached_data = price_data
        self.last_update = current_time
        
        return price_data
    
    async def check_emergency_conditions(self) -> Dict[str, any]:
        """Check all emergency conditions and return status."""
        prices = await self.get_current_prices()
        
        result = {
            "depeg_detected": False,
            "deviation_bps": prices.deviation_bps,
            "confidence_score": prices.confidence_score,
            "timestamp": time.time()
        }
        
        if prices.deviation_bps:
            result["depeg_detected"] = self.is_depeg_detected(prices.deviation_bps)
            
            if result["depeg_detected"]:
                logger.critical(
                    f"DEP