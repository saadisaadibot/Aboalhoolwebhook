
import os
import json
import time
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

def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        response = requests.get(url)
        if response.status_code == 200:
            return float(response.json()["price"])
    except:
        return None

def format_duration(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} ساعة و{mins} دقيقة" if hours else f"{mins} دقيقة"

def process_commands(text):
    if "حذف" in text:
        keys = r.keys("*-EUR")
        for k in keys:
            r.delete(k)
        r.delete("sell_log")
        send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")

    elif "الملخص" in text or "الحسابات" in text:
        log = json.loads(r.get("sell_log") or "[]")
        if not log:
            send_message("📊 لا توجد أي عمليات بيع مُسجلة بعد.")
        else:
            total_profit = 0
            win_count = 0
            lose_count = 0
            for trade in log:
                profit_percent = ((trade["exit"] - trade["entry"]) / trade["entry"]) * 100
                total_profit += profit_percent
                if profit_percent >= 0:
                    win_count += 1
                else:
                    lose_count += 1

            msg = (
                f"📈 عدد الصفقات الرابحة: {win_count}
"
                f"📉 عدد الصفقات الخاسرة: {lose_count}
"
                f"💰 صافي الربح/الخسارة: {round(total_profit, 2)}%
"
            )

            # 👁️ العملات التي تتم مراقبتها الآن
            keys = r.keys("*-EUR")
            watchlist = []
            for key in keys:
                entry = json.loads(r.get(key))
                duration_min = int((time.time() - entry["start_time"]) / 60)
                watchlist.append(f"- {key} منذ {format_duration(duration_min)}")

            if watchlist:
                msg += "
👁️ العملات التي تتم مراقبتها الآن:
" + "
".join(watchlist)
            send_message(msg)

def process_price_tracking():
    keys = r.keys("*-EUR")
    for symbol in keys:
        entry = json.loads(r.get(symbol))
        price = fetch_price(symbol)
        if not price:
            continue

        entry_price = entry["entry"]

        if entry.get("status") == "trailing":
            peak = entry["peak"]
            if price > peak:
                entry["peak"] = price
                r.set(symbol, json.dumps(entry))
            drop = ((peak - price) / peak) * 100
            if drop >= 1.5:
                change = ((price - entry_price) / entry_price) * 100
                send_message(f"🎯 {symbol} تم البيع بعد ارتفاع ثم نزول – ربح {round(change,2)}%")
                log = json.loads(r.get("sell_log") or "[]")
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": price,
                    "change": round(change,2),
                    "result": "ربح"
                })
                r.set("sell_log", json.dumps(log))
                r.delete(symbol)
        else:
            change = ((price - entry_price) / entry_price) * 100
            if change >= 3:
                entry["status"] = "trailing"
                entry["peak"] = price
                r.set(symbol, json.dumps(entry))
                send_message(f"🟢 {symbol} ارتفعت +3% – نبدأ مراقبة القمة.")
            elif change <= -3:
                send_message(f"📉 {symbol} خسارة -{round(abs(change), 2)}% – تم البيع.")
                log = json.loads(r.get("sell_log") or "[]")
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": price,
                    "change": round(change,2),
                    "result": "خسارة"
                })
                r.set("sell_log", json.dumps(log))
                r.delete(symbol)

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("✅ Webhook استلم:", data)

        message = data.get("message", {})
        text = message.get("text", "")

        if "-EUR" in text:
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

        process_commands(text)
        return "200"
    except Exception as e:
        print("❌ خطأ:", e)
        return "error", 500

if __name__ == "__main__":
    import threading
    def loop():
        while True:
            try:
                process_price_tracking()
                time.sleep(5)
            except Exception as e:
                print("Loop Error:", e)
                time.sleep(5)
    threading.Thread(target=loop).start()
    send_message("🤖 تم تشغيل أبو الهول.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
