import os
import json
import time
import redis
import requests
from flask import Flask, request
from python_bitvavo_api.bitvavo import Bitvavo

app = Flask(__name__)

# إعدادات Bitvavo
bitvavo = Bitvavo({
    'APIKEY': os.getenv("BITVAVO_API_KEY"),
    'APISECRET': os.getenv("BITVAVO_API_SECRET"),
    'RESTURL': 'https://api.bitvavo.com/v2'
})

# إعدادات تيليغرام
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Redis
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True)

def send_message(text):
    try:
        requests.post(BASE_URL, data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print(f"فشل إرسال رسالة تيليغرام: {e}")

def fetch_price(symbol):
    try:
        response = requests.get(f"https://api.bitvavo.com/v2/ticker/price?market={symbol}")
        if response.status_code == 200:
            return float(response.json()["price"])
    except:
        return None

def buy(symbol, amount_eur):
    try:
        response = bitvavo.placeOrder(
            symbol,
            'buy',
            'market',
            { 'amountQuote': str(amount_eur) }
        )
        print("✅ عملية شراء:", response)
        return fetch_price(symbol)
    except Exception as e:
        print("❌ فشل الشراء:", e)
        return None

def sell(symbol, amount):
    try:
        response = bitvavo.placeOrder(
            symbol,
            'sell',
            'market',
            { 'amount': str(amount) }
        )
        print("🟥 عملية بيع:", response)
    except Exception as e:
        print("❌ فشل البيع:", e)

def get_balance(symbol):
    try:
        balances = bitvavo.balance({})
        for b in balances:
            if b["symbol"] == symbol.split("-")[0]:
                return float(b["available"])
        return 0
    except Exception as e:
        print("⚠️ خطأ بجلب الرصيد:", e)
        return 0

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.json
        message = data.get("message", {}) or data.get("edited_message", {})
        text = message.get("text", "")
        if not text:
            return "no text"

        if "طوارئ" in text or "#EMERGENCY" in text:
            emergency_sell()
            return "200"

        if "-EUR" in text:
            for word in text.split():
                if "-EUR" in word and not r.exists(word):
                    price = buy(word, 10)
                    if price:
                        r.set(word, json.dumps({
                            "entry": price,
                            "status": None,
                            "start_time": time.time()
                        }))
                        send_message(f"🕵️‍♂️ أبو الهول يراقب {word} عند {price} EUR")
        return "200"
    except Exception as e:
        print("❌ Webhook Error:", e)
        return "500"

def emergency_sell():
    for key in r.keys():
        if key == "sell_log":
            continue
        entry = json.loads(r.get(key))
        current = fetch_price(key)
        if not current:
            continue
        entry_price = entry["entry"]
        amount = get_balance(key)
        if amount > 0:
            sell(key, amount)
            change = ((current - entry_price) / entry_price) * 100
            result = "ربح" if change >= 0 else "خسارة"
            send_message(f"⚡ {key} تم بيعه بوضع الطوارئ – {result} {round(change, 2)}%")
            log = json.loads(r.get("sell_log") or "[]")
            log.append({
                "symbol": key,
                "entry": entry_price,
                "exit": current,
                "change": round(change, 2),
                "result": result
            })
            r.set("sell_log", json.dumps(log))
            r.delete(key)

def check_prices():
    for key in r.keys():
        if key == "sell_log":
            continue
        entry = json.loads(r.get(key))
        entry_price = entry["entry"]
        current = fetch_price(key)
        if not current:
            continue

        if entry.get("status") == "trailing":
            peak = entry["peak"]
            if current > peak:
                entry["peak"] = current
                r.set(key, json.dumps(entry))
            drop = ((peak - current) / peak) * 100
            if drop >= 1.5:
                amount = get_balance(key)
                if amount > 0:
                    sell(key, amount)
                    change = ((current - entry_price) / entry_price) * 100
                    send_message(f"🎯 {key} تم البيع بعد ارتفاع ثم نزول – ربح {round(change,2)}%")
                    log = json.loads(r.get("sell_log") or "[]")
                    log.append({
                        "symbol": key,
                        "entry": entry_price,
                        "exit": current,
                        "change": round(change, 2),
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
                amount = get_balance(key)
                if amount > 0:
                    sell(key, amount)
                    send_message(f"📉 {key} خسارة -{round(abs(change), 2)}% – تم البيع.")
                    log = json.loads(r.get("sell_log") or "[]")
                    log.append({
                        "symbol": key,
                        "entry": entry_price,
                        "exit": current,
                        "change": round(change, 2),
                        "result": "خسارة"
                    })
                    r.set("sell_log", json.dumps(log))
                    r.delete(key)

@app.route("/")
def home():
    return "✅ Abo Alhoul Trading Bot is running."

if __name__ == "__main__":
    send_message("✅ تم تشغيل أبو الهول الحقيقي بنجاح.")
    from threading import Thread
    def run_checker():
        while True:
            try:
                check_prices()
                time.sleep(15)
            except Exception as e:
                print("⚠️ Price check error:", e)
                time.sleep(10)
    Thread(target=run_checker).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
