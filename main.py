
import os
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo

# إعدادات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# Telegram API
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
def send_message(text):
    requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text})

# Redis
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Bitvavo API
bitvavo = Bitvavo({
    'APIKEY': API_KEY,
    'APISECRET': API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# دالة جلب السعر
def fetch_price(symbol):
    try:
        response = bitvavo.tickerPrice({'market': symbol})
        return float(response['price'])
    except:
        return None

# أمر الملخص
def summary():
    msg = "📊 العملات المُراقَبة:\n"
    for symbol in r.keys():
        symbol = symbol
        data = r.hgetall(symbol)
        bought = float(data['bought'])
        high = float(data['high'])
        current = fetch_price(symbol)
        change = ((current - bought) / bought) * 100
        msg += f"{symbol}: حالياً {current:.4f} | ربح/خسارة: {change:.2f}%"
    send_message(msg)

# Flask Webhook
app = Flask(__name__)

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {}).get("text", "")

    if not message:
        return "No message", 200

    # أوامر خاصة
    if "يرجى مسح الذاكرة" in message:
        r.flushall()
        send_message("🧹 تم مسح ذاكرة أبو الهول بنجاح.")
        return "ذاكرة مسحت", 200

    if message == "الملخص":
        summary()
        return "ملخص أرسل", 200

    # قنص عملة
    if "-EUR" in message:
        symbol = message.strip().split()[0]
        price = fetch_price(symbol)
        if price:
            r.hset(symbol, mapping={"bought": price, "high": price})
            send_message(f"📈 تمت مراقبة {symbol} عند سعر {price:.4f}")
        else:
            send_message(f"❌ فشل في جلب السعر لـ {symbol}")
        return "عملة سُجلت", 200

    return "تم الاستلام", 200

# تشغيل السيرفر
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
