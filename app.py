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
    tv_message = data.get("message", "ไม่มีข้อความจาก TradingView")
    gpt_reply = ask_gpt(tv_message)
    send_telegram_message(gpt_reply)
    return jsonify({"status": "✅ ส่งไป Telegram แล้ว", "GPT_ตอบว่า": gpt_reply}), 200

def ask_gpt(prompt):
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": """คุณคือ GoldScalpGPT — ผู้ช่วยเทรด XAU/USD แบบมืออาชีพ ด้วยกลยุทธ์ที่ใช้การวิเคราะห์ Timeframe H1, M15, M5 เพื่อหาจุดเข้าออกที่ปลอดภัยที่สุด:

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

❌ ห้ามเดา ❌ ห้ามชี้สัญญาณถ้าโครงสร้างยังไม่ชัด

นี่คือลักษณะของข้อความจาก TradingView: จะให้คุณวิเคราะห์ “สถานการณ์ราคา” แบบสด ๆ"""},
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
    app.run(debug=True)
