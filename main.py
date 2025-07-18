import os
import redis
import requests
from flask import Flask, request
from bitvavo import Bitvavo
from threading import Thread
from time import sleep

# إعداد المفاتيح من env
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

# إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# Redis
r = redis.Redis.from_url(REDIS_URL)

# Flask
app = Flask(__name__)

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
    except:
        pass

def fetch_price(symbol):
    try:
        res = bitvavo.tickerPrice({'market': symbol})
        return float(res['price'])
    except:
        return None

def buy(symbol, amount_eur):
    try:
        response = bitvavo.placeOrder({
            'market': symbol,
            'side': 'buy',
            'orderType': 'market',
            'amountQuote': str(amount_eur)
        })
        print("✅ عملية شراء:", response)
        return fetch_price(symbol)
    except Exception as e:
        print("❌ فشل الشراء:", e)
        return None

def sell(symbol, amount):
    try:
        response = bitvavo.placeOrder({
            'market': symbol,
            'side': 'sell',
            'orderType': 'market',
            'amount': str(amount)
        })
        print("🟥 عملية بيع:", response)
        return response
    except Exception as e:
        print("❌ فشل البيع:", e)
        return None

def get_balance(symbol):
    try:
        balances = bitvavo.balance({})
        for b in balances:
            if b["symbol"] == symbol.split("-")[0]:
                return float(b["available"])
        return 0
    except Exception as e:
        print("⚠️ خطأ بجلب الرصيد:", e)
        return 0

def monitor(symbol, buy_price):
    peak = buy_price
    while True:
        sleep(15)
        current = fetch_price(symbol)
        if current is None:
            continue
        if current > peak:
            peak = current
        change = (current - buy_price) / buy_price * 100
        drop_from_peak = (peak - current) / peak * 100
        if change <= -3:
            amt = get_balance(symbol)
            if amt > 0:
                sell(symbol, amt)
            r.delete(symbol)
            break
        elif change >= 3 and drop_from_peak >= 1.5:
            amt = get_balance(symbol)
            if amt > 0:
                sell(symbol, amt)
            r.delete(symbol)
            break

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.json
    if not data or "message" not in data:
        return "no data", 200
    text = data["message"].get("text", "")
    if not text:
        return "no text", 200

    print("📥 رسالة واردة:", text)

    if "طوارئ" in text or "#EMERGENCY" in text:
        keys = r.keys()
        for key in keys:
            symbol = key.decode()
            amt = get_balance(symbol)
            if amt > 0:
                sell(symbol, amt)
            r.delete(symbol)
        send_message("🚨 تم تنفيذ أمر بيع المحفظة بالكامل")
        return "done", 200

    if text == "الملخص":
        msg = "📊 العملات المتابعة:"
        for key in r.keys():
            k = key.decode()
            v = r.get(k).decode()
            msg += f"- {k} بسعر {v} يورو
"
        send_message(msg if msg.strip() != "📊 العملات المتابعة:" else "لا يوجد عملات تحت المراقبة حالياً.")
        return "done", 200

    if "-EUR" in text:
        symbol = text.strip()
        if r.exists(symbol):
            send_message(f"⚠️ {symbol} تحت المراقبة بالفعل")
            return "already exists", 200
        price = buy(symbol, 10)
        if price:
            r.set(symbol, price)
            send_message(f"👁‍🗨 بدأنا بمراقبة {symbol} بسعر {price} يورو")
            Thread(target=monitor, args=(symbol, price)).start()
    return "ok", 200

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)