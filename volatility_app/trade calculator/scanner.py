"""
Batch scanning of multiple tickers with thread pool.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Callable


@dataclass
class ScanResult:
    ticker: str
    analysis: Optional[object] = None  # AnalysisResult
    error: Optional[str] = None


DEFAULT_WATCHLISTS = {
    'Mega Cap Tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'],
    'Semiconductors': ['NVDA', 'AMD', 'INTC', 'AVGO', 'QCOM', 'MU', 'MRVL'],
    'Finance': ['JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'SCHW'],
    'Consumer': ['NFLX', 'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'WMT'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'BMY'],
}


def scan_tickers(tickers: List[str], data_provider,
                 include_iv_rank: bool = True,
                 max_workers: int = 3,
                 progress_callback: Optional[Callable] = None) -> List[ScanResult]:
    """Scan multiple tickers in parallel.

    Args:
        tickers: list of ticker symbols
        data_provider: DataProvider instance
        include_iv_rank: whether to compute IV rank/percentile
        max_workers: max concurrent yfinance requests
        progress_callback: called with (completed_count, total_count)
    """
    from calculator import analyze_ticker

    results = []
    completed = 0
    total = len(tickers)

    def process_one(ticker_symbol):
        data = data_provider.fetch_all(
            ticker_symbol,
            include_earnings=False,
            include_1yr_history=include_iv_rank,
        )
        return analyze_ticker(data, include_iv_rank=include_iv_rank)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_one, t.strip().upper()): t.strip().upper()
            for t in tickers if t.strip()
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                analysis = future.result(timeout=30)
                results.append(ScanResult(ticker=ticker, analysis=analysis))
            except Exception as e:
                results.append(ScanResult(ticker=ticker, error=str(e)))

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return results


def sort_results(results: List[ScanResult], sort_key: str = 'iv_rv_ratio',
                 descending: bool = True) -> List[ScanResult]:
    """Sort scan results by a field from AnalysisResult.

    Results with errors are placed at the end.
    """
    def key_func(r):
        if r.analysis is None:
            return float('-inf') if descending else float('inf')
        val = getattr(r.analysis, sort_key, 0)
        return val if val is not None else 0

    return sorted(results, key=key_func, reverse=descending)
