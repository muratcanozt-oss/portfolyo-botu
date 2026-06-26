#!/usr/bin/env python3
"""
Portföy yönetim aracı.
Kullanım:
  python manage.py ekle THYAO bist 100 45.50
  python manage.py ekle BTC crypto 0.05 2800000
  python manage.py ekle AAPL us_stock 10 185.00 USD
  python manage.py listele
  python manage.py sil THYAO
  python manage.py islem THYAO al 50 42.00
  python manage.py islem THYAO sat 30 55.00
"""

import json
import sys
import os
from datetime import datetime

PORTFOLIO_FILE = "portfolio.json"
HISTORY_FILE = "transactions.json"

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"assets": []}
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        return json.load(f)

def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def ekle(symbol, atype, quantity, price, currency="TRY"):
    portfolio = load_portfolio()
    symbol = symbol.upper()

    # Zaten var mı?
    for a in portfolio["assets"]:
        if a["symbol"] == symbol:
            print(f"⚠️  {symbol} zaten portföyde. Güncelleme için 'islem' komutunu kullan.")
            return

    asset = {
        "symbol": symbol,
        "type": atype,
        "quantity": float(quantity),
        "buy_price": float(price),
        "buy_currency": currency.upper(),
        "added_at": datetime.now().isoformat()
    }
    portfolio["assets"].append(asset)
    save_portfolio(portfolio)
    print(f"✅ {symbol} eklendi: {quantity} adet, alış fiyatı {price} {currency}")

def sil(symbol):
    portfolio = load_portfolio()
    symbol = symbol.upper()
    before = len(portfolio["assets"])
    portfolio["assets"] = [a for a in portfolio["assets"] if a["symbol"] != symbol]
    if len(portfolio["assets"]) < before:
        save_portfolio(portfolio)
        print(f"🗑️  {symbol} portföyden silindi.")
    else:
        print(f"❌ {symbol} bulunamadı.")

def listele():
    portfolio = load_portfolio()
    assets = portfolio.get("assets", [])
    if not assets:
        print("Portföy boş.")
        return
    print(f"\n{'Sembol':<10} {'Tip':<12} {'Miktar':<12} {'Alış Fiyatı':<15} {'Para'}")
    print("-" * 60)
    for a in assets:
        print(f"{a['symbol']:<10} {a['type']:<12} {a['quantity']:<12} {a['buy_price']:<15} {a.get('buy_currency','TRY')}")

def islem(symbol, direction, quantity, price, currency="TRY"):
    portfolio = load_portfolio()
    symbol = symbol.upper()
    direction = direction.lower()
    quantity = float(quantity)
    price = float(price)

    history = load_history()
    history.append({
        "symbol": symbol,
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "currency": currency,
        "date": datetime.now().isoformat()
    })
    save_history(history)

    # Portföyü güncelle
    found = False
    for a in portfolio["assets"]:
        if a["symbol"] == symbol:
            found = True
            if direction == "al":
                # Ortalama maliyet hesapla
                old_qty = a["quantity"]
                new_qty = old_qty + quantity
                a["buy_price"] = ((a["buy_price"] * old_qty) + (price * quantity)) / new_qty
                a["quantity"] = new_qty
                print(f"✅ {symbol} alım eklendi. Yeni miktar: {new_qty}, Ort. maliyet: {a['buy_price']:.4f}")
            elif direction == "sat":
                if quantity > a["quantity"]:
                    print(f"❌ Hata: Satmak istediğin miktar ({quantity}) eldeki miktardan ({a['quantity']}) fazla.")
                    return
                a["quantity"] -= quantity
                if a["quantity"] <= 0:
                    portfolio["assets"] = [x for x in portfolio["assets"] if x["symbol"] != symbol]
                    print(f"✅ {symbol} tamamen satıldı ve portföyden çıkarıldı.")
                else:
                    print(f"✅ {symbol} satım kaydedildi. Kalan miktar: {a['quantity']}")
            break

    if not found:
        if direction == "al":
            ekle(symbol, "unknown", quantity, price, currency)
            print("⚠️  Tip bilinmiyor, lütfen manuel düzenle.")
        else:
            print(f"❌ {symbol} portföyde bulunamadı.")
        return

    save_portfolio(portfolio)

def gecmis():
    history = load_history()
    if not history:
        print("İşlem geçmişi boş.")
        return
    print(f"\n{'Tarih':<22} {'Sembol':<10} {'Yön':<6} {'Miktar':<12} {'Fiyat'}")
    print("-" * 65)
    for t in history[-20:]:  # Son 20 işlem
        date = t["date"][:16].replace("T", " ")
        print(f"{date:<22} {t['symbol']:<10} {t['direction']:<6} {t['quantity']:<12} {t['price']} {t.get('currency','TRY')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "ekle" and len(sys.argv) >= 6:
        currency = sys.argv[6] if len(sys.argv) > 6 else "TRY"
        ekle(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], currency)
    elif cmd == "sil" and len(sys.argv) >= 3:
        sil(sys.argv[2])
    elif cmd == "listele":
        listele()
    elif cmd == "islem" and len(sys.argv) >= 6:
        currency = sys.argv[6] if len(sys.argv) > 6 else "TRY"
        islem(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], currency)
    elif cmd == "gecmis":
        gecmis()
    else:
        print(__doc__)
