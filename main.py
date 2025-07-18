import os
import json
import threading
import time
import redis
from flask import Flask, request
import requests
from python_bitvavo_api.bitvavo import Bitvavo

app = Flask(__name__)

# إعداد الاتصال ب Redis
redis_url = os.getenv("REDIS_URL")
r = redis.from_url(redis_url)

# إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': os.getenv("BITVAVO_API_KEY"),
    'APISECRET': os.getenv("BITVAVO_API_SECRET")
})

# إعداد Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(text):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

def buy_coin(symbol):
    try:
        response = bitvavo.placeOrder({
            'market': symbol,
            'side': 'buy',
            'orderType': 'market',
            'amount': '10'
        })
        price = float(response['fills'][0]['price'])
        r.hset(symbol, mapping={"buy_price": price, "peak_price": price})
        send_message(f"✅ تم شراء {symbol} بسعر {price}€")
    except Exception as e:
        send_message(f"❌ فشل شراء {symbol}: {e}")

def sell_coin(symbol):
    try:
        balance = float(bitvavo.getBalance({})[symbol.replace("-EUR", "")]['available'])
        if balance > 0:
            response = bitvavo.placeOrder({
                'market': symbol,
                'side': 'sell',
                'orderType': 'market',
                'amount': str(balance)
            })
            r.delete(symbol)
            send_message(f"💸 تم بيع {symbol} بالكامل!")
    except Exception as e:
        send_message(f"❌ فشل بيع {symbol}: {e}")

def monitor_prices():
    while True:
        try:
            for key in r.keys():
                symbol = key.decode()
                data = r.hgetall(symbol)
                buy_price = float(data[b"buy_price"].decode())
                peak_price = float(data[b"peak_price"].decode())

                current_price = float(requests.get(f"https://api.bitvavo.com/v2/ticker/price?market={symbol}").json()["price"])

                if current_price > peak_price:
                    r.hset(symbol, "peak_price", current_price)

                profit_percent = ((current_price - buy_price) / buy_price) * 100
                drop_from_peak = ((peak_price - current_price) / peak_price) * 100

                if profit_percent >= 3 and drop_from_peak >= 1.5:
                    sell_coin(symbol)
                elif profit_percent <= -3:
                    sell_coin(symbol)

            time.sleep(15)
        except:
            time.sleep(10)

@app.route("/", methods=["GET"])
def home():
    return "أبو الهول يعمل 👑"

@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    try:
        data = request.json
        print("✅ Webhook استلم:", data)

        message = data.get("message", {})
        text = message.get("text", "")

        if "يرجى المسح" in text:
            for key in r.keys():
                r.delete(key)
            send_message("🧹 تم مسح الذاكرة بنجاح")

        elif "الملخص" in text:
            summary = ""
            for key in r.keys():
                symbol = key.decode()
                data = r.hgetall(symbol)
                buy_price = float(data[b"buy_price"].decode())
                peak_price = float(data[b"peak_price"].decode())
                current_price = float(requests.get(f"https://api.bitvavo.com/v2/ticker/price?market={symbol}").json()["price"])
                summary += f"{symbol} - شراء: {buy_price:.2f}€ | الآن: {current_price:.2f}€ | الذروة: {peak_price:.2f}€\n"
            send_message(summary or "لا يوجد عملات تحت المراقبة")

        elif "طوارئ" in text or "#EMERGENCY" in text:
            for key in r.keys():
                sell_coin(key.decode())

        elif "-EUR" in text:
            parts = text.split()
            for word in parts:
                if "-EUR" in word:
                    buy_coin(word.strip())

    except Exception as e:
        print("❌ خطأ في Webhook:", e)
    return "", 200

if __name__ == "__main__":
    send_message("🚀 تم تشغيل بوت أبو الهول بنجاح!")
    threading.Thread(target=monitor_prices).start()
    app.run(host="0.0.0.0", port=8080)
