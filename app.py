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
    # [ปรับปรุง] เพิ่มการตรวจสอบข้อมูลเบื้องต้น
    if not request.is_json:
        return jsonify({"status": "❌ Error", "message": "Request must be JSON"}), 400
        
    data = request.json
    symbol = data.get("symbol", "ไม่มีข้อมูล")
    alerts = data.get("alerts", [])
    time = data.get("time", "ไม่มีข้อมูล")

    # [ปรับปรุง] เช็คว่ามีข้อมูล alerts มาหรือไม่
    if not alerts:
        return jsonify({"status": "❌ Error", "message": "No alerts data found in payload"}), 400

    prompt = build_prompt(symbol, alerts, time)
    gpt_reply = ask_gpt(prompt)
    send_telegram_message(gpt_reply)

    return jsonify({"status": "✅ ส่งไป Telegram แล้ว", "GPT_ตอบว่า": gpt_reply}), 200

def build_prompt(symbol, alerts, time):
    # [ปรับปรุง] เปลี่ยน List of Dicts ให้เป็น Dict of Dicts เพื่อให้ดึงข้อมูลง่ายและเร็วกว่า
    # จาก O(n) กลายเป็น O(1) lookup
    alerts_by_tf = {alert.get("timeframe"): alert for alert in alerts}

    def extract_tf_data(tf):
        alert_data = alerts_by_tf.get(tf)
        if alert_data:
            return f"""- ประเภท: {alert_data.get("type", "N/A")}
- รูปแบบ: {alert_data.get("pattern", "N/A")}
- ราคา: {alert_data.get("price", "N/A")}"""
        return "ไม่มีข้อมูล"

    # prompt template เหมือนเดิม แต่เรียกใช้ฟังก์ชันที่ปรับปรุงแล้ว
    return f"""
วิเคราะห์ XAU/USD ตามกลยุทธ์ GoldScalpGPT:

📍 เวลา: {time}
📌 สัญลักษณ์: {symbol}

🔹 H1 Trend:
{extract_tf_data("H1")}

🔹 M15 Setup:
{extract_tf_data("M15")}

🔹 M5 Entry Confirm:
{extract_tf_data("M5")}

วิเคราะห์ให้ชัดเจน:
- ทิศทาง: BUY หรือ SELL
- จุดเข้า (Entry), SL, TP1, TP2
- เหตุผลเข้าออเดอร์ (Confluence)
- ความเสี่ยง (Risk)
- เวลาถือคร่าว ๆ (Holding Time)
❌ ถ้าโครงสร้างยังไม่ชัดเจน หรือข้อมูลจาก Timeframe ต่างๆ ขัดแย้งกัน: ให้ตอบว่า WAIT และอธิบายเหตุผลอย่างละเอียด
"""

def ask_gpt(prompt):
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "คุณคือ GoldScalpGPT — นักวิเคราะห์ผู้เชี่ยวชาญ XAU/USD วิเคราะห์ข้อมูลจาก 3 Timeframe (H1, M15, M5) เพื่อหาจุดเข้าเทรดที่ปลอดภัยและมีโอกาสชนะสูงสุด ให้คำตอบที่ชัดเจนและเป็นประโยชน์ต่อนักเทรด"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[❌ GPT ERROR]: {str(e)}"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"} # เพิ่ม parse_mode เพื่อให้ข้อความสวยขึ้น
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    # สำหรับใช้งานจริง (Production) ควรเปลี่ยน debug=False
    app.run(host="0.0.0.0", port=10000, debug=True)
