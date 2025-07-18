import os
import json
import time
import redis
import requests
from flask import Flask, request
from threading import Thread

app = Flask(__name__)

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
REDIS_URL = os.getenv("REDIS_URL")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

r = redis.from_url(REDIS_URL, decode_responses=True)

def send_message(text):
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(BASE_URL, data={"chat_id": CHAT_ID, "text": text})
        except Exception as e:
            print(f"فشل الإرسال: {e}")
    else:
        print("⚠️ لم يتم ضبط متغيرات BOT_TOKEN أو CHAT_ID")

def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return float(response.json()["price"])
    except:
        return None

def format_duration(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h} ساعة و{m} دقيقة" if h > 0 else f"{m} دقيقة"

def check_prices_loop():
    while True:
        try:
            for symbol in r.keys():
                if symbol == "sell_log":
                    continue

                data = json.loads(r.get(symbol))
                current = fetch_price(symbol)
                if not current:
                    continue

                entry = data["entry"]
                if entry == "waiting":
                    continue

                if data.get("status") == "trailing":
                    peak = data["peak"]
                    if current > peak:
                        data["peak"] = current
                        r.set(symbol, json.dumps(data))

                    drop = ((peak - current) / peak) * 100
                    if drop >= 1.5:
                        change = ((current - entry) / entry) * 100
                        send_message(f"🎯 {symbol} تم البيع بعد ارتفاع ثم نزول – ربح {round(change,2)}%")
                        log = json.loads(r.get("sell_log") or "[]")
                        log.append({
                            "symbol": symbol,
                            "entry": entry,
                            "exit": current,
                            "change": round(change,2),
                            "result": "ربح"
                        })
                        r.set("sell_log", json.dumps(log))
                        r.delete(symbol)
                else:
                    change = ((current - entry) / entry) * 100
                    if change >= 3:
                        data["status"] = "trailing"
                        data["peak"] = current
                        data["start_time"] = time.time()
                        r.set(symbol, json.dumps(data))
                        send_message(f"🟢 {symbol} ارتفعت +3% – نبدأ مراقبة القمة.")
                    elif change <= -3:
                        send_message(f"📉 {symbol} خسارة -{round(abs(change),2)}% – تم البيع.")
                        log = json.loads(r.get("sell_log") or "[]")
                        log.append({
                            "symbol": symbol,
                            "entry": entry,
                            "exit": current,
                            "change": round(change,2),
                            "result": "خسارة"
                        })
                        r.set("sell_log", json.dumps(log))
                        r.delete(symbol)

            time.sleep(5)

        except Exception as e:
            print(f"❌ خطأ في المراقبة: {e}")
            time.sleep(10)

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("📥 Webhook وصل:", data)

        message = data.get("message", {})
        text = message.get("text", "")

        if "-EUR" in text:
            words = text.split()
            for word in words:
                if "-EUR" in word and not r.exists(word):
                    price = fetch_price(word)
                    if price:
                        r.set(word, json.dumps({
                            "entry": price,
                            "status": None,
                            "start_time": time.time()
                        }))
                        send_message(f"🕵️‍♂️ أبو الهول يراقب {word} عند {price} EUR")
                        print(f"✅ سجل {word} عند {price}")
                    else:
                        print(f"⚠️ تعذر جلب سعر {word}")
        return "200"

    except Exception as e:
        print("❌ خطأ في Webhook:", e)
        return "error", 500

if __name__ == "__main__":
    Thread(target=check_prices_loop, daemon=True).start()
    print("🚀 أبو الهول يعمل الآن على Webhook و Redis.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
