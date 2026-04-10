"""
Shared HTTP session for yfinance.

Yahoo Finance aggressively rate-limits vanilla `requests` clients (HTTP 429
"Too Many Requests. Rate limited. Try after a while."). Using a curl_cffi
session that impersonates a real Chrome browser bypasses Cloudflare's bot
detection and is the standard workaround as of 2025.

Import `session` from this module and pass it into `yf.Ticker(ticker, session=session)`.
"""

from curl_cffi import requests as curl_requests

# A single module-level session is reused across all backend requests so we
# look like one consistent browser to Yahoo rather than a burst of new clients.
session = curl_requests.Session(impersonate="chrome")
