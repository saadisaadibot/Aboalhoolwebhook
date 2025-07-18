
import os
import time
import json
import redis
import requests
from flask import Flask, request

# إعدادات تيليغرام
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# إعداد Redis
redis_url = os.getenv("REDIS_URL")
r = redis.from_url(redis_url, decode_responses=True)

# Flask App
app = Flask(__name__)

def send_message(text):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print(f"خطأ أثناء إرسال الرسالة: {e}")

def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        response = requests.get(url)
        if response.status_code == 200:
            return float(response.json()["price"])
    except:
        return None

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("✅ Webhook استلم:", data)
        msg = data.get("message") or data.get("edited_message") or {}
        text = msg.get("text", "") or msg.get("caption", "")
        if not text:
            return "no text", 200

        parts = text.split()
        for word in parts:
            if "-EUR" in word and not r.exists(word):
                price = fetch_price(word)
                if price:
                    r.set(word, json.dumps({
                        "entry": price,
                        "status": None,
                        "start_time": time.time()
                    }))
                    send_message(f"🕵️‍♂️ أبو الهول يراقب {word} عند {price} EUR")
        return "200", 200
    except Exception as e:
        print("❌ خطأ:", e)
        return "error", 500

@app.route("/", methods=["GET"])
def index():
    return "Abu Houl Webhook Running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
