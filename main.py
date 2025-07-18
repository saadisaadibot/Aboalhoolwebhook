import os
import time
import json
import redis
import requests
from flask import Flask, request

# إعدادات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
REDIS_URL = os.getenv("REDIS_URL")
PORT = int(os.environ.get("PORT", 5000))
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Redis
db = redis.from_url(REDIS_URL, decode_responses=True)

# Flask
app = Flask(__name__)

# إرسال رسالة
def send_message(text):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print(f"❌ فشل إرسال الرسالة: {e}")

# جلب سعر العملة
def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        res = requests.get(url)
        if res.status_code == 200:
            return float(res.json()["price"])
    except:
        return None

# تلقي العملات من صقر عبر Webhook
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("✅ Webhook:", data)
        msg = data.get("message", {}) or data.get("edited_message", {})
        text = msg.get("text") or msg.get("caption") or ""
        if not text:
            return "ok"

        if "-EUR" in text:
            for word in text.split():
                if "-EUR" in word and word not in db:
                    price = fetch_price(word)
                    if price:
                        db.set(word, json.dumps({
                            "entry": price,
                            "status": None,
                            "start_time": time.time()
                        }))
                        send_message(f"🕵️‍♂️ أبو الهول يراقب {word} عند {price} EUR")
        return "200"
    except Exception as e:
        print("❌ Webhook Error:", e)
        return "error", 500

# حذف الذاكرة
def delete_memory():
    for key in db.keys():
        if key != "sell_log":
            db.delete(key)
    send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")

# حساب الوقت
def format_duration(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} ساعة و{mins} دقيقة" if hours else f"{mins} دقيقة"

# إرسال ملخص
def summary():
    log = json.loads(db.get("sell_log", "[]"))
    if not log:
        send_message("📊 لا توجد أي عمليات بيع مُسجلة بعد.")
        return

    total_profit = 0
    win_count = 0
    lose_count = 0
    for trade in log:
        total_profit += trade["change"]
        if trade["change"] >= 0:
            win_count += 1
        else:
            lose_count += 1

    msg = (
        f"📈 عدد الصفقات الرابحة: {win_count}\n"
        f"📉 عدد الصفقات الخاسرة: {lose_count}\n"
        f"💰 صافي الربح/الخسارة: {round(total_profit, 2)}%\n"
    )

    watchlist = []
    for key in db.keys():
        if key == "sell_log":
            continue
        entry = json.loads(db.get(key))
        duration = int((time.time() - entry["start_time"]) / 60)
        watchlist.append(f"- {key} منذ {format_duration(duration)}")

    if watchlist:
        msg += "\n👁️ العملات التي تتم مراقبتها الآن:\n" + "\n".join(watchlist)

    send_message(msg)

# مراقبة تغير السعر
def check_prices():
    for symbol in list(db.keys()):
        if symbol == "sell_log":
            continue

        entry = json.loads(db.get(symbol))
        current = fetch_price(symbol)
        if not current:
            continue

        entry_price = entry["entry"]

        if entry.get("status") == "trailing":
            peak = entry["peak"]
            if current > peak:
                entry["peak"] = current
                db.set(symbol, json.dumps(entry))

            drop = ((peak - current) / peak) * 100
            if drop >= 1.5:
                change = ((current - entry_price) / entry_price) * 100
                send_message(f"🎯 {symbol} تم البيع بعد ارتفاع ثم نزول – ربح {round(change, 2)}%")
                log = json.loads(db.get("sell_log", "[]"))
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": current,
                    "change": round(change, 2),
                    "result": "ربح"
                })
                db.set("sell_log", json.dumps(log))
                db.delete(symbol)

        else:
            change = ((current - entry_price) / entry_price) * 100
            if change >= 3:
                entry["status"] = "trailing"
                entry["peak"] = current
                db.set(symbol, json.dumps(entry))
                send_message(f"🟢 {symbol} ارتفعت +3% – نبدأ مراقبة القمة.")
            elif change <= -3:
                send_message(f"📉 {symbol} خسارة -{round(abs(change), 2)}% – تم البيع.")
                log = json.loads(db.get("sell_log", "[]"))
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": current,
                    "change": round(change, 2),
                    "result": "خسارة"
                })
                db.set("sell_log", json.dumps(log))
                db.delete(symbol)

# استقبال أوامر تيليغرام
@app.route(f"/bot/{BOT_TOKEN}", methods=["POST"])
def telegram_commands():
    try:
        data = request.json
        msg = data.get("message", {}) or data.get("edited_message", {})
        text = msg.get("text", "") or ""
        if "حذف" in text:
            delete_memory()
        elif "الملخص" in text or "الحسابات" in text:
            summary()
        return "ok"
    except Exception as e:
        print("❌ أمر تيليغرام فشل:", e)
        return "error", 500

# تشغيل البوت
if __name__ == "__main__":
    send_message("✅ تم تشغيل أبو الهول بنجاح (Webhook + Trail Logic).")
    import threading
    def loop():
        while True:
            try:
                check_prices()
                time.sleep(5)
            except Exception as e:
                print("❌ حلقة السعر:", e)
                time.sleep(10)
    threading.Thread(target=loop).start()
    app.run(host="0.0.0.0", port=PORT)
