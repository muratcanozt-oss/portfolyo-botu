import json
import os
import time
import schedule
import requests
import yfinance as yf
from datetime import datetime

# Config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
PORTFOLIO_FILE = "portfolio.json"

# ── Telegram ──────────────────────────────────────────────
def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

# ── Portföy ───────────────────────────────────────────────
def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"assets": []}
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── Fiyat Çekme ───────────────────────────────────────────
def get_price(symbol, asset_type):
    try:
        if asset_type == "crypto":
            # CoinGecko API (ücretsiz)
            coin_ids = {
                "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
                "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
                "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
                "MATIC": "matic-network", "LINK": "chainlink", "LTC": "litecoin",
                "ATOM": "cosmos", "UNI": "uniswap", "TRX": "tron",
            }
            coin_id = coin_ids.get(symbol.upper(), symbol.lower())
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,try"
            r = requests.get(url, timeout=10)
            data = r.json()
            if coin_id in data:
                return data[coin_id]["try"], data[coin_id]["usd"], "TRY"
            return None, None, None

        elif asset_type in ("bist", "us_stock"):
            if asset_type == "bist":
                ticker = symbol + ".IS"
            else:
                ticker = symbol
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if hist.empty:
                return None, None, None
            price = hist["Close"].iloc[-1]
            currency = "TRY" if asset_type == "bist" else "USD"
            return price, price, currency

    except Exception as e:
        print(f"Fiyat çekme hatası {symbol}: {e}")
        return None, None, None

def get_usd_try():
    try:
        ticker = yf.Ticker("USDTRY=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return hist["Close"].iloc[-1]
    except:
        pass
    return 38.0  # fallback

# ── RSI Hesaplama ─────────────────────────────────────────
def calculate_rsi(symbol, asset_type, period=14):
    try:
        if asset_type == "crypto":
            coin_ids = {
                "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
                "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
            }
            coin_id = coin_ids.get(symbol.upper(), symbol.lower())
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=try&days=30"
            r = requests.get(url, timeout=10)
            prices = [p[1] for p in r.json().get("prices", [])]
        else:
            ticker = symbol + ".IS" if asset_type == "bist" else symbol
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            prices = hist["Close"].tolist()

        if len(prices) < period + 1:
            return None

        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)
    except:
        return None

# ── Analiz ve Bildirim ────────────────────────────────────
def analyze_and_notify():
    portfolio = load_portfolio()
    assets = portfolio.get("assets", [])

    if not assets:
        send_message("⚠️ Portföyünde henüz varlık yok. /ekle komutuyla ekleyebilirsin.")
        return

    usd_try = get_usd_try()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    messages = [f"📊 <b>Portföy Raporu</b> — {now}\n💱 USD/TRY: {usd_try:.2f}\n"]

    total_cost_try = 0
    total_value_try = 0

    for asset in assets:
        symbol = asset["symbol"]
        atype = asset["type"]
        quantity = asset["quantity"]
        buy_price = asset["buy_price"]  # TRY cinsinden
        buy_currency = asset.get("buy_currency", "TRY")

        price_try, price_usd, currency = get_price(symbol, atype)

        if price_try is None:
            messages.append(f"❌ {symbol}: Fiyat alınamadı")
            continue

        # Maliyet TRY'ye çevir
        if buy_currency == "USD":
            cost_try = buy_price * asset.get("buy_usd_try", usd_try) * quantity
        else:
            cost_try = buy_price * quantity

        current_value_try = price_try * quantity
        pnl_try = current_value_try - cost_try
        pnl_pct = (pnl_try / cost_try) * 100 if cost_try > 0 else 0

        total_cost_try += cost_try
        total_value_try += current_value_try

        # RSI
        rsi = calculate_rsi(symbol, atype)
        rsi_text = ""
        rsi_alert = ""
        if rsi:
            rsi_text = f" | RSI: {rsi}"
            if rsi >= 70:
                rsi_alert = " 🔴 AŞIRI ALIM"
            elif rsi <= 30:
                rsi_alert = " 🟢 AŞIRI SATIM"

        emoji = "📈" if pnl_pct >= 0 else "📉"
        sign = "+" if pnl_pct >= 0 else ""

        if currency == "USD":
            price_display = f"${price_usd:.2f} ({price_try:.2f}₺)"
        else:
            price_display = f"{price_try:.2f}₺"

        line = (
            f"{emoji} <b>{symbol}</b>: {price_display}\n"
            f"   {sign}{pnl_pct:.1f}% | {sign}{pnl_try:,.0f}₺{rsi_text}{rsi_alert}\n"
        )
        messages.append(line)

        # Özel uyarılar
        if pnl_pct <= -10:
            messages.append(f"   ⚠️ Stop-loss uyarısı! -%10 eşiği geçildi.\n")
        elif pnl_pct >= 20:
            messages.append(f"   🎯 Hedef uyarısı! +%20 seviyesine ulaştı.\n")

    # Genel özet
    total_pnl = total_value_try - total_cost_try
    total_pct = (total_pnl / total_cost_try) * 100 if total_cost_try > 0 else 0
    sign = "+" if total_pct >= 0 else ""

    messages.append(
        f"\n💼 <b>Toplam Portföy</b>\n"
        f"   Maliyet: {total_cost_try:,.0f}₺\n"
        f"   Güncel: {total_value_try:,.0f}₺\n"
        f"   Kâr/Zarar: {sign}{total_pnl:,.0f}₺ ({sign}{total_pct:.1f}%)\n"
        f"   2x Hedef: {total_cost_try*2:,.0f}₺ ({((total_value_try/(total_cost_try*2))*100):.1f}% tamamlandı)"
    )

    send_message("\n".join(messages))

# ── Zamanlayıcı ───────────────────────────────────────────
def run_scheduler():
    # Her sabah 09:00 ve akşam 19:00'da rapor gönder
    schedule.every().day.at("09:00").do(analyze_and_notify)
    schedule.every().day.at("19:00").do(analyze_and_notify)

    send_message("🚀 Portföy botu başlatıldı! Her gün 09:00 ve 19:00'da rapor alacaksın.")
    analyze_and_notify()  # Başlangıçta bir kere çalıştır

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
