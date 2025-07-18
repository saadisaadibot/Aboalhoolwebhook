import os
import time
import json
import redis
import requests
import threading
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo

# 📦 متغيرات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
REDIS_URL = os.getenv("REDIS_URL")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")
PORT = int(os.environ.get("PORT", 8080))

# ⛓️ الاتصال مع Redis
db = redis.from_url(REDIS_URL, decode_responses=True)

# 🔗 Bitvavo API
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# 📡 إعداد Flask
app = Flask(__name__)
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 📩 إرسال رسالة تيليغرام
def send_message(text):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print("❌ فشل إرسال الرسالة:", e)

# 🏷️ جلب سعر العملة من Bitvavo
def fetch_price(symbol):
    try:
        result = bitvavo.tickerPrice({"market": symbol})
        return float(result["price"])
    except:
        return None

# 💰 شراء عملة بـ 10 يورو
def buy(symbol):
    try:
        bitvavo.placeOrder(symbol, 'buy', 'market', {'amount': 10})
        return True
    except Exception as e:
        send_message(f"❌ فشل تنفيذ أمر الشراء: {e}")
        return False

# 🔥 بيع كامل الرصيد
def sell(symbol):
    try:
        base = symbol.split("-")[0]
        balance = bitvavo.balance({"symbol": base})
        amount = float(balance[0]["available"])
        if amount > 0:
            bitvavo.placeOrder(symbol, 'sell', 'market', {"amount": amount})
        return True
    except Exception as e:
        send_message(f"❌ فشل تنفيذ البيع لـ {symbol}: {e}")
        return False

# 🧹 مسح الذاكرة
def delete_memory():
    for key in db.keys():
        db.delete(key)
    send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")

# 📊 ملخص الصفقات والمراقبة
def summary():
    log = json.loads(db.get("sell_log", "[]"))
    total_profit = sum([x["change"] for x in log])
    wins = sum([1 for x in log if x["change"] > 0])
    losses = sum([1 for x in log if x["change"] < 0])

    msg = (
        f"📈 صفقات رابحة: {wins}\n"
        f"📉 صفقات خاسرة: {losses}\n"
        f"💰 إجمالي الأرباح/الخسائر: {round(total_profit, 2)}%\n"
    )

    watching = []
    for key in db.keys():
        if key == "sell_log":
            continue
        entry = json.loads(db.get(key))
        duration = int((time.time() - entry["start_time"]) / 60)
        watching.append(f"👁️ {key} منذ {duration} دقيقة")

    if watching:
        msg += "\n" + "\n".join(watching)

    send_message(msg)

# 📉 منطق البيع والمراقبة
def check_prices():
    while True:
        try:
            for symbol in list(db.keys()):
                if symbol == "sell_log":
                    continue
                entry = json.loads(db.get(symbol))
                current = fetch_price(symbol)
                if not current:
                    continue
                entry_price = entry["entry"]
                change = ((current - entry_price) / entry_price) * 100

                if entry.get("status") == "trailing":
                    peak = entry["peak"]
                    if current > peak:
                        entry["peak"] = current
                        db.set(symbol, json.dumps(entry))
                    elif ((peak - current) / peak) * 100 >= 1.5:
                        sell(symbol)
                        send_message(f"🎯 بيع {symbol} بعد صعود وهبوط، ربح {round(change,2)}%")
                        log = json.loads(db.get("sell_log", "[]"))
                        log.append({"symbol": symbol, "change": round(change, 2)})
                        db.set("sell_log", json.dumps(log))
                        db.delete(symbol)
                else:
                    if change >= 3:
                        entry["status"] = "trailing"
                        entry["peak"] = current
                        db.set(symbol, json.dumps(entry))
                        send_message(f"🟢 {symbol} ارتفع +3%، بدأنا متابعة القمة")
                    elif change <= -3:
                        sell(symbol)
                        send_message(f"🔻 تم البيع بخسارة {symbol} بنسبة {round(change,2)}%")
                        log = json.loads(db.get("sell_log", "[]"))
                        log.append({"symbol": symbol, "change": round(change, 2)})
                        db.set("sell_log", json.dumps(log))
                        db.delete(symbol)
        except Exception as e:
            print("❌ خطأ في المراقبة:", e)
        time.sleep(7)

# 🧲 استقبال Webhook من صقر
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {}) or data.get("edited_message", {})
    text = msg.get("text") or msg.get("caption") or ""

    if "-EUR" in text:
        for word in text.split():
            if "-EUR" in word and word not in db:
                price = fetch_price(word)
                if price and buy(word):
                    db.set(word, json.dumps({
                        "entry": price,
                        "start_time": time.time(),
                        "status": None
                    }))
                    send_message(f"🤖 تم شراء {word} بسعر {price:.2f}€ ومراقبته.")
    return "200"

# 📥 أوامر تيليغرام
@app.route(f"/bot/{BOT_TOKEN}", methods=["POST"])
def telegram():
    data = request.json
    msg = data.get("message", {}) or data.get("edited_message", {})
    text = msg.get("text", "")

    if "يرجى المسح" in text:
        delete_memory()
    elif "الملخص" in text:
        summary()
    return "ok"

# 🚀 بدء البوت
if __name__ == "__main__":
    send_message("✅ تم تشغيل أبو الهول الملكي بنجاح 👑")
    threading.Thread(target=check_prices, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
