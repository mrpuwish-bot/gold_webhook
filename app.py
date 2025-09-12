from flask import Flask, request, jsonify
from openai import OpenAI
import requests
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GPT_MODEL = "gpt-4o"

client = OpenAI(api_key=OPENAI_API_KEY)

@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return jsonify({"status": "❌ Error", "message": "Request must be JSON"}), 400
        
    data = request.json
    symbol = data.get("symbol", "ไม่มีข้อมูล")
    alerts = data.get("alerts", [])
    time = data.get("time", "ไม่มีข้อมูล")

    if not alerts:
        return jsonify({"status": "❌ Error", "message": "No alerts data found in payload"}), 400

    # [ใหม่] ดึงข้อมูล "ประเภทสัญญาณ" จาก M5 alert
    m5_alert = next((alert for alert in alerts if alert.get("timeframe") == "M5"), {})
    signal_type = m5_alert.get("type", "Unknown Signal") # e.g., "Scalp Signal" or "Structure Signal"

    prompt = build_prompt(symbol, alerts, time, signal_type) # ส่งประเภทสัญญาณเข้าไปใน prompt
    gpt_reply = ask_gpt(prompt)
    send_telegram_message(gpt_reply)

    return jsonify({"status": "✅ ส่งไป Telegram แล้ว", "GPT_ตอบว่า": gpt_reply}), 200

def build_prompt(symbol, alerts, time, signal_type):
    alerts_by_tf = {alert.get("timeframe"): alert for alert in alerts}

    def extract_tf_data(tf):
        alert_data = alerts_by_tf.get(tf)
        if alert_data:
            return f"""- ประเภท: {alert_data.get("type", "N/A")}
- รูปแบบ: {alert_data.get("pattern", "N/A")}
- ราคา: {alert_data.get("price", "N/A")}"""
        return "ไม่มีข้อมูล"

    # [ปรับปรุง] เพิ่ม signal_type เข้าไปใน prompt เพื่อให้ GPT รู้บริบท
    return f"""
ข้อมูลจาก TradingView:

- สัญลักษณ์: {symbol}
- เวลา: {time}
- ประเภทสัญญาณ: {signal_type}

- H1 Trend:
{extract_tf_data("H1")}

- M15 Setup:
{extract_tf_data("M15")}

- M5 Entry Confirm:
{extract_tf_data("M5")}
"""

def ask_gpt(prompt):
    try:
        # [อัปเกรด] เปลี่ยน System Prompt เป็นเวอร์ชันใหม่ที่คุณออกแบบ
        system_prompt = """คุณคือ GoldScalpGPT — ผู้ช่วยเทรด XAU/USD แบบมืออาชีพ ด้วยกลยุทธ์ที่ใช้การวิเคราะห์ Timeframe H1, M15, M5 เพื่อหาจุดเข้าออกที่ปลอดภัยที่สุด:

🔁 กรอบการวิเคราะห์:
- H1 = เทรนด์หลัก (Trend)
- M15 = โครงสร้างการตั้งค่า (Setup)
- M5 = จุดเข้า (Entry Confirmation)

📊 สิ่งที่คุณต้องวิเคราะห์จากข้อมูลที่ได้รับ:
- มีสัญญาณของ trap หรือ wick ยาวผิดปกติไหม?
- มีความเป็นไปได้ที่จะเกิด fake breakout, stop hunt, หรือ liquidity grab หรือไม่?
- มีแรง reject ที่โซน supply/demand ที่สำคัญหรือไม่?

✅ ถ้าเห็นว่าพร้อมเข้าออเดอร์:
- ให้คำตอบสั้น ๆ: **BUY** หรือ **SELL**
- บอกราคาเข้า (Entry Price) ที่แนะนำ
- บอก SL และ TP โดยประมาณ เช่น SL = xxx, TP1 = xxx, TP2 = xxx
- คำอธิบายเหตุผล 1–2 บรรทัด

🕐 ระบุเวลาถือตามประเภทสัญญาณที่ได้รับ:
- ถ้าเป็น "Scalp Signal": 5–15 นาที
- ถ้าเป็น "Structure Signal": 15–45 นาที

❌ **กฎเหล็ก: ห้ามเดา!** หากโครงสร้างยังไม่ชัดเจน หรือข้อมูลจาก Timeframe ต่างๆ ขัดแย้งกัน ให้ตอบว่า **WAIT** และอธิบายเหตุผลสั้นๆ"""

        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[❌ GPT ERROR]: {str(e)}"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
