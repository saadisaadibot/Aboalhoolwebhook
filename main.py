
import os
import json
import redis
import requests
from flask import Flask, request

app = Flask(__name__)

# إعدادات تيليغرام
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Redis
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True)

def send_message(text):
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(BASE_URL, data={"chat_id": CHAT_ID, "text": text})
        except Exception as e:
            print(f"فشل الإرسال: {e}")
    else:
        print("⚠️ لم يتم ضبط متغيرات BOT_TOKEN أو CHAT_ID")

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("✅ Webhook استلم:", data)

        message = data.get("message", {})
        text = message.get("text", "")

        if "-EUR" in text:
            words = text.split()
            for word in words:
                if "-EUR" in word and not r.exists(word):
                    r.set(word, json.dumps({
                        "entry": "waiting",
                        "status": None,
                        "start_time": 0
                    }))
                    print(f"💾 تم تسجيل العملة: {word}")
                    send_message(f"🕵️‍♂️ أبو الهول بدأ بمراقبة {word}")

        return "200"
    except Exception as e:
        print("❌ خطأ:", e)
        return "error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
