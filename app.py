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

# --- ระบบป้องกันสัญญาณซ้ำซ้อน (Deduplication Cache) ---
last_signal_cache = {
    "fingerprint": None,
    "timestamp": 0
}
DEDUPLICATION_WINDOW_SECONDS = 5 # ป้องกันสัญญาณซ้ำภายใน 5 วินาที
# -------------------------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return jsonify({"status": "❌ Error", "message": "Request must be JSON"}), 400
        
    data = request.json
    
    # --- ขั้นตอนการตรวจสอบและกรองสัญญาณซ้ำซ้อน ---
    current_fingerprint = str(data)
    current_timestamp = time.time()

    if (current_fingerprint == last_signal_cache["fingerprint"] and 
        current_timestamp - last_signal_cache["timestamp"] < DEDUPLICATION_WINDOW_SECONDS):
        
        print(f"Duplicate signal ignored: {current_fingerprint}")
        return jsonify({"status": "🟡 Ignored", "message": "Duplicate signal."}), 200

    last_signal_cache["fingerprint"] = current_fingerprint
    last_signal_cache["timestamp"] = current_timestamp
    print(f"New signal received: {current_fingerprint}")
    # -------------------------------------------------------------

    symbol = data.get("symbol", "N/A")
    alerts = data.get("alerts", [])
    # [แก้ไข] เปลี่ยนชื่อตัวแปร tv_time เป็น unix_timestamp เพื่อความชัดเจน
    unix_timestamp = data.get("time", 0) 

    if not alerts:
        return jsonify({"status": "❌ Error", "message": "No alerts data found."}), 400

    prompt = build_prompt(symbol, alerts, unix_timestamp)
    gpt_reply = ask_gpt(prompt)
    send_telegram_message(gpt_reply)

    return jsonify({"status": "✅ Sent to Telegram", "GPT_Response": gpt_reply}), 200

def build_prompt(symbol, alerts, unix_timestamp):
    alerts_by_tf = {alert.get("timeframe"): alert for alert in alerts}

    def extract_tf_data(tf):
        alert_data = alerts_by_tf.get(tf)
        if alert_data:
            return f"""- ประเภท: {alert_data.get("type", "N/A")} | รูปแบบ: {alert_data.get("pattern", "N/A")} | ราคา: {alert_data.get("price", "N/A")}"""
        return "ไม่มีข้อมูล"
        
    # [แก้ไข] แก้ไขวิธีแปลงเวลาให้ถูกต้อง
    readable_time = "N/A"
    if isinstance(unix_timestamp, (int, float)) and unix_timestamp > 0:
        # แปลงจาก Milliseconds (จาก TradingView) เป็น Seconds
        readable_time = datetime.fromtimestamp(unix_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')

    m5_alert = alerts_by_tf.get("M5", {})
    signal_type = m5_alert.get("type", "Unknown Signal")

    # [ปรับปรุง] จัดระเบียบ Prompt ให้อ่านง่ายขึ้น
    return f"""ข้อมูลจาก TradingView:
- สัญลักษณ์: {symbol}
- เวลา: {readable_time}
- ประเภทสัญญาณ: {signal_type}

ข้อมูลประกอบการวิเคราะห์:
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
- Scalp Signal: 5–15 นาที
- Structure Signal: 15–45 นาที

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
        error_message = f"[❌ GPT ERROR]: {str(e)}"
        print(error_message)
        return error_message

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    # สำหรับ Production แนะนำให้ใช้ Gunicorn หรือ Waitress แทน
    app.run(host="0.0.0.0", port=10000, debug=False)

