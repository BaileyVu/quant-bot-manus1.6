from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, timezone

class Candle(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_completed: bool = True
    
    @field_validator("timestamp", mode="after")
    @classmethod
    def validate_timestamp(cls, v):
        if v.tzinfo is None or v.tzinfo != timezone.utc:
            raise ValueError("Timestamp must be UTC")
        return v
        
    @field_validator("high", mode="after")
    @classmethod
    def validate_high(cls, v, info):
        # In Pydantic v2, validation of fields depends on definition order.
        # It's better to use model_validator for cross-field validation.
        return v
        
    @field_validator("low", mode="after")
    @classmethod
    def validate_low(cls, v, info):
        return v
        
    @field_validator("volume", mode="after")
    @classmethod
    def validate_volume(cls, v):
        if v < 0:
            raise ValueError("Volume must be non-negative")
        return v
        
    @model_validator(mode="after")
    def validate_prices(self):
        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise ValueError("High must be >= open, close, and low")
        if self.low > self.open or self.low > self.close or self.low > self.high:
            raise ValueError("Low must be <= open, close, and high")
        return self
