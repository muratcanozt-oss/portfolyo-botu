cat > /home/claude/portfolio_bot/main.py << 'EOF'
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

# ── USD/TRY kuru ──────────────────────────────────────────
def get_usd_try():
    try:
        ticker = yf.Ticker("USDTRY=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except:
        pass
    return 38.0

# ── Fiyat Çekme ───────────────────────────────────────────
def get_price(symbol, asset_type, coingecko_id=None, usd_try=38.0):
    try:
        if asset_type == "crypto":
            coin_id = coingecko_id or symbol.lower()
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,try"
            r = requests.get(url, timeout=10)
            data = r.json()
            if coin_id in data:
                return data[coin_id]["try"], data[coin_id]["usd"]
            return None, None

        elif asset_type == "bist":
            ticker = symbol + ".IS"
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if hist.empty:
                return None, None
            price_try = float(hist["Close"].iloc[-1])
            return price_try, price_try / usd_try

        elif asset_type == "us_stock":
            stock = yf.Ticker(symbol)
            hist = stock.history(period="2d")
            if hist.empty:
                return None, None
            price_usd = float(hist["Close"].iloc[-1])
            return price_usd * usd_try, price_usd

        elif asset_type == "fund_try":
            return None, None

    except Exception as e:
        print(f"Fiyat çekme hatası {symbol}: {e}")
        return None, None

# ── RSI Hesaplama ─────────────────────────────────────────
def calculate_rsi(symbol, asset_type, coingecko_id=None, period=14):
    try:
        if asset_type == "crypto":
            coin_id = coingecko_id or symbol.lower()
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=try&days=30"
            r = requests.get(url, timeout=10)
            prices = [p[1] for p in r.json().get("prices", [])]
        elif asset_type in ("bist", "us_stock"):
            ticker = symbol + ".IS" if asset_type == "bist" else symbol
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            prices = hist["Close"].tolist()
        else:
            return None

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
        send_message("⚠️ Portföyünde henüz varlık yok.")
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
        buy_price = asset["buy_price"]
        buy_currency = asset.get("buy_currency", "TRY")
        coingecko_id = asset.get("coingecko_id", None)

        # Türk fonları
        if atype == "fund_try":
            cost_try = buy_price * quantity
            total_cost_try += cost_try
            total_value_try += cost_try
            note = asset.get("note", symbol)
            messages.append(
                f"🏦 <b>{symbol}</b>: {note}\n"
                f"   {quantity} adet × {buy_price:.2f}₺ = {cost_try:,.0f}₺\n"
            )
            continue

        price_try, price_usd = get_price(symbol, atype, coingecko_id, usd_try)

        if price_try is None:
            messages.append(f"❌ {symbol}: Fiyat alınamadı\n")
            continue

        # Maliyet TRY'ye çevir
        if buy_currency == "USD":
            cost_try = buy_price * usd_try * quantity
        else:
            cost_try = buy_price * quantity

        current_value_try = price_try * quantity
        pnl_try = current_value_try - cost_try
        pnl_pct = (pnl_try / cost_try) * 100 if cost_try > 0 else 0

        total_cost_try += cost_try
        total_value_try += current_value_try

        # RSI
        rsi = calculate_rsi(symbol, atype, coingecko_id)
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

        if atype == "us_stock" and price_usd:
            price_display = f"${price_usd:.2f} ({price_try:.2f}₺)"
        else:
            price_display = f"{price_try:.2f}₺"

        line = (
            f"{emoji} <b>{symbol}</b>: {price_display}\n"
            f"   {sign}{pnl_pct:.1f}% | {sign}{pnl_try:,.0f}₺{rsi_text}{rsi_alert}\n"
        )
        messages.append(line)

        if pnl_pct <= -10:
            messages.append(f"   ⚠️ Stop-loss uyarısı! -%10 eşiği geçildi.\n")
        elif pnl_pct >= 20:
            messages.append(f"   🎯 Hedef uyarısı! +%20 seviyesine ulaştı.\n")

    # Genel özet
    total_pnl = total_value_try - total_cost_try
    total_pct = (total_pnl / total_cost_try) * 100 if total_cost_try > 0 else 0
    sign = "+" if total_pct >= 0 else ""
    target = total_cost_try * 2
    progress = (total_value_try / target * 100) if target > 0 else 0

    messages.append(
        f"\n💼 <b>Toplam Portföy</b>\n"
        f"   Maliyet: {total_cost_try:,.0f}₺\n"
        f"   Güncel: {total_value_try:,.0f}₺\n"
        f"   Kâr/Zarar: {sign}{total_pnl:,.0f}₺ ({sign}{total_pct:.1f}%)\n"
        f"   🎯 2x Hedef: {target:,.0f}₺ — %{progress:.1f} tamamlandı"
    )

    send_message("\n".join(messages))

# ── Zamanlayıcı ───────────────────────────────────────────
def run_scheduler():
    schedule.every().day.at("09:00").do(analyze_and_notify)
    schedule.every().day.at("19:00").do(analyze_and_notify)

    send_message("🚀 Portföy botu başlatıldı! Her gün 09:00 ve 19:00'da rapor alacaksın.")
    analyze_and_notify()

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
EOF
echo "Hazır"
