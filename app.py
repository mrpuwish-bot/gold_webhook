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
    trade = data.get("trade_parameters", {})
    context = data.get("market_context", {})
    fundamentals = data.get("fundamentals", {})
    tech = data.get("technical_details", {})

    readable_time = "N/A"
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    return f"""
📊 บริบทการเทรดทองคำจาก Pine Script

สัญลักษณ์: {symbol}
เวลา: {readable_time}
กลยุทธ์: {signal.get('strategy')} | ทิศทาง: {signal.get('direction')} | ความมั่นใจ: {signal.get('confidence')}%
เหตุผลเบื้องต้น: {signal.get('reason')}

📈 ราคาที่เสนอเข้า: {trade.get('entry')} | SL เบื้องต้น: {trade.get('stop_loss')} | TP กลาง: {trade.get('take_profit')}
RR: {trade.get('risk_reward')} | Pip Risk: {trade.get('pip_risk')} | ขนาดล็อต: {trade.get('position_size')}

🧠 บริบทตลาด:
- ช่วงเวลา: {context.get('session')} | เทรนด์ H1: {context.get('h1_trend')} | ความแรงเทรนด์: {context.get('trend_strength')}
- RSI M15: {context.get('rsi_m15')} | ความผันผวน: {context.get('volatility_ratio')}

📉 ปัจจัยพื้นฐาน:
- DXY: Bearish={fundamentals.get('dxy_bearish')} / Bullish={fundamentals.get('dxy_bullish')}
- Bond Yield: Fall={fundamentals.get('yield_falling')} / Rise={fundamentals.get('yield_rising')}
- VIX: {fundamentals.get('vix_level')}

📐 โซนเทคนิค:
- EMA50/200 H1: {tech.get('ema50_h1')} / {tech.get('ema200_h1')}
- แนวรับ: {tech.get('support')} | แนวต้าน: {tech.get('resistance')}

กรุณาวิเคราะห์จากข้อมูลข้างต้น:
- บอกว่าเข้าออเดอร์ได้ไหม หรือควรรอก่อน
- ถ้าเข้าได้: กำหนด Entry, SL, TP1, TP2 ที่เหมาะสมจากโครงสร้างจริง (ไม่อิง RR อย่างเดียว)
- ให้ SL วางนอก zone ที่อาจโดน trap/wick
- TP1 เน้นปลอดภัย | TP2 ใช้ momentum ถ้าทางโล่ง
- เตือนถ้ามีโซนอันตราย เช่น fakeout, trap, RSI กลาง, vol ต่ำ, ชนโซนสำคัญ
- ระบุเวลาในการถือโดยประมาณ
"""

def ask_gpt(prompt):
    system_prompt = """
คุณคือ GoldScalpGPT — ผู้ช่วยวิเคราะห์ทองคำแบบมืออาชีพ (XAU/USD) โดยใช้ 3 ไทม์เฟรม:
- H1: เทรนด์หลัก
- M15: โครงสร้างการตั้งค่า
- M5: การยืนยันจุดเข้า

หน้าที่ของคุณ:
- วิเคราะห์ข้อมูลจากระบบ Pine Script ที่คัดกรองแล้ว
- ถ้าโครงสร้างพร้อม ให้ระบุ: เข้า BUY หรือ SELL
- กำหนด Entry, SL, TP1, TP2 อย่างมีเหตุผลตามโครงสร้างจริง
- ถ้าไม่พร้อม ให้บอกว่า WAIT พร้อมอธิบายสั้น ๆ
- อย่าเดา อย่า over-optimize
- ตอบให้มืออาชีพอ่านเข้าใจง่าย รัดกุม ไม่ขายฝัน
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
