"""Quick portfolio P&L check for WSE positions."""
import yfinance as yf

portfolio = {
    "KRU.WA": {"shares": 22, "avg": 444.10},
    "XTB.WA": {"shares": 79, "avg": 87.05},
    "CBF.WA": {"shares": 44, "avg": 184.21},
    "DIA.WA": {"shares": 49, "avg": 163.20},
    "ACP.WA": {"shares": 39, "avg": 179.26},
    "PKO.WA": {"shares": 56, "avg": 93.87},
    "MBR.WA": {"shares": 10, "avg": 337.70},
    "SNT.WA": {"shares": 2,  "avg": 271.80},
}

print(f"{'Ticker':<10} {'Buy':>8} {'Now':>8} {'Gain%':>8} {'Cost PLN':>10} {'Value PLN':>10} {'P&L PLN':>10}")
print("-" * 70)
total_cost = 0
total_value = 0

for ticker, p in portfolio.items():
    try:
        price = yf.Ticker(ticker).fast_info.last_price
        gain_pct = (price - p["avg"]) / p["avg"] * 100
        current_val = price * p["shares"]
        cost = p["avg"] * p["shares"]
        pnl = current_val - cost
        total_cost += cost
        total_value += current_val
        print(f"{ticker:<10} {p['avg']:>8.2f} {price:>8.2f} {gain_pct:>+8.1f}% {cost:>10.0f} {current_val:>10.0f} {pnl:>+10.0f}")
    except Exception as e:
        print(f"{ticker}: ERROR {e}")

print("-" * 70)
total_pnl = total_value - total_cost
print(f"{'TOTAL WSE':<10} {'':>8} {'':>8} {(total_pnl/total_cost*100):>+8.1f}% {total_cost:>10.0f} {total_value:>10.0f} {total_pnl:>+10.0f}")
