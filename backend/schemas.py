from typing import List, Optional
from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    amount: float = Field(..., gt=0)
    horizonDays: int = Field(..., ge=5, le=252)


class HistoryPoint(BaseModel):
    date: str
    price: float


class ProjectionPoint(BaseModel):
    date: str
    p5: float
    p50: float
    p95: float


class DollarReturn(BaseModel):
    low: float
    expected: float
    high: float


class Recommendation(BaseModel):
    label: str
    color: str
    rationale: str


class VolatilitySignals(BaseModel):
    available: bool
    reason: Optional[str] = None
    avgVolume: Optional[bool] = None
    iv30Rv30: Optional[bool] = None
    tsSlope045: Optional[bool] = None
    expectedMove: Optional[str] = None


class PredictResponse(BaseModel):
    ticker: str
    currentPrice: float
    muAnnual: float
    sigmaAnnual: float
    horizonDays: int
    history: List[HistoryPoint]
    projection: List[ProjectionPoint]
    dollarReturn: DollarReturn
    expectedReturnPct: float
    recommendation: Recommendation
    volatilitySignals: VolatilitySignals
