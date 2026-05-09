"""
Centralized data fetching with caching and rate limiting.
- yfinance: options, prices, earnings dates, volume
- Finnhub: company news (ticker-specific, no filtering needed)
"""

import yfinance as yf
import time
import threading
import urllib.request
import json as _json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NewsItem:
    """A single news article."""
    title: str
    summary: str
    publisher: str
    link: str
    published: str  # human-readable date string
    timestamp: int  # unix timestamp
    related: str  # related ticker symbols


@dataclass
class NewsContext:
    """News and events context for a ticker."""
    news: List[NewsItem]
    next_earnings_date: Optional[str]  # YYYY-MM-DD or None
    days_to_earnings: Optional[int]
    news_volume_flag: bool  # True if unusually high news count
    caution_keywords_found: List[str]  # e.g. ["lawsuit", "FDA", "merger"]
    news_source: str  # "finnhub" or "yfinance"


@dataclass
class OptionData:
    """Holds all fetched data for a single ticker."""
    ticker_symbol: str
    underlying_price: float
    option_chains: Dict  # {exp_date_str: OptionChain}
    exp_dates: List[str]
    price_history_3mo: object  # DataFrame
    price_history_1yr: Optional[object] = None  # DataFrame
    avg_volume_30d: float = 0.0
    earnings_dates: Optional[object] = None  # DataFrame
    news_context: Optional[NewsContext] = None
    fetch_timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class DataCache:
    """Thread-safe TTL cache for OptionData."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, OptionData] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, ticker: str) -> Optional[OptionData]:
        with self._lock:
            data = self._cache.get(ticker)
            if data and (time.time() - data.fetch_timestamp) < self._ttl:
                return data
            if data:
                del self._cache[ticker]
            return None

    def put(self, ticker: str, data: OptionData) -> None:
        with self._lock:
            self._cache[ticker] = data

    def invalidate(self, ticker: str) -> None:
        with self._lock:
            self._cache.pop(ticker, None)


# ---------------------------------------------------------------------------
# Caution keywords (shared between news providers)
# ---------------------------------------------------------------------------

# Two-tier caution system:
# - HEADLINE_KEYWORDS: scanned in title only (high confidence)
# - SUMMARY_KEYWORDS: scanned in title + summary (require whole-word match)

HEADLINE_KEYWORDS = [
    "lawsuit", "sued", "litigation", "settlement", "fraud",
    "fda approval", "fda rejected", "fda ruling", "clinical trial",
    "merger", "acquisition", "takeover", "buyout",
    "sec investigation", "sec probe", "doj investigation", "subpoena",
    "bankruptcy", "delisted",
    "data breach", "cybersecurity breach", "hacked",
    "mass layoff", "restructuring plan",
    "ceo resign", "cfo resign", "ceo fired", "ceo step",
    "guidance cut", "profit warning", "misses estimates",
    "short seller report", "short report",
    "stock offering", "dilution", "reverse split",
]

SUMMARY_KEYWORDS = [
    "lawsuit", "fraud", "indictment",
    "fda reject", "clinical trial fail",
    "merger agreement", "acquisition deal",
    "sec charges", "doj charges",
    "bankruptcy filing",
    "data breach",
    "guidance lower", "profit warning",
]


# ---------------------------------------------------------------------------
# Finnhub news fetcher
# ---------------------------------------------------------------------------

def _fetch_finnhub_news(ticker_symbol: str, api_key: str,
                        days_back: int = 7) -> List[NewsItem]:
    """Fetch company news from Finnhub. Returns ticker-specific news only."""
    today = datetime.today().date()
    from_date = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = today.strftime('%Y-%m-%d')

    url = (
        f"https://finnhub.io/api/v1/company-news"
        f"?symbol={ticker_symbol}"
        f"&from={from_date}&to={to_date}"
        f"&token={api_key}"
    )

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'VolAnalyzer/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = _json.loads(resp.read().decode('utf-8'))
    except Exception:
        return []

    if not isinstance(raw, list):
        return []

    items = []
    for article in raw[:15]:  # cap at 15 articles
        headline = article.get('headline', '')
        if not headline:
            continue

        ts = article.get('datetime', 0)
        try:
            pub_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else ''
        except Exception:
            pub_str = ''

        items.append(NewsItem(
            title=headline,
            summary=article.get('summary', ''),
            publisher=article.get('source', ''),
            link=article.get('url', ''),
            published=pub_str,
            timestamp=int(ts),
            related=article.get('related', ''),
        ))

    return items


# ---------------------------------------------------------------------------
# yfinance news fetcher (fallback)
# ---------------------------------------------------------------------------

def _fetch_yfinance_news(stock, ticker_symbol: str) -> List[NewsItem]:
    """Fetch news from yfinance with ticker-relevance filtering."""
    # Build search terms
    search_terms = [ticker_symbol.lower()]
    try:
        info = stock.info
        company_name = info.get('shortName') or info.get('longName') or ''
        if company_name:
            search_terms.append(company_name.lower())
            for word in company_name.replace(',', '').replace('.', '').split():
                w = word.lower().strip()
                if len(w) >= 4 and w not in ('inc', 'corp', 'ltd', 'llc', 'group',
                                               'holdings', 'company', 'technologies',
                                               'international'):
                    search_terms.append(w)
    except Exception:
        pass

    items = []
    try:
        raw_news = stock.news
        if not raw_news:
            return []

        for article in raw_news[:20]:
            title = ""
            description = ""
            publisher = ""
            link = ""
            pub_ts = 0
            pub_date = ""

            if isinstance(article, dict):
                content = article.get('content', article)
                if isinstance(content, dict):
                    title = content.get('title', '')
                    description = content.get('description', '') or content.get('summary', '') or ''
                    pub_info = content.get('provider', {})
                    publisher = pub_info.get('displayName', '') if isinstance(pub_info, dict) else str(pub_info)
                    link = content.get('canonicalUrl', {})
                    if isinstance(link, dict):
                        link = link.get('url', '')
                    pub_date = content.get('pubDate', '')
                else:
                    title = article.get('title', '')
                    description = article.get('description', '') or ''
                    publisher = article.get('publisher', '')
                    link = article.get('link', '')
                    pub_ts = article.get('providerPublishTime', 0)

            if not title:
                continue

            # Filter: only keep articles mentioning this ticker/company
            text_to_search = (title + ' ' + description).lower()
            if not any(term in text_to_search for term in search_terms):
                continue

            if pub_ts and isinstance(pub_ts, (int, float)) and pub_ts > 0:
                try:
                    pub_str = datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pub_str = ""
            elif pub_date:
                pub_str = str(pub_date)[:16]
            else:
                pub_str = ""

            items.append(NewsItem(
                title=title,
                summary=description[:200] if description else '',
                publisher=publisher,
                link=link if isinstance(link, str) else "",
                published=pub_str,
                timestamp=int(pub_ts) if isinstance(pub_ts, (int, float)) else 0,
                related='',
            ))
    except Exception:
        pass

    return items


# ---------------------------------------------------------------------------
# Main DataProvider
# ---------------------------------------------------------------------------

class DataProvider:
    """Centralized data fetching with rate limiting and caching.

    News: uses Finnhub if API key provided, falls back to yfinance.
    Everything else: always yfinance.
    """

    def __init__(self, cache_ttl: int = 300, finnhub_api_key: Optional[str] = None):
        self._cache = DataCache(cache_ttl)
        self._rate_limiter = threading.Semaphore(3)
        self._finnhub_key = finnhub_api_key

    @property
    def finnhub_api_key(self) -> Optional[str]:
        return self._finnhub_key

    @finnhub_api_key.setter
    def finnhub_api_key(self, key: Optional[str]):
        self._finnhub_key = key

    def fetch_all(self, ticker_symbol: str, include_earnings: bool = False,
                  include_1yr_history: bool = False,
                  include_news: bool = False) -> OptionData:
        """Fetch all data needed for a ticker. Uses cache if fresh."""
        ticker_symbol = ticker_symbol.strip().upper()
        cached = self._cache.get(ticker_symbol)
        if cached is not None:
            if include_earnings and cached.earnings_dates is None:
                pass
            elif include_1yr_history and cached.price_history_1yr is None:
                pass
            elif include_news and cached.news_context is None:
                pass
            else:
                return cached

        with self._rate_limiter:
            return self._fetch_fresh(ticker_symbol, include_earnings,
                                     include_1yr_history, include_news)

    def _fetch_fresh(self, ticker_symbol: str, include_earnings: bool,
                     include_1yr_history: bool,
                     include_news: bool = False) -> OptionData:
        """Fetch all data from yfinance + optionally Finnhub for news."""
        from calculator import filter_dates

        stock = yf.Ticker(ticker_symbol)

        # Validate has options
        if not stock.options or len(stock.options) == 0:
            raise ValueError(f"No options found for '{ticker_symbol}'.")

        # Filter expiration dates
        exp_dates = filter_dates(list(stock.options))

        # Fetch option chains
        option_chains = {}
        for exp_date in exp_dates:
            option_chains[exp_date] = stock.option_chain(exp_date)

        # Get current price
        underlying_price = self._get_price(stock)

        # Fetch price history (yfinance)
        price_history_3mo = stock.history(period='3mo')
        if price_history_3mo.empty:
            raise ValueError(f"No price history for '{ticker_symbol}'.")

        # 30-day average volume
        vol_series = price_history_3mo['Volume'].rolling(30).mean().dropna()
        avg_volume_30d = float(vol_series.iloc[-1]) if not vol_series.empty else 0.0

        # Optional: 1 year history for IV rank (yfinance)
        price_history_1yr = None
        if include_1yr_history:
            price_history_1yr = stock.history(period='1y')

        # Optional: earnings dates (yfinance)
        earnings_dates = None
        if include_earnings:
            earnings_dates = self._fetch_earnings_dates(stock)

        # Optional: news (Finnhub primary, yfinance fallback) + earnings context (yfinance)
        news_context = None
        if include_news:
            news_context = self._fetch_news_context(stock, ticker_symbol, earnings_dates)

        data = OptionData(
            ticker_symbol=ticker_symbol,
            underlying_price=underlying_price,
            option_chains=option_chains,
            exp_dates=exp_dates,
            price_history_3mo=price_history_3mo,
            price_history_1yr=price_history_1yr,
            avg_volume_30d=avg_volume_30d,
            earnings_dates=earnings_dates,
            news_context=news_context,
            fetch_timestamp=time.time(),
        )
        self._cache.put(ticker_symbol, data)
        return data

    def _get_price(self, stock) -> float:
        """Get current stock price with fallbacks."""
        try:
            hist = stock.history(period='1d')
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception:
            pass
        try:
            info = stock.info
            price = info.get('regularMarketPrice') or info.get('currentPrice')
            if price:
                return float(price)
        except Exception:
            pass
        raise ValueError("Unable to retrieve stock price.")

    def _fetch_earnings_dates(self, stock, limit: int = 12) -> Optional[object]:
        """Fetch historical earnings dates from yfinance."""
        try:
            dates = stock.get_earnings_dates(limit=limit)
            if dates is not None and not dates.empty:
                return dates
        except Exception:
            pass
        return None

    def _fetch_news_context(self, stock, ticker_symbol: str,
                            earnings_dates_df) -> Optional[NewsContext]:
        """Build news context: Finnhub for news, yfinance for earnings dates.

        Strategy:
        1. If Finnhub API key is set → use Finnhub (native ticker filter)
        2. Otherwise → fall back to yfinance (keyword-based filtering)
        3. Earnings date always from yfinance
        4. Caution keywords scanned regardless of source
        """
        # --- Fetch news ---
        news_source = "yfinance"
        news_items = []

        if self._finnhub_key:
            news_items = _fetch_finnhub_news(ticker_symbol, self._finnhub_key)
            if news_items:
                news_source = "finnhub"

        # Fallback to yfinance if Finnhub returned nothing or no key
        if not news_items:
            news_items = _fetch_yfinance_news(stock, ticker_symbol)
            news_source = "yfinance"

        # --- Scan for caution keywords (two-tier) ---
        caution_found = []
        for item in news_items:
            title_lower = item.title.lower()
            # Tier 1: headline keywords (high confidence, title only)
            for kw in HEADLINE_KEYWORDS:
                if kw in title_lower and kw not in caution_found:
                    caution_found.append(kw)
            # Tier 2: summary keywords (require match in summary too)
            summary_lower = item.summary.lower() if item.summary else ''
            for kw in SUMMARY_KEYWORDS:
                if kw in summary_lower and kw not in caution_found:
                    caution_found.append(kw)

        # --- Next earnings date (yfinance) ---
        next_earnings = None
        days_to_earnings = None
        today = datetime.today().date()

        try:
            if earnings_dates_df is not None and not earnings_dates_df.empty:
                for idx in earnings_dates_df.index:
                    d = idx.date() if hasattr(idx, 'date') else idx
                    if d >= today:
                        next_earnings = d.strftime('%Y-%m-%d')
                        days_to_earnings = (d - today).days
                        break
        except Exception:
            pass

        # Also try stock.calendar for next earnings
        if next_earnings is None:
            try:
                cal = stock.calendar
                if cal is not None and isinstance(cal, dict):
                    earn_date = cal.get('Earnings Date')
                    if earn_date:
                        if isinstance(earn_date, list) and len(earn_date) > 0:
                            d = earn_date[0]
                        else:
                            d = earn_date
                        if hasattr(d, 'date'):
                            d = d.date()
                        if d >= today:
                            next_earnings = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
                            days_to_earnings = (d - today).days
            except Exception:
                pass

        # News volume flag
        news_volume_flag = len(news_items) >= 5

        return NewsContext(
            news=news_items,
            next_earnings_date=next_earnings,
            days_to_earnings=days_to_earnings,
            news_volume_flag=news_volume_flag,
            caution_keywords_found=caution_found,
            news_source=news_source,
        )
