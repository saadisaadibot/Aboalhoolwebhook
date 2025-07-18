import os
import redis
import requests
from flask import Flask, request
from threading import Thread
from time import sleep
from bitvavo import Bitvavo

# إعداد المفاتيح من البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("API_KEY")
BITVAVO_API_SECRET = os.getenv("API_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

# إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET
})

# إعداد Redis
r = redis.Redis.from_url(REDIS_URL)

# إعداد Flask
app = Flask(__name__)

# إرسال رسالة تيليغرام
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=data)

# شراء العملة
def buy_coin(symbol):
    try:
        response = bitvavo.placeOrder({
            'market': symbol,
            'side': 'buy',
            'orderType': 'market',
            'amount': '10'  # يورو وليس كمية العملات
        })
        send_message(f"✅ تم شراء {symbol} بـ 10 يورو.")
        price = float(fetch_price(symbol))
        r.hset(symbol, mapping={"bought": price, "high": price})
    except Exception as e:
        send_message(f"❌ فشل الشراء: {e}")

# بيع العملة
def sell_coin(symbol):
    try:
        balance = bitvavo.getBalance({symbol.replace("-EUR", ""): ""})
        amount = next((b["available"] for b in balance if b["symbol"] == symbol.replace("-EUR", "")), None)
        if amount and float(amount) > 0:
            bitvavo.placeOrder({
                'market': symbol,
                'side': 'sell',
                'orderType': 'market',
                'amount': amount
            })
            send_message(f"📤 تم بيع {symbol} بالكامل.")
        r.delete(symbol)
    except Exception as e:
        send_message(f"❌ فشل البيع: {e}")

# جلب سعر العملة
def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        response = requests.get(url)
        if response.status_code == 200:
            return float(response.json()["price"])
    except:
        return None

# مراقبة العملات
def monitor():
    while True:
        for symbol in r.keys():
            symbol = symbol.decode()
            data = r.hgetall(symbol)
            bought = float(data[b"bought"].decode())
            high = float(data[b"high"].decode())
            current = fetch_price(symbol)
            if not current:
                continue
            if current > high:
                high = current
                r.hset(symbol, "high", high)
            change_from_buy = ((current - bought) / bought) * 100
            drop_from_peak = ((high - current) / high) * 100

            if change_from_buy >= 3 and drop_from_peak >= 1.5:
                sell_coin(symbol)
            elif change_from_buy <= -3:
                sell_coin(symbol)
        sleep(30)

# أمر الطوارئ
def emergency_sell_all():
    for symbol in r.keys():
        symbol = symbol.decode()
        sell_coin(symbol)

# أمر الملخص
def summary():
    msg = "📊 العملات المراقبة:
"
    for symbol in r.keys():
        symbol = symbol.decode()
        data = r.hgetall(symbol)
        bought = float(data[b"bought"].decode())
        high = float(data[b"high"].decode())
        current = fetch_price(symbol)
        change = ((current - bought) / bought) * 100 if current else 0
        msg += f"{symbol}: حاليًا {current:.2f}€ | تم الشراء {bought:.2f}€ | ربح/خسارة {change:.2f}%
"
    send_message(msg)

# استقبال Webhook
@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != BOT_TOKEN:
        return "Unauthorized", 403

    data = request.get_json()
    if not data:
        return "No data", 400

    msg = data.get("message", {}).get("text", "")
    if not msg:
        return "No message", 400

    if msg.strip().lower() in ["#emergency", "طوارئ"]:
        send_message("🚨 تم تفعيل وضع الطوارئ.")
        emergency_sell_all()
    elif msg.strip() == "الملخص":
        summary()
    elif "-EUR" in msg:
        symbol = msg.strip().upper()
        buy_coin(symbol)

    return "OK", 200

# بدء المراقبة
Thread(target=monitor).start()

# تشغيل السيرفر
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
