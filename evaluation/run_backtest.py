"""Run the walk-forward backtest across the watchlist and write artifacts.

Usage (from repo root):

    python evaluation/run_backtest.py
    python evaluation/run_backtest.py --tickers AAPL,MSFT,NVDA --horizons 5,21
    python evaluation/run_backtest.py --no-chronos     # skip the heavy model

Outputs:
    evaluation/output/results.csv     long-format, one row per origin × model × horizon
    evaluation/output/summary.csv     averaged across origins
    evaluation/output/<ticker>_<h>.png   plot per ticker × horizon (matplotlib)

Designed to run in 1–2 hours on a Mac without GPU. Commit `results.csv` and the
PNGs so the demo and the dissertation never depend on running inference live.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from forecasting.evaluator import backtest_ticker, rows_to_dataframe, summarise  # noqa: E402
from forecasting.service import watchlist_tickers  # noqa: E402


OUT_DIR = REPO / "evaluation" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Walk-forward backtest")
    p.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated tickers. Defaults to the watchlist.",
    )
    p.add_argument(
        "--horizons",
        type=str,
        default="5,63",
        help="Comma-separated horizons in trading days (default 5,63).",
    )
    p.add_argument(
        "--n-origins",
        type=int,
        default=12,
        help="Number of walk-forward origins per ticker (default 12).",
    )
    p.add_argument(
        "--no-chronos",
        action="store_true",
        help="Skip Chronos even if installed (fast smoke run).",
    )
    return p.parse_args()


def _maybe_disable_chronos():
    """Monkeypatch is_chronos_available so the backtest skips the heavy model.

    Used for a fast smoke run on a teaching laptop without torch installed.
    """
    from forecasting.models import chronos_model  # type: ignore

    chronos_model._load_pipeline = lambda: None  # type: ignore
    chronos_model.is_chronos_available = lambda: False  # type: ignore


def _plot_ticker(df_ticker: pd.DataFrame, ticker: str, horizon: int):
    try:
        import matplotlib.pyplot as plt  # local import: optional dep
    except ImportError:
        return

    sub = df_ticker[df_ticker["horizon"] == horizon].dropna(subset=["mape"])
    if sub.empty:
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    for model, group in sub.groupby("model"):
        ax.plot(group["origin"], group["mape"], marker="o", label=model)
    ax.set_title(f"{ticker} — MAPE by walk-forward origin (h={horizon})")
    ax.set_ylabel("MAPE")
    ax.set_xlabel("origin date")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{ticker}_{horizon}.png", dpi=120)
    plt.close(fig)


def main():
    args = _parse_args()

    if args.no_chronos:
        _maybe_disable_chronos()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = watchlist_tickers()

    horizons = tuple(int(x) for x in args.horizons.split(",") if x.strip())

    print(f"Backtesting {len(tickers)} tickers × {len(horizons)} horizons × n_origins={args.n_origins}")

    all_rows = []
    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}", flush=True)
        try:
            rows = backtest_ticker(
                ticker, horizons=horizons, n_origins=args.n_origins
            )
            all_rows.extend(rows)
        except Exception as e:  # noqa: BLE001
            print(f"    {ticker}: {type(e).__name__}: {e}")

    df = rows_to_dataframe(all_rows)
    df.to_csv(OUT_DIR / "results.csv", index=False)

    summary = summarise(df)
    summary.to_csv(OUT_DIR / "summary.csv", index=False)

    print("\nSummary (averaged across origins):")
    print(summary.to_string(index=False))

    for ticker in df["ticker"].unique():
        for h in horizons:
            _plot_ticker(df[df["ticker"] == ticker], ticker, h)

    print(f"\nWrote {len(df)} rows to {OUT_DIR}/results.csv")


if __name__ == "__main__":
    main()
