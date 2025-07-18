
import os
import json
import time
import redis
import requests
import threading
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True)

def send_message(text):
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(BASE_URL, data={"chat_id": CHAT_ID, "text": text})
        except Exception as e:
            print(f"فشل الإرسال: {e}")

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

        message = data.get("message", {}) or data.get("edited_message", {})
        text = message.get("text", "").strip()

        if "احذف" in text or "حذف" in text:
            for key in list(r.scan_iter()):
                r.delete(key)
            send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")
            return "200"

        elif "الملخص" in text or "الحسابات" in text:
            log = json.loads(r.get("sell_log")) if r.exists("sell_log") else []
            if not log:
                send_message("📊 لا توجد أي عمليات بيع مُسجلة بعد.")
            else:
                total_profit = 0
                win_count = 0
                lose_count = 0
                for trade in log:
                    entry = trade["entry"]
                    exit_price = trade["exit"]
                    profit_percent = ((exit_price - entry) / entry) * 100
                    total_profit += profit_percent
                    if profit_percent >= 0:
                        win_count += 1
                    else:
                        lose_count += 1
                msg = (
                    f"📈 عدد الصفقات الرابحة: {win_count}\n"
                    f"📉 عدد الصفقات الخاسرة: {lose_count}\n"
                    f"💰 صافي الربح/الخسارة: {round(total_profit, 2)}%\n"
                )
                watchlist = []
                for key in r.scan_iter():
                    if key == "sell_log":
                        continue
                    entry = json.loads(r.get(key))
                    minutes = int((time.time() - entry["start_time"]) / 60)
                    duration = f"{minutes} دقيقة" if minutes < 60 else f"{minutes // 60} ساعة و{minutes % 60} دقيقة"
                    watchlist.append(f"- {key} منذ {duration}")
                if watchlist:
                    msg += "\n👁️ العملات التي تتم مراقبتها الآن:\n" + "\n".join(watchlist)
                send_message(msg)
            return "200"

        if "طوارئ" in text or "🚨" in text:
            count = 0
            for key in list(r.scan_iter()):
                if key == "sell_log":
                    continue
                entry = json.loads(r.get(key))
                current = fetch_price(key)
                if current:
                    entry_price = entry["entry"]
                    change = ((current - entry_price) / entry_price) * 100
                    result = "ربح" if change >= 0 else "خسارة"
                    send_message(f"⚠️ بيع {key} بنسبة {round(change, 2)}% – {result}")
                    log = json.loads(r.get("sell_log") or "[]")
                    log.append({
                        "symbol": key,
                        "entry": entry_price,
                        "exit": current,
                        "change": round(change,2),
                        "result": result
                    })
                    r.set("sell_log", json.dumps(log))
                    r.delete(key)
                    count += 1
            send_message(f"🚨 تم تنفيذ بيع الطوارئ لعدد {count} عملة.")
            return "200"

        if "-EUR" in text:
            for word in text.split():
                if "-EUR" in word and not r.exists(word):
                    price = fetch_price(word)
                    if price:
                        r.set(word, json.dumps({
                            "entry": price,
                            "status": None,
                            "start_time": time.time()
                        }))
                        send_message(f"🕵️‍♂️ أبو الهول يراقب {word} عند {price} EUR")
            return "200"

        return "تم الاستلام"
    except Exception as e:
        print("❌ خطأ:", e)
        return "error", 500

@app.route("/")
def home():
    return "Abo Alhoul Webhook is running."

def check_prices():
    while True:
        try:
            for key in list(r.scan_iter()):
                if key == "sell_log":
                    continue
                entry = json.loads(r.get(key))
                current = fetch_price(key)
                if not current:
                    continue
                entry_price = entry["entry"]
                if entry.get("status") == "trailing":
                    peak = entry["peak"]
                    if current > peak:
                        entry["peak"] = current
                        r.set(key, json.dumps(entry))
                    drop = ((peak - current) / peak) * 100
                    if drop >= 1.5:
                        change = ((current - entry_price) / entry_price) * 100
                        send_message(f"🎯 {key} تم البيع بعد ارتفاع ثم نزول – ربح {round(change,2)}%")
                        log = json.loads(r.get("sell_log") or "[]")
                        log.append({
                            "symbol": key,
                            "entry": entry_price,
                            "exit": current,
                            "change": round(change,2),
                            "result": "ربح"
                        })
                        r.set("sell_log", json.dumps(log))
                        r.delete(key)
                else:
                    change = ((current - entry_price) / entry_price) * 100
                    if change >= 3:
                        entry["status"] = "trailing"
                        entry["peak"] = current
                        r.set(key, json.dumps(entry))
                        send_message(f"🟢 {key} ارتفعت +3% – نبدأ مراقبة القمة.")
                    elif change <= -3:
                        send_message(f"📉 {key} خسارة -{round(abs(change), 2)}% – تم البيع.")
                        log = json.loads(r.get("sell_log") or "[]")
                        log.append({
                            "symbol": key,
                            "entry": entry_price,
                            "exit": current,
                            "change": round(change,2),
                            "result": "خسارة"
                        })
                        r.set("sell_log", json.dumps(log))
                        r.delete(key)
            time.sleep(5)
        except Exception as e:
            print("❌ خطأ في المتابعة:", e)
            time.sleep(10)

if __name__ == "__main__":
    send_message("✅ تم تشغيل أبو الهول (Webhook + مراقبة الأسعار).")
    threading.Thread(target=check_prices).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
