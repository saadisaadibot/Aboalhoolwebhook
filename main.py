import os
import time
import requests
import redis
import json
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
redis_url = os.getenv("REDIS_URL")
r = redis.from_url(redis_url, decode_responses=True)

def send_message(text):
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(f"{BASE_URL}/sendMessage", data=data)

def fetch_price(symbol):
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={symbol}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return float(resp.json().get("price", 0))
    except:
        return None

def check_prices():
    for symbol in r.keys():
        if symbol == "sell_log":
            continue
        entry = json.loads(r.get(symbol))
        current = fetch_price(symbol)
        if not current:
            continue
        entry_price = entry["entry"]

        if entry.get("status") == "trailing":
            peak = entry["peak"]
            if current > peak:
                entry["peak"] = current
                r.set(symbol, json.dumps(entry))
            drop = (peak - current) / peak * 100
            if drop >= 1.5:
                change = (current - entry_price) / entry_price * 100
                send_message(f"🎯 {symbol} تم البيع بعد پيك – ربح {round(change,2)}%")
                log = json.loads(r.get("sell_log") or "[]")
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": current,
                    "change": round(change,2),
                    "result": "ربح"
                })
                r.set("sell_log", json.dumps(log))
                r.delete(symbol)
        else:
            change = (current - entry_price) / entry_price * 100
            if change >= 3:
                entry["status"] = "trailing"
                entry["peak"] = current
                entry["start_time"] = time.time()
                r.set(symbol, json.dumps(entry))
                send_message(f"🟢 {symbol} +3% – بدء المراقبة.")
            elif change <= -3:
                send_message(f"📉 {symbol} خسارة -{abs(round(change,2))}% – بيع فوري.")
                log = json.loads(r.get("sell_log") or "[]")
                log.append({
                    "symbol": symbol,
                    "entry": entry_price,
                    "exit": current,
                    "change": round(change,2),
                    "result": "خسارة"
                })
                r.set("sell_log", json.dumps(log))
                r.delete(symbol)

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "", 200

    msg = data["message"]
    text = msg.get("text", "")

    if "تم قنص" in text:
        parts = text.split()
        for w in parts:
            if "-EUR" in w and not r.exists(w):
                price = fetch_price(w)
                if price:
                    r.set(w, json.dumps({
                        "entry": price,
                        "status": None,
                        "start_time": time.time()
                    }))
                    send_message(f"🕵️‍♂️ أبو الهول يراقب {w} عند {price} EUR")

    elif "احذف" in text or "حذف" in text:
        r.flushdb()
        send_message("🧹 تم مسح ذاكرة أبو الهول بالكامل.")

    elif "الملخص" in text or "الحسابات" in text:
        log = json.loads(r.get("sell_log") or "[]")
        if not log:
            send_message("📊 لا توجد أي عمليات بيع مسجلة.")
        else:
            total, wins, losses = 0, 0, 0
            for t in log:
                perf = (t["exit"] - t["entry"]) / t["entry"] * 100
                total += perf
                wins += 1 if perf >= 0 else 0
                losses += 1 if perf < 0 else 0
            summary = f"📈 فوز: {wins} — خسارة: {losses} — صافي: {round(total,2)}%"
            send_message(summary)

    return "", 200

if __name__ == "__main__":
    from threading import Thread
    def price_loop():
        while True:
            try:
                check_prices()
            except:
                pass
            time.sleep(10)

    Thread(target=price_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
