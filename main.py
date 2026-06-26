cat > /home/claude/portfolio_bot/main.py << 'PYEOF'
import json
import os
import time
import schedule
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
PORTFOLIO_FILE = "portfolio.json"

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"assets": []}
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)

def get_usd_try():
    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=TRY"
        r = requests.get(url, timeout=10)
        return r.json()["rates"]["TRY"]
    except:
        return 38.0

def get_stock_price_usd(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception as e:
        print(f"Hisse fiyat hatasi {symbol}: {e}")
        return None

def get_crypto_price(coingecko_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd,try"
        r = requests.get(url, timeout=10)
        data = r.json()
        if coingecko_id in data:
            return data[coingecko_id]["try"], data[coingecko_id]["usd"]
        return None, None
    except Exception as e:
        print(f"Kripto fiyat hatasi {coingecko_id}: {e}")
        return None, None

def calculate_rsi_from_prices(prices, period=14):
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

def get_rsi(symbol, asset_type, coingecko_id=None):
    try:
        if asset_type == "crypto":
            url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/market_chart?vs_currency=usd&days=30"
            r = requests.get(url, timeout=10)
            prices = [p[1] for p in r.json().get("prices", [])]
            return calculate_rsi_from_prices(prices)
        elif asset_type == "us_stock":
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            prices = [p for p in closes if p is not None]
            return calculate_rsi_from_prices(prices)
    except:
        return None

def get_ai_analysis(portfolio_summary):
    try:
        prompt = f"""Sen deneyimli bir portföy yöneticisisin. Kullanicinin portfoyu asagida.
Hedef: TL bazinda yil sonuna kadar portfoyu 2 katina cikarmak.
Risk profili: Orta-agresif.
Portfoy ozeti:
{portfolio_summary}

Lutfen asagidakileri yap:
1. Mevcut portfoyu kisaca degerlendir (hangi hisseler iyi/kotu gidiyor)
2. 2-3 somut oneri ver: hangi varlik satilabilir, yerine ne alinabilir
3. Guncel piyasa kosullarini dikkate al (AI/teknoloji, kripto trendleri, TL/USD)
4. Maksimum 250 kelime, net ve anlasilir yaz. Turkce yaz."""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        data = response.json()
        return data["content"][0]["text"]
    except Exception as e:
        print(f"AI analiz hatasi: {e}")
        return None

def analyze_and_notify():
    portfolio = load_portfolio()
    assets = portfolio.get("assets", [])

    if not assets:
        send_message("Portfolio bos.")
        return

    usd_try = get_usd_try()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    messages = [f"Portfolio Raporu - {now}\nUSD/TRY: {usd_try:.2f}\n"]

    total_cost_try = 0
    total_value_try = 0
    portfolio_summary_lines = []

    for asset in assets:
        symbol = asset["symbol"]
        atype = asset["type"]
        quantity = asset["quantity"]
        buy_price = asset["buy_price"]
        buy_currency = asset.get("buy_currency", "TRY")
        coingecko_id = asset.get("coingecko_id", symbol.lower())

        if atype == "fund_try":
            cost_try = buy_price * quantity
            total_cost_try += cost_try
            total_value_try += cost_try
            note = asset.get("note", symbol)
            messages.append(f"[FON] {symbol}: {note}\n  {quantity} x {buy_price:.2f}TL = {cost_try:,.0f}TL\n")
            portfolio_summary_lines.append(f"{symbol} (Fon): {cost_try:,.0f}TL deger")
            continue

        price_try = None
        price_usd = None

        if atype == "crypto":
            price_try, price_usd = get_crypto_price(coingecko_id)
        elif atype == "us_stock":
            price_usd = get_stock_price_usd(symbol)
            if price_usd:
                price_try = price_usd * usd_try
        elif atype == "bist":
            price_try_raw = get_stock_price_usd(symbol + ".IS")
            if price_try_raw:
                price_try = price_try_raw
                price_usd = price_try / usd_try

        if price_try is None:
            messages.append(f"[?] {symbol}: Fiyat alinamadi\n")
            continue

        if buy_currency == "USD":
            cost_try = buy_price * usd_try * quantity
        else:
            cost_try = buy_price * quantity

        current_value_try = price_try * quantity
        pnl_try = current_value_try - cost_try
        pnl_pct = (pnl_try / cost_try) * 100 if cost_try > 0 else 0

        total_cost_try += cost_try
        total_value_try += current_value_try

        rsi = get_rsi(symbol, atype, coingecko_id)
        rsi_text = f" | RSI:{rsi}" if rsi else ""
        rsi_alert = ""
        if rsi:
            if rsi >= 70:
                rsi_alert = " ASIRI ALIM"
            elif rsi <= 30:
                rsi_alert = " ASIRI SATIM"

        arrow = "+" if pnl_pct >= 0 else ""
        if atype == "us_stock" and price_usd:
            price_str = f"${price_usd:.2f} ({price_try:.1f}TL)"
        else:
            price_str = f"{price_try:.2f}TL"

        line = f"{'[+]' if pnl_pct >= 0 else '[-]'} {symbol}: {price_str}\n  {arrow}{pnl_pct:.1f}% | {arrow}{pnl_try:,.0f}TL{rsi_text}{rsi_alert}\n"
        messages.append(line)

        portfolio_summary_lines.append(
            f"{symbol} ({atype}): {quantity} adet, maliyet {cost_try:,.0f}TL, guncel {current_value_try:,.0f}TL, {arrow}{pnl_pct:.1f}%, RSI:{rsi}"
        )

        if pnl_pct <= -10:
            messages.append(f"  [UYARI] Stop-loss! -%10 esigi asildi.\n")
        elif pnl_pct >= 20:
            messages.append(f"  [HEDEF] +%20 seviyesine ulasildi!\n")

    total_pnl = total_value_try - total_cost_try
    total_pct = (total_pnl / total_cost_try) * 100 if total_cost_try > 0 else 0
    sign = "+" if total_pct >= 0 else ""
    target = total_cost_try * 2
    progress = (total_value_try / target * 100) if target > 0 else 0

    messages.append(
        f"\nTOPLAM PORTFOY\n"
        f"  Maliyet: {total_cost_try:,.0f}TL\n"
        f"  Guncel: {total_value_try:,.0f}TL\n"
        f"  Kar/Zarar: {sign}{total_pnl:,.0f}TL ({sign}{total_pct:.1f}%)\n"
        f"  2x Hedef: {target:,.0f}TL - %{progress:.1f} tamamlandi"
    )

    send_message("\n".join(messages))

    # AI analizi ayri mesaj olarak gonder
    portfolio_summary = "\n".join(portfolio_summary_lines)
    portfolio_summary += f"\nToplam maliyet: {total_cost_try:,.0f}TL, Guncel deger: {total_value_try:,.0f}TL, Degisim: {sign}{total_pct:.1f}%"

    ai_text = get_ai_analysis(portfolio_summary)
    if ai_text:
        send_message(f"AI ANALIZ VE ONERILER\n\n{ai_text}")

def run_scheduler():
    schedule.every().day.at("09:00").do(analyze_and_notify)
    schedule.every().day.at("19:00").do(analyze_and_notify)

    send_message("Portfoy botu baslatildi! Her gun 09:00 ve 19:00'da rapor alacaksin.")
    analyze_and_notify()

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
PYEOF
echo "OK"
