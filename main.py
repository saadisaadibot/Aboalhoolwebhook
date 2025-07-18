import os
import json
import threading
import time
import requests
from flask import Flask, request
from redis import Redis
from python_bitvavo_api.bitvavo import Bitvavo

# إعداد البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

# تيليغرام
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

# Redis
redis = Redis.from_url(REDIS_URL, decode_responses=True)

# Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET
})

# Flask
app = Flask(__name__)

@app.route('/')
def home():
    return 'Abo Alhool is alive!'

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    try:
        message = data.get("message", {}).get("text", "")
        if not message:
            return "No message", 200

        if message.strip() == "يرجى المسح":
            redis.flushdb()
            send_message("🧹 تم مسح الذاكرة بنجاح.")
            return "Memory cleared", 200

        elif message.strip() == "الملخص":
            keys = redis.keys("*")
            if not keys:
                send_message("لا يوجد عملات تحت المراقبة حالياً.")
            else:
                summary = "📊 العملات المراقبة:\n\n"
                for key in keys:
                    if key.startswith("sell_log"): continue
                    try:
                        coin = json.loads(redis.get(key))
                        summary += f"{key} - شراء: {coin['buy_price']}€\n"
                    except:
                        continue
                send_message(summary)
            return "Summary sent", 200

        elif message.strip() in ["طوارئ", "#EMERGENCY"]:
            keys = redis.keys("*")
            for symbol in keys:
                if symbol.startswith("sell_log"): continue
                coin = json.loads(redis.get(symbol))
                try:
                    balance = bitvavo.getBalance({'symbol': symbol.split('-')[0]})
                    quantity = float(balance["available"])
                    if quantity > 0:
                        bitvavo.placeOrder(symbol, {'side': 'sell', 'orderType': 'market', 'amount': quantity})
                        send_message(f"🚨 تم بيع {symbol} بسبب الطوارئ.")
                        redis.delete(symbol)
                except:
                    continue
            return "Emergency sell executed", 200

        elif "-EUR" in message:
            symbol = message.strip().upper()
            price = float(bitvavo.getTickerPrice({'market': symbol})['price'])
            redis.set(symbol, json.dumps({
                "symbol": symbol,
                "buy_price": price,
                "high_price": price
            }))
            bitvavo.placeOrder(symbol, {'side': 'buy', 'orderType': 'market', 'amount': 10 / price})
            send_message(f"📈 تمت مراقبة وشراء {symbol} عند {price}€")
            return "Coin registered", 200

    except Exception as e:
        send_message(f"❌ خطأ في Webhook: {str(e)}")
        return "Error", 500

    return "OK", 200

# مراقبة الأسعار
def watch_prices():
    while True:
        try:
            keys = redis.keys("*")
            for symbol in keys:
                if symbol.startswith("sell_log"): continue
                coin = json.loads(redis.get(symbol))
                current_price = float(bitvavo.getTickerPrice({'market': symbol})['price'])
                buy_price = float(coin["buy_price"])
                high_price = float(coin["high_price"])

                if current_price > high_price:
                    high_price = current_price
                    coin["high_price"] = high_price
                    redis.set(symbol, json.dumps(coin))

                profit_percent = ((current_price - buy_price) / buy_price) * 100
                drop_from_peak = ((high_price - current_price) / high_price) * 100

                if profit_percent >= 3 and drop_from_peak >= 1.5:
                    quantity = float(bitvavo.getBalance({'symbol': symbol.split('-')[0]})["available"])
                    if quantity > 0:
                        bitvavo.placeOrder(symbol, {'side': 'sell', 'orderType': 'market', 'amount': quantity})
                        send_message(f"💰 تم بيع {symbol} بربح {round(profit_percent,2)}%")
                        redis.delete(symbol)

                elif profit_percent <= -3:
                    quantity = float(bitvavo.getBalance({'symbol': symbol.split('-')[0]})["available"])
                    if quantity > 0:
                        bitvavo.placeOrder(symbol, {'side': 'sell', 'orderType': 'market', 'amount': quantity})
                        send_message(f"📉 تم بيع {symbol} بخسارة {round(profit_percent,2)}%")
                        redis.delete(symbol)

        except Exception as e:
            send_message(f"💥 خطأ في المراقبة: {str(e)}")
        time.sleep(30)

if __name__ == '__main__':
    send_message("🤖 تم تشغيل بوت أبو الهول بنجاح!")
    threading.Thread(target=watch_prices).start()
    app.run(host='0.0.0.0', port=8080)
