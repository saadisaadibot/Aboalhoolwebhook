
from flask import Flask, request
import os
import requests
import redis

app = Flask(__name__)

# إعدادات البوت
BOT_TOKEN = "8009488976:AAGU5x04wCdDavSoxzEM77SF17ZB_6QP-wU"
CHAT_ID = "-1002606997108"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# إعداد Redis
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

def send_telegram_message(text):
    requests.post(BASE_URL, data={"chat_id": CHAT_ID, "text": text})

@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    data = request.json
    print("✅ 200 - Received Webhook")
    print("📦 البيانات الواردة:", data)

    message = data.get("message", {})
    text = message.get("text", "")

    # استخراج العملة إذا فيها "تم قنص"
    if "تم قنص" in text:
        for word in text.split():
            if word.endswith("-EUR"):
                coin = word
                r.set(coin, "under_watch")
                print(f"👁️ تم وضع {coin} تحت المراقبة")
                send_telegram_message(f"📡 تم استقبال إشعار القنص لـ {coin}")
                break

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
