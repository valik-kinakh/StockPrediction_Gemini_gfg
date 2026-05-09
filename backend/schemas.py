from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy GBM-only schema (still used by /api/predict for backward compatibility).
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    amount: float = Field(..., gt=0)
    horizonDays: int = Field(..., ge=1, le=252)


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


# ---------------------------------------------------------------------------
# New ML-forecasting schemas.
# ---------------------------------------------------------------------------


class ForecastRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    horizon: int = Field(..., ge=1, le=252)


class ModelProjection(BaseModel):
    name: str
    available: bool
    error: Optional[str] = None
    projection: List[ProjectionPoint] = []
    seconds: float = 0.0


class ForecastResponse(BaseModel):
    ticker: str
    horizon: int
    currentPrice: float
    asOf: str
    history: List[HistoryPoint]
    models: List[ModelProjection]


class OptionsContextSignal(BaseModel):
    available: bool
    reason: Optional[str] = None
    sigmaForecast: Optional[float] = None
    iv30: Optional[float] = None
    ratio: Optional[float] = None
    regime: Optional[str] = None  # 'overpriced' | 'underpriced' | 'fair'
    tradeIdea: Optional[str] = None
    modelUsed: Optional[str] = None


class OptionsContextResponse(ForecastResponse):
    optionsContext: OptionsContextSignal


class BacktestMetric(BaseModel):
    model: str
    horizon: int
    mape: float
    directionalAccuracy: float
    originCount: int


class BacktestResponse(BaseModel):
    ticker: str
    available: bool
    reason: Optional[str] = None
    metrics: List[BacktestMetric] = []
    generatedAt: Optional[str] = None


# ---------------------------------------------------------------------------
# Options Lab schemas.
# ---------------------------------------------------------------------------


class OptionsLabRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    horizon: int = Field(..., ge=1, le=252)


class ScanRequest(BaseModel):
    watchlist: str = Field(..., min_length=1, max_length=64)
    horizon: int = Field(..., ge=1, le=252)


# Loose-typed pass-through responses: the backend produces nested dicts that
# vary per card. `Dict[str, Any]` keeps the OpenAPI schema honest without
# forcing us to mirror every internal field name. The frontend treats them
# as opaque JSON.


class OptionsLabResponse(BaseModel):
    ticker: str
    horizon: int
    currentPrice: float
    asOf: str
    market: Dict[str, Any]
    earnings: Dict[str, Any]
    greeks: Dict[str, Any]
    pl: Dict[str, Any]


class ScanResponse(BaseModel):
    watchlist: str
    horizon: int
    asOf: str
    rows: List[Dict[str, Any]]
    elapsedSeconds: Optional[float] = None
    errors: Optional[List[str]] = None
