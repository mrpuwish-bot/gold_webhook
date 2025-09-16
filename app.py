import os
import time
import json
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
    try:
        raw_data = request.get_data(as_text=True)
        data = json.loads(raw_data)
    except Exception as e:
        print(f"Error parsing JSON from request body: {e}")
        print(f"Received raw data: {request.get_data(as_text=True)}")
        return jsonify({"status": "❌ Error", "message": "Failed to parse JSON body"}), 400

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
        print(f"An error occurred during processing: {e}")
        return jsonify({"status": "❌ Error", "message": str(e)}), 500

def build_prompt_from_pine(data):
    # ดึงข้อมูลทั้งหมด รวมถึง Market Structure ที่เพิ่มเข้ามาใหม่
    symbol = data.get("symbol", "N/A")
    timestamp = data.get("timestamp", 0)
    signal = data.get("signal", {})
    trade = data.get("trade_parameters", {})
    context = data.get("market_context", {})
    structure = data.get("market_structure", {}) # <-- ดึงข้อมูล Market Structure
    tech = data.get("technical_analysis", {})
    confidence_score = data.get("confidence_score", "N/A")
    risk = data.get("risk_assessment", {})
    
    readable_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S') if timestamp > 0 else "N/A"

    # สร้าง Prompt ที่ส่งข้อมูลสำคัญทั้งหมดให้ AI
    return f"""
📊 **ข้อมูลดิบ:**
- **สัญญาณ:** {signal.get("strategy")} {signal.get("type")}, Conf: {confidence_score}%
- **เทรนด์ H1:** {context.get("h1_trend")} ({context.get("trend_strength")})
- **รูปแบบ M5:** {context.get("m5_pattern")}
- **Session:** {context.get("trading_session")}
- **Volatility:** {context.get("volatility_percentile")}%
- **RSI M15:** {context.get("rsi_m15")}
- **ราคาเริ่มต้น:** Entry: {trade.get("entry")}, SL: {trade.get("sl")}, TP: {trade.get("tp")}

🏗️ **โครงสร้างตลาด (Market Structure):**
- **PDH:** {structure.get("prev_day_high", "N/A")}
- **PDL:** {structure.get("prev_day_low", "N/A")}
- **M15 Swing High:** {structure.get("m15_last_swing_high", "N/A")}
- **M15 Swing Low:** {structure.get("m15_last_swing_low", "N/A")}

🧠 **ภารกิจ:**
วิเคราะห์ข้อมูลทั้งหมด โดยเฉพาะข้อมูล 'โครงสร้างตลาด' เพื่อสร้างแผนการเทรดที่สมบูรณ์ แล้วสรุปตามรูปแบบของ System Prompt
"""

def ask_gpt(prompt):
    system_prompt = """
คุณคือ GoldScalpGPT — **นักวิเคราะห์และวางแผนกลยุทธ์** ที่เชี่ยวชาญทองคำ หน้าที่ของคุณคือวิเคราะห์ข้อมูลที่ได้รับทั้งหมด แล้วสรุปออกมาให้ **กระชับและเข้าใจง่ายที่สุด** สำหรับเทรดเดอร์มืออาชีพ

**รูปแบบการตอบที่ต้องใช้เท่านั้น:**

1.  **[อีโมจิสถานะ] สรุป (Executive Summary):** 1 ประโยคจบ บอกภาพรวมของสัญญาณ
2.  **✅ ปัจจัยสนับสนุน (Pros):** (ลิสต์เป็นข้อๆ ไม่เกิน 2 ข้อ)
3.  **⚠️ ข้อควรระวัง (Cons):** (ลิสต์เป็นข้อๆ ไม่เกิน 2 ข้อ)
4.  **🎯 แผนการเทรด (Plan):**
    - Entry: [ราคา]
    - SL: [ราคา]
    - TP1: [ราคา]
    - TP2: [ราคา]

**สำคัญ:** ต้องตอบเป็นภาษาไทยและอยู่ในรูปแบบนี้เท่านั้น **ต้องใช้ข้อมูล 'โครงสร้างตลาด' (PDH/PDL/Swings) ในการกำหนด SL และ TP ใหม่เสมอ ห้ามคัดลอกแผนการเทรดจากข้อมูลดิบ**
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
    app.run(host="host="0.0.0.0", port=10000, debug=False)
