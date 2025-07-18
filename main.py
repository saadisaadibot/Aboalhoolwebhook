import os
import time
import json
import redis
import requests
from flask import Flask, request
import threading
from python_bitvavo_api.bitvavo import Bitvavo

# ⚙️ إعداد المتغيرات
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
REDIS_URL = os.getenv("REDIS_URL")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET")
PORT = int(os.environ.get("PORT", 5000))

# 🧠 إعداد Redis
db = redis.from_url(REDIS_URL, decode_responses=True)

# 🤖 إعداد Bitvavo
bitvavo = Bitvavo({
    'APIKEY': BITVAVO_API_KEY,
    'APISECRET': BITVAVO_API_SECRET,
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# 🚀 Flask
app = Flask(__name__)

# 📤 إرسال رسالة
def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("❌ فشل إرسال الرسالة:", e)

# 💸 تنفيذ شراء Market بقيمة 10 يورو
def buy(symbol):
    try:
        bitvavo.placeOrder(symbol, 'buy', 'market', {'amountQuote': 10})
        return True
    except Exception as e:
        send_message(f"❌ فشل الشراء: {e}")
        return False

# 💰 تنفيذ بيع كامل الرصيد لرمز معين
def sell(symbol):
    try:
        asset = symbol.split("-")[0]
        balance = bitvavo.balance({'symbol': asset})
        amount = float(balance[0]["available"])
        if amount > 0:
            bitvavo.placeOrder(symbol, 'sell', 'market', {'amount': amount})
            return amount
    except Exception as e:
        send_message(f"❌ فشل البيع: {e}")
    return 0

# 🧹 مسح الذاكرة
def delete_memory():
    for key in db.keys():
        if key != "sell_log":
            db.delete(key)
    send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")

# ⏱️ تنسيق الوقت
def format_duration(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h} ساعة و{m} دقيقة" if h else f"{m} دقيقة"

# 💵 جلب السعر الحالي
def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        res = requests.get(url)
        if res.status_code == 200:
            return float(res.json()["price"])
    except:
        return None

# 📊 عرض الملخص
def summary():
    log = json.loads(db.get("sell_log", "[]"))
    if not log:
        send_message("📊 لا توجد أي عمليات بيع مُسجلة بعد.")
        return

    total_profit = 0
    win = 0
    lose = 0
    for trade in log:
        total_profit += trade["change"]
        if trade["change"] >= 0:
            win += 1
        else:
            lose += 1

    msg = (
        f"📈 عدد الصفقات الرابحة: {win}\n"
        f"📉 عدد الصفقات الخاسرة: {lose}\n"
        f"💰 صافي الربح/الخسارة: {round(total_profit, 2)}%\n"
    )

    watchlist = []
    for key in db.keys():
        if key == "sell_log":
            continue
        entry = json.loads(db.get(key))
        minutes = int((time.time() - entry["start_time"]) / 60)
        watchlist.append(f"- {key} منذ {format_duration(minutes)}")

    if watchlist:
        msg += "\n👁️ العملات المُراقبة:\n" + "\n".join(watchlist)

    send_message(msg)

# 📈 منطق مراقبة الربح والخسارة
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
                amount = sell(symbol)
                send_message(f"🎯 {symbol} بيع بعد صعود + نزول بنسبة {round(change, 2)}%")
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
                send_message(f"🟢 {symbol} ارتفعت +3% – بدأنا مراقبة القمة.")
            elif change <= -3:
                amount = sell(symbol)
                send_message(f"📉 {symbol} خسارة {round(change, 2)}% – تم البيع.")
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

# 🛰️ استقبال إشارات صقر وأوامر المجموعة
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        msg = data.get("message", {}) or data.get("edited_message", {})
        text = msg.get("text") or msg.get("caption") or ""
        if not text:
            return "ok"

        # طوارئ
        if "طوارئ" in text or "#EMERGENCY" in text:
            for symbol in list(db.keys()):
                if symbol == "sell_log":
                    continue
                sell(symbol)
                db.delete(symbol)
            send_message("🚨 تم تفعيل وضع الطوارئ وبيع كل العملات.")
            return "ok"

        # أمر المسح
        if "يرجى المسح" in text:
            delete_memory()
            return "ok"

        # الملخص
        if "الملخص" in text or "الحسابات" in text:
            summary()
            return "ok"

        # شراء تلقائي عند وجود -EUR
        if "-EUR" in text:
            for word in text.split():
                if "-EUR" in word and word not in db:
                    price = fetch_price(word)
                    if price:
                        if buy(word):
                            db.set(word, json.dumps({
                                "entry": price,
                                "status": None,
                                "start_time": time.time()
                            }))
                            send_message(f"🕵️‍♂️ بدأ مراقبة {word} عند {price} يورو")
        return "ok"
    except Exception as e:
        print("❌ Webhook Error:", e)
        return "error", 500

# 🏁 تشغيل البوت
if __name__ == "__main__":
    send_message("🤖 تم تشغيل أبو الهول بنجاح!")
    def loop():
        while True:
            try:
                check_prices()
                time.sleep(5)
            except Exception as e:
                print("❌ حلقة المراقبة:", e)
                time.sleep(10)
    threading.Thread(target=loop).start()
    app.run(host="0.0.0.0", port=PORT)
