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
    data = request.json
    symbol = data.get("symbol", "XAUUSD")
    alerts = data.get("alerts", [])
    time = data.get("time", "unknown")

    prompt = build_prompt(symbol, alerts, time)
    gpt_reply = ask_gpt(prompt)
    send_telegram_message(gpt_reply)

    return jsonify({"status": "✅ ส่งไป Telegram แล้ว", "GPT_ตอบว่า": gpt_reply}), 200

def build_prompt(symbol, alerts, time):
    def extract_tf(tf):
        for alert in alerts:
            if alert.get("timeframe") == tf:
                return f"""- ประเภท: {alert.get("type")}
- รูปแบบ: {alert.get("pattern")}
- ราคา: {alert.get("price")}"""
        return "ไม่มีข้อมูล"

    return f"""
วิเคราะห์ XAU/USD ตามกลยุทธ์ GoldScalpGPT:

📍 เวลา: {time}
📌 สัญลักษณ์: {symbol}

🔹 H1 Trend:
{extract_tf("H1")}

🔹 M15 Setup:
{extract_tf("M15")}

🔹 M5 Entry Confirm:
{extract_tf("M5")}

วิเคราะห์ให้ชัดเจน:
- ทิศทาง: BUY หรือ SELL
- จุดเข้า (Entry), SL, TP1, TP2
- เหตุผลเข้าออเดอร์
- เวลาถือคร่าว ๆ
❌ ถ้าโครงสร้างยังไม่ชัด: ให้ตอบว่า WAIT และอธิบายเหตุผล
"""

def ask_gpt(prompt):
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "คุณคือ GoldScalpGPT — วิเคราะห์โครงสร้าง XAU/USD ด้วย 3 Timeframe: H1, M15, M5 เพื่อตัดสินใจเข้าเทรดที่ปลอดภัยที่สุด"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[❌ GPT ERROR]: {str(e)}"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[❌ Telegram ERROR]: {str(e)}")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
