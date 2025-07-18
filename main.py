import os
import time
import threading
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo

# إعداد البوت
app = Flask(__name__)
bitvavo = Bitvavo({
    'APIKEY': os.getenv('BITVAVO_API_KEY'),
    'APISECRET': os.getenv('BITVAVO_API_SECRET'),
    'RESTURL': 'https://api.bitvavo.com/v2'
})

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
redis_url = os.getenv('REDIS_URL')
r = redis.from_url(redis_url, decode_responses=True)

def send_message(text):
    url = f"{BASE_URL}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def fetch_price(symbol):
    try:
        res = bitvavo.tickerPrice({'market': symbol})
        return float(res['price'])
    except:
        return None

def buy(symbol):
    try:
        res = bitvavo.placeOrder({
            'market': symbol,
            'side': 'buy',
            'orderType': 'market',
            'amount': str(round(10 / fetch_price(symbol), 8))
        })
        return res
    except Exception as e:
        send_message(f"❌ فشل في الشراء: {e}")
        return None

def sell(symbol, amount):
    try:
        res = bitvavo.placeOrder({
            'market': symbol,
            'side': 'sell',
            'orderType': 'market',
            'amount': str(amount)
        })
        return res
    except Exception as e:
        send_message(f"❌ فشل في البيع: {e}")
        return None

def monitor():
    while True:
        keys = [key for key in r.keys() if key.endswith('-EUR')]
        for symbol in keys:
            try:
                data = eval(r.get(symbol))
                buy_price = data['buy_price']
                amount = data['amount']
                high = data.get('high', buy_price)
                price = fetch_price(symbol)

                if not price:
                    continue

                if price > high:
                    high = price
                    data['high'] = high
                    r.set(symbol, str(data))

                change = (price - buy_price) / buy_price * 100
                drop_from_high = (high - price) / high * 100

                if change >= 3 and drop_from_high >= 1.5:
                    sell(symbol, amount)
                    r.delete(symbol)
                    log = f"✅ تم البيع: {symbol} بربح {round(change, 2)}%"
                    send_message(log)
                    update_sell_log(log)

                elif change <= -3:
                    sell(symbol, amount)
                    r.delete(symbol)
                    log = f"⚠️ تم البيع بخسارة: {symbol} بنسبة {round(change, 2)}%"
                    send_message(log)
                    update_sell_log(log)

            except Exception as e:
                send_message(f"🚨 خطأ في المراقبة: {e}")
        time.sleep(15)

def update_sell_log(entry):
    old = r.get("sell_log") or ""
    updated = old + entry + "\n"
    r.set("sell_log", updated)

@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    try:
        msg = request.json["message"]
        text = msg.get("text", "")
        if not text:
            return "No text", 200

        if text == "الملخص":
            return summary(), 200

        elif "يرجى المسح" in text:
            try:
                for key in r.keys():
                    r.delete(key)
                send_message("🧹 تم مسح الذاكرة.")
            except Exception as e:
                send_message(f"⚠️ فشل في المسح: {e}")
            return "Done", 200

        elif text in ["طوارئ", "#EMERGENCY"]:
            try:
                keys = [key for key in r.keys() if key.endswith("-EUR")]
                for symbol in keys:
                    data = eval(r.get(symbol))
                    sell(symbol, data['amount'])
                    r.delete(symbol)
                send_message("🚨 تم تنفيذ بيع كامل للمحفظة.")
            except Exception as e:
                send_message(f"⚠️ فشل في بيع الطوارئ: {e}")
            return "Emergency", 200

        elif "-EUR" in text:
            symbol = text.strip()
            price = fetch_price(symbol)
            if not price:
                send_message(f"⚠️ لم يتم جلب سعر {symbol}")
                return "Error", 200

            res = buy(symbol)
            if res:
                amount = float(res['filled'][0]['amount'])
                r.set(symbol, str({'buy_price': price, 'amount': amount, 'high': price}))
                send_message(f"👁️‍🗨️ تمت المراقبة: {symbol} عند سعر {price}")
            return "OK", 200

        return "Ignored", 200
    except Exception as e:
        send_message(f"❌ حدث خطأ: {e}")
        return "Error", 200

def summary():
    keys = [key for key in r.keys() if key.endswith("-EUR")]
    if not keys:
        send_message("📭 لا توجد عملات تحت المراقبة.")
        return "No coins", 200

    summary_text = "📊 العملات تحت المراقبة:\n"
    for symbol in keys:
        try:
            data = eval(r.get(symbol))
            price = fetch_price(symbol)
            change = (price - data['buy_price']) / data['buy_price'] * 100
            summary_text += f"• {symbol} 🔹 ربح/خسارة: {round(change, 2)}%\n"
        except:
            continue

    log = r.get("sell_log") or ""
    if log:
        summary_text += f"\n📜 سجل المبيعات:\n{log}"

    send_message(summary_text)
    return "Sent", 200

if __name__ == "__main__":
    send_message("🤖 تم تشغيل بوت أبو الهول بنجاح!")
    threading.Thread(target=monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
