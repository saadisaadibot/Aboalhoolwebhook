import os
import time
import threading
import redis
import requests
from flask import Flask, request
from bitvavo import Bitvavo

# إعدادات
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")

bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

r = redis.Redis(host='redis', port=6379, decode_responses=True)
app = Flask(__name__)

# إرسال رسالة تيليغرام
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=data)

# جلب السعر الحالي
def fetch_price(symbol):
    try:
        data = bitvavo.tickerPrice({'market': symbol})
        return float(data["price"])
    except:
        return None

# شراء عملة بقيمة 10 يورو
def buy(symbol):
    try:
        bitvavo.placeOrder(symbol, 'buy', 'market', {'amount': 10})
        return True
    except Exception as e:
        send_message(f"❌ فشل الشراء: {e}")
        return False

# بيع كامل الكمية
def sell(symbol):
    try:
        balance = bitvavo.balance({'symbol': symbol.split("-")[0]})
        amount = float(balance[0]['available'])
        bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': amount})
        return True
    except Exception as e:
        send_message(f"❌ فشل البيع: {e}")
        return False

# تابع المراقبة
def monitor():
    while True:
        try:
            for symbol in r.keys():
                if not isinstance(symbol, str):
                    continue
                data = r.hgetall(symbol)
                if "bought" not in data or "high" not in data:
                    continue
                bought = float(data["bought"])
                high = float(data["high"])
                current = fetch_price(symbol)
                if not current:
                    continue
                change = ((current - bought) / bought) * 100
                if current > high:
                    r.hset(symbol, "high", current)
                elif high >= bought * 1.03 and current <= high * 0.985:
                    sell(symbol)
                    send_message(f"📉 تم البيع (Trail Stop) لـ {symbol}")
                    r.delete(symbol)
                elif current <= bought * 0.97:
                    sell(symbol)
                    send_message(f"🔻 تم البيع بخسارة لـ {symbol}")
                    r.delete(symbol)
        except Exception as e:
            send_message(f"💥 خطأ في المراقبة: {e}")
        time.sleep(15)

# أمر الملخص
def summary():
    msg = "📊 العملات المُراقَبة:\n"
    for symbol in r.keys():
        try:
            if not isinstance(symbol, str):
                continue
            data = r.hgetall(symbol)
            bought = float(data["bought"])
            current = fetch_price(symbol)
            change = ((current - bought) / bought) * 100
            msg += f"{symbol}: حالياً {current:.2f}€ | تم الشراء {bought:.2f}€ | ربح/خسارة {change:.2f}%\n"
        except:
            continue
    send_message(msg)

# مسح الذاكرة يدويًا (بشرط وجود عبارة واضحة)
def clear_memory():
    for key in r.keys():
        r.delete(key)
    send_message("🧹 تم مسح جميع العملات من الذاكرة.")

# Webhook من صقر
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {}).get("text", "")
    if not message:
        return "No message", 200

    if "طوارئ" in message or "#EMERGENCY" in message:
        for symbol in r.keys():
            sell(symbol)
            r.delete(symbol)
        send_message("🚨 تم بيع المحفظة بالكامل (وضع الطوارئ)")
        return "Emergency handled", 200

    if "يرجى مسح الذاكرة" in message:
        clear_memory()
        return "Memory cleared", 200

    if "الملخص" in message:
        summary()
        return "Summary sent", 200

    if "-EUR" in message:
        symbol = message.strip()
        price = fetch_price(symbol)
        if not price:
            send_message(f"❌ فشل في جلب السعر لـ {symbol}")
            return "No price", 200
        bought = buy(symbol)
        if bought:
            r.hset(symbol, mapping={"bought": price, "high": price})
            send_message(f"✅ بدأ مراقبة {symbol} عند {price:.2f}€")
        return "Buy order handled", 200

    return "Message ignored", 200

# تشغيل المراقبة
threading.Thread(target=monitor, daemon=True).start()

# إشعار بدء البوت
send_message("🤖 تم تشغيل بوت أبو الهول بنجاح!")

# تشغيل Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
