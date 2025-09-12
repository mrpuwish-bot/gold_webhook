import os
import time
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

# --- [ใหม่] ระบบป้องกันสัญญาณซ้ำซ้อน (Deduplication Cache) ---
# สร้าง "ความจำ" ให้เซิร์ฟเวอร์ เพื่อจำสัญญาณล่าสุดที่ได้รับ
last_signal_cache = {
    "fingerprint": None,
    "timestamp": 0
}
# กำหนดช่วงเวลาที่จะถือว่าเป็นสัญญาณซ้ำ (เช่น 5 วินาที)
DEDUPLICATION_WINDOW_SECONDS = 5
# -------------------------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return jsonify({"status": "❌ Error", "message": "Request must be JSON"}), 400
        
    data = request.json
    
    # --- [ใหม่] ขั้นตอนการตรวจสอบและกรองสัญญาณซ้ำซ้อน ---
    # 1. สร้าง "ลายนิ้วมือ" ที่ไม่ซ้ำกันสำหรับสัญญาณนี้โดยใช้ข้อมูลทั้งหมด
    current_fingerprint = str(data)
    current_timestamp = time.time()

    # 2. ตรวจสอบกับ "ความจำ" ของเซิร์ฟเวอร์
    if (current_fingerprint == last_signal_cache["fingerprint"] and 
        current_timestamp - last_signal_cache["timestamp"] < DEDUPLICATION_WINDOW_SECONDS):
        
        # 3. ถ้าเป็นสัญญาณซ้ำ ให้ตอบกลับว่า "ละเว้น" แล้วหยุดทำงานทันที
        print(f"Duplicate signal ignored: {current_fingerprint}")
        return jsonify({"status": "🟡 Ignored", "message": "Duplicate signal received within the cooldown window."}), 200

    # 4. ถ้าเป็นสัญญาณใหม่ ให้ "จดจำ" สัญญาณนี้ไว้ แล้วทำงานต่อ
    last_signal_cache["fingerprint"] = current_fingerprint
    last_signal_cache["timestamp"] = current_timestamp
    print(f"New signal received: {current_fingerprint}")
    # -------------------------------------------------------------

    symbol = data.get("symbol", "ไม่มีข้อมูล")
    alerts = data.get("alerts", [])
    tv_time = data.get("time", "ไม่มีข้อมูล")

    if not alerts:
        return jsonify({"status": "❌ Error", "message": "No alerts data found in payload"}), 400

    m5_alert = next((alert for alert in alerts if alert.get("timeframe") == "M5"), {})
    signal_type = m5_alert.get("type", "Unknown Signal")

    prompt = build_prompt(symbol, alerts, tv_time, signal_type)
    gpt_reply = ask_gpt(prompt)
    send_telegram_message(gpt_reply)

    return jsonify({"status": "✅ Sent to Telegram", "GPT_Response": gpt_reply}), 200

def build_prompt(symbol, alerts, time, signal_type):
    alerts_by_tf = {alert.get("timeframe"): alert for alert in alerts}

    def extract_tf_data(tf):
        alert_data = alerts_by_tf.get(tf)
        if alert_data:
            return f"""- ประเภท: {alert_data.get("type", "N/A")}
- รูปแบบ: {alert_data.get("pattern", "N/A")}
- ราคา: {alert_data.get("price", "N/A")}"""
        return "ไม่มีข้อมูล"
        
    # แปลง Unix timestamp จาก Pine Script (milliseconds) เป็นเวลาที่อ่านง่าย
    readable_time = "N/A"
    if isinstance(time, (int, float)):
        readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time / 1000))

    return f"""ข้อมูลจาก TradingView:
- สัญลักษณ์: {symbol}
- เวลา: {readable_time}
- ประเภทสัญญาณ: {signal_type}
- H1 Trend: {extract_tf_data("H1")}
- M15 Setup: {extract_tf_data("M15")}
- M5 Entry: {extract_tf_data("M5")}
"""

def ask_gpt(prompt):
    system_prompt = """คุณคือ GoldScalpGPT — ผู้ช่วยเทรด XAU/USD แบบมืออาชีพ ด้วยกลยุทธ์ที่ใช้การวิเคราะห์ Timeframe H1, M15, M5 เพื่อหาจุดเข้าออกที่ปลอดภัยที่สุด:

🔁 กรอบการวิเคราะห์:
- H1 = เทรนด์หลัก (Trend)
- M15 = โครงสร้างการตั้งค่า (Setup)
- M5 = จุดเข้า (Entry Confirmation)

📊 สิ่งที่ต้องวิเคราะห์:
- มี trap หรือ wick ยาวผิดปกติไหม?
- มีการ fake breakout, stop hunt, หรือ liquidity grab หรือไม่?
- มีแรง reject ที่ zone supply/demand หรือไม่?
- ราคาเบรกแนวไหนแล้วยังไม่มี follow-through หรือไม่?

✅ ถ้าเห็นว่าพร้อมเข้าออเดอร์:
- ให้คำตอบสั้น ๆ: BUY หรือ SELL
- บอกราคาเข้า (Entry Price) ที่แนะนำ
- บอก SL และ TP โดยประมาณ เช่น SL = xxx, TP1 = xxx, TP2 = xxx
- คำอธิบายเหตุผล 1–2 บรรทัด

🕐 ระบุเวลาถือตามประเภท:
- Scalp: 5–15 นาที
- โครงสร้าง: 15–45 นาที

❌ ห้ามเดา ❌ ห้ามชี้สัญญาณถ้าโครงสร้างยังไม่ชัด"""
    
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[❌ GPT ERROR]: {str(e)}")
        return f"[❌ GPT ERROR]: {str(e)}"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=False)

