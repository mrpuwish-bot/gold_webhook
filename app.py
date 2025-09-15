import os
import time
from datetime import datetime
from flask import Flask, request, jsonify
from openai import OpenAI
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GPT_MODEL = "gpt-4o"

client = OpenAI(api_key=OPENAI_API_KEY)

# --- Deduplication ---
last_signal_cache = {
    "fingerprint": None,
    "timestamp": 0
}
DEDUPLICATION_WINDOW_SECONDS = 5

@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return jsonify({"status": "❌ Error", "message": "Request must be JSON"}), 400

    data = request.json

    current_fingerprint = str(data)
    current_timestamp = time.time()
    if (current_fingerprint == last_signal_cache["fingerprint"] and 
        current_timestamp - last_signal_cache["timestamp"] < DEDUPLICATION_WINDOW_SECONDS):
        print(f"Duplicate signal ignored: {current_fingerprint}")
        return jsonify({"status": "🟡 Ignored", "message": "Duplicate signal."}), 200

    last_signal_cache["fingerprint"] = current_fingerprint
    last_signal_cache["timestamp"] = current_timestamp
    print(f"New signal received: {current_fingerprint}")

    try:
        prompt = build_prompt_from_pine(data)
        gpt_reply = ask_gpt(prompt)
        send_telegram_message(gpt_reply)
        return jsonify({"status": "✅ Sent to Telegram", "GPT_Response": gpt_reply}), 200
    except Exception as e:
        return jsonify({"status": "❌ Error", "message": str(e)}), 500

def build_prompt_from_pine(data):
    symbol = data.get("symbol", "N/A")
    timestamp = data.get("timestamp", 0)
    signal = data.get("signal", {})
    trade = data.get("trade_setup", {})
    context = data.get("market_context", {})
    fundamentals = data.get("fundamentals", {})
    tech = data.get("technical_details", {})

    readable_time = "N/A"
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    return f"""
📡 สัญญาณจาก Gold Pro System

- สัญลักษณ์: {symbol}
- เวลา: {readable_time}
- กลยุทธ์: {signal.get('strategy')} | ทิศทาง: {signal.get('direction')}
- เหตุผล: {signal.get('reason')}
- ความมั่นใจ: {signal.get('confidence')}%

🎯 จุดเข้า: {trade.get('entry')} | SL: {trade.get('stop_loss')} | TP: {trade.get('take_profit')}
- RR: {trade.get('risk_reward')} | Pip Risk: {trade.get('pip_risk')} | Size: {trade.get('position_size')}

📊 Context:
- เทรนด์ H1: {context.get('h1_trend')} ({context.get('trend_strength')})
- Session: {context.get('session')}
- RSI M15: {context.get('rsi_m15')} | Vol Ratio: {context.get('volatility_ratio')}

📉 Fundamentals:
- DXY: Bearish={fundamentals.get('dxy_bearish')} | Bullish={fundamentals.get('dxy_bullish')}
- Yield: Falling={fundamentals.get('yield_falling')} | Rising={fundamentals.get('yield_rising')}
- VIX: {fundamentals.get('vix_level')}

🔎 แนวรับ/ต้าน:
- EMA50/200 H1: {tech.get('ema50_h1')} / {tech.get('ema200_h1')}
- Support: {tech.get('support')} | Resistance: {tech.get('resistance')}
"""

def ask_gpt(prompt):
    system_prompt = """คุณคือ GoldScalpGPT — ผู้ช่วยเทรด XAU/USD มืออาชีพ:
- วิเคราะห์ H1 = เทรนด์ / M15 = Setup / M5 = Entry
- ห้ามเดา ห้ามชี้สัญญาณถ้าโครงสร้างยังไม่ชัด
- ถ้าพร้อมเข้าออเดอร์: ระบุ BUY หรือ SELL พร้อม Entry, SL, TP1, TP2
- บอกเหตุผล และระยะเวลาถือคร่าว ๆ
"""
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=False)
