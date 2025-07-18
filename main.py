import os
import time
import threading
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo

# إعداد المتغيرات من البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")

# إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# Redis
r = redis.Redis(host='redis', port=6379, decode_responses=True)

# Flask
app = Flask(__name__)

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def fetch_price(symbol):
    try:
        data = bitvavo.tickerPrice({'market': symbol})
        return float(data["price"])
    except:
        return None

def buy(symbol):
    try:
        bitvavo.placeOrder(symbol, 'buy', 'market', {'amount': 10})
        return True
    except Exception as e:
        send_message(f"❌ فشل الشراء: {e}")
        return False

def sell(symbol):
    try:
        balance = bitvavo.balance({'symbol': symbol.split("-")[0]})
        amount = float(balance[0]['available'])
        bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': amount})
        return True
    except Exception as e:
        send_message(f"❌ فشل البيع: {e}")
        return False

def clear_memory():
    try:
        for key in r.keys():
            r.delete(key)
        send_message("🧹 تم مسح جميع العملات من الذاكرة.")
    except Exception as e:
        send_message(f"⚠️ فشل في مسح الذاكرة عند التشغيل: {e}")

def monitor():
    while True:
        try:
            for symbol in r.keys():
                if r.type(symbol) != 'hash':
                    continue  # تجاهل المفاتيح الغريبة
                data = r.hgetall(symbol)
                if "bought" not in data or "high" not in data:
                    continue
                bought = float(data["bought"])
                high = float(data["high"])
                current = fetch_price(symbol)
                if not current:
                    continue
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
            print(f"خطأ في المراقبة: {e}")
        time.sleep(15)

def summary():
    msg = "📊 العملات المُراقبة:\n"
    for symbol in r.keys():
        if r.type(symbol) != 'hash':
            continue
        data = r.hgetall(symbol)
        try:
            bought = float(data["bought"])
            current = fetch_price(symbol)
            change = ((current - bought) / bought) * 100
            msg += f"{symbol}: حالياً {current:.2f}€ | تم الشراء {bought:.2f}€ | ربح/خسارة {change:.2f}%\n"
        except:
            continue
    send_message(msg if msg != "📊 العملات المُراقبة:\n" else "لا توجد عملات تحت المراقبة حالياً.")

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        message = data.get("message", {}).get("text", "")
        if not message:
            return "No text", 200

        if "طوارئ" in message or "#EMERGENCY" in message:
            for symbol in r.keys():
                if r.type(symbol) == 'hash':
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
            symbol = message.strip().split()[0]
            price = fetch_price(symbol)
            if not price:
                send_message(f"❌ فشل في جلب السعر لـ {symbol}")
                return "No price", 200
            if buy(symbol):
                r.hset(symbol, mapping={"bought": price, "high": price})
                send_message(f"✅ بدأ مراقبة {symbol} عند {price:.2f}€")
            return "Buy order handled", 200

        return "Message ignored", 200

    except Exception as e:
        send_message(f"💥 خطأ غير متوقع: {e}")
        return "Server Error", 500

# 🔁 بداية التشغيل
clear_memory()
threading.Thread(target=monitor, daemon=True).start()
send_message("🤖 تم تشغيل بوت أبو الهول بنجاح!")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
