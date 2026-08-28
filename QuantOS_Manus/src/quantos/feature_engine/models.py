from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any

class FeatureVector(BaseModel):
    """
    Represents a deterministic set of calculated features for a specific symbol at a specific timestamp.
    """
    symbol: str
    timestamp: datetime
    version: str = Field(default="1.0")
    features: Dict[str, float]
    
    def has_missing_values(self) -> bool:
        """
        Check if any feature value is missing (None or NaN).
        """
        import math
        for value in self.features.values():
            if value is None or math.isnan(value):
                return True
        return False
