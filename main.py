import os
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo
from threading import Thread
from time import sleep

# إعداد المفاتيح
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("API_KEY")
BITVAVO_API_SECRET = os.getenv("API_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2',
    'WSURL': 'wss://ws.bitvavo.com/v2/',
    'ACCESSWINDOW': 10000,
    'DEBUGGING': False
})

r = redis.from_url(REDIS_URL)

app = Flask(__name__)

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def monitor_price(symbol, buy_price):
    try:
        symbol = symbol.upper()
        peak_price = buy_price
        while True:
            price = float(bitvavo.tickerPrice({'market': symbol})['price'])
            change_percent = ((price - buy_price) / buy_price) * 100
            peak_change = ((peak_price - buy_price) / buy_price) * 100

            if price > peak_price:
                peak_price = price

            if peak_change >= 3 and ((peak_price - price) / peak_price) >= 0.015:
                bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': '10'})
                r.delete(symbol)
                send_message(f"🚨 بيع {symbol} - هبط 1.5% من القمة بعد ربح")
                break

            elif change_percent <= -3:
                bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': '10'})
                r.delete(symbol)
                send_message(f"📉 بيع {symbol} بخسارة -3%")
                break

            sleep(10)
    except Exception as e:
        send_message(f"خطأ في المراقبة: {e}")

@app.route('/webhook/<token>', methods=["POST"])
def webhook(token):
    data = request.get_json()
    try:
        text = data["message"]["text"]
        if text.startswith("/"):
            return "OK"

        if "طوارئ" in text or "#EMERGENCY" in text:
            keys = list(r.keys())
            for symbol in keys:
                try:
                    bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': '10'})
                    r.delete(symbol)
                except Exception as e:
                    send_message(f"خطأ بيع {symbol}: {e}")
            send_message("🚨 تم بيع كامل المحفظة بسبب الطوارئ")
            return "OK"

        if "الملخص" in text:
            keys = r.keys()
            if not keys:
                send_message("لا توجد عملات تحت المراقبة حالياً.")
            else:
                summary = "📊 العملات تحت المراقبة:\n"
                for k in keys:
                    summary += f"• {k.decode()} - {r.get(k).decode()} EUR\n"
                send_message(summary)
            return "OK"

        if "-EUR" in text:
            symbol = text.strip().upper()
            if not r.exists(symbol):
                price = float(bitvavo.tickerPrice({'market': symbol})['price'])
                r.set(symbol, price)
                send_message(f"🟢 مراقبة {symbol} - السعر الحالي: {price} EUR")

                # شراء فوري
                bitvavo.placeOrder(symbol, 'buy', 'market', {'amount': '10'})

                # بدء المراقبة
                Thread(target=monitor_price, args=(symbol, price)).start()
        return "200"
    except Exception as e:
        send_message(f"فشل الشراء: {e}")
        return "error"
