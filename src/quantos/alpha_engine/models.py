from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class AlphaDecision(BaseModel):
    """
    Represents a single production trading decision produced by the Alpha Engine.
    """
    symbol: str
    timestamp: datetime
    strategy_version: str
    model_version: str
    feature_version: str
    signal: Signal
    model_score: Optional[float] = None
    reason: str = Field(default="Standard prediction")
    
class ModelArtifactMetadata(BaseModel):
    """
    Metadata required for reproducible future inference.
    """
    model_version: str
    strategy_version: str
    feature_version: str
    target_definition: str
    prediction_horizon_minutes: int
    training_start: datetime
    training_end: datetime
    validation_start: datetime
    validation_end: datetime
    symbols: List[str]
    features: List[str]
    training_metrics: Dict[str, float]
    validation_metrics: Dict[str, float]
    created_at: datetime = Field(default_factory=datetime.utcnow)
