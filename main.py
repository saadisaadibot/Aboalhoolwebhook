
import os
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo
from threading import Thread
from time import sleep

# إعداد المفاتيح من env
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

# إعداد Redis
r = redis.from_url(REDIS_URL)

# إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET
})

# إرسال رسالة إلى تيليغرام
def send_message(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": CHAT_ID,
        "text": text
    })

# جلب السعر الحالي
def fetch_price(symbol):
    try:
        res = bitvavo.tickerPrice({'market': symbol})
        return float(res['price'])
    except:
        return None

# تنفيذ أمر شراء
def buy_coin(symbol):
    try:
        balance = float(bitvavo.balance({'currency': 'EUR'})[0]['available'])
        if balance < 10:
            send_message("❌ لا يوجد رصيد كافي للشراء.")
            return

        res = bitvavo.placeOrder(symbol, 'buy', 'market', {
            'amount': round(10 / fetch_price(symbol), 5)
        })

        current = fetch_price(symbol)
        data = {
            'bought': current,
            'high': current
        }
        r.hset(symbol, mapping=data)
        send_message(f"✅ تم شراء {symbol} بسعر {current}€")
    except Exception as e:
        send_message(f"❌ فشل الشراء: {e}")

# تنفيذ أمر بيع
def sell_coin(symbol):
    try:
        data = r.hgetall(symbol)
        if not data:
            return
        amount = round(10 / float(data[b'bought'].decode()), 5)
        bitvavo.placeOrder(symbol, 'sell', 'market', {
            'amount': amount
        })
        send_message(f"🚨 تم بيع {symbol}")
        r.delete(symbol)
    except Exception as e:
        send_message(f"❌ فشل البيع: {e}")

# منطق المراقبة
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
                r.hset(symbol, "high", current)
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
    msg = "📊 العملات المراقبة:\n"
for symbol in r.keys():
    symbol = symbol.decode()
    data = r.hgetall(symbol)
    bought = float(data[b"bought"].decode())
    high = float(data[b"high"].decode())
    current = fetch_price(symbol)
    change = ((current - bought) / bought) * 100
    msg += f"{symbol}: حاليا {current:.2f}€ | تم الشراء {bought:.2f}€ | ربح/خسارة {change:.2f}%\n"

send_message(msg)
# إعداد Flask
app = Flask(__name__)

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True) or {}
    print("✅ تم استقبال رسالة Webhook:", data)
    message = data.get("message", {}).get("text", "")

    if not message:
        return "No message", 200

    if "طوارئ" in message or "#EMERGENCY" in message:
        emergency_sell_all()
    elif "الملخص" in message:
        summary()
    elif "-EUR" in message:
        symbol = extract_symbol(message)
        if symbol:
            buy_coin(symbol)

    return "ok", 200

    return "Ignored", 200

# تشغيل المراقبة في Thread
Thread(target=monitor).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
