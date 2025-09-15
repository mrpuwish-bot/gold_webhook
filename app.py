import os
import time
import json # <-- 1. เพิ่มการ import json
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
    # --- 2. แก้ไขส่วนการรับข้อมูลให้ยืดหยุ่นขึ้น ---
    try:
        # รับข้อมูลดิบ (raw body) ที่เป็น text แล้วแปลงเป็น JSON ด้วยตัวเอง
        raw_data = request.get_data(as_text=True)
        data = json.loads(raw_data)
    except Exception as e:
        # ถ้าแปลงไม่ได้ แสดงว่าข้อมูลที่ส่งมาไม่ใช่ JSON จริงๆ
        print(f"Error parsing JSON from request body: {e}")
        print(f"Received raw data: {request.get_data(as_text=True)}") # แสดงข้อมูลดิบที่ได้รับเพื่อ debug
        return jsonify({"status": "❌ Error", "message": "Failed to parse JSON body"}), 400
    # --- จบส่วนที่แก้ไข ---

    # ส่วนที่เหลือของโค้ดทำงานเหมือนเดิม
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
        print(f"An error occurred during processing: {e}") # เพิ่มการ print error เพื่อให้ debug ง่ายขึ้น
        return jsonify({"status": "❌ Error", "message": str(e)}), 500

def build_prompt_from_pine(data):
    symbol = data.get("symbol", "N/A")
    timestamp = data.get("timestamp", 0)
    signal = data.get("signal", {})
    trade = data.get("trade_parameters", {})
    context = data.get("market_context", {})
    tech = data.get("technical_analysis", {})
    confidence_score = data.get("confidence_score", "N/A")
    risk = data.get("risk_assessment", {})
    metadata = data.get("metadata", {})

    readable_time = "N/A"
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        readable_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')

    return f"""
📊 ข้อมูลวิเคราะห์จาก Pine Script สำหรับทองคำ (XAU/USD)

🕒 เวลา: {readable_time}
สัญลักษณ์: {symbol}
กลยุทธ์: {signal.get("strategy")} | ประเภท: {signal.get("type")} | เหตุผล: {signal.get("reason")}
Confidence Score: {confidence_score}%

🎯 Trade Plan
- Entry: {trade.get("entry")}
- SL: {trade.get("sl")}
- TP: {trade.get("tp")}
- RR Ratio: {trade.get("rr_ratio")}
- Pip Risk: {trade.get("pip_risk")}
- Risk %: {trade.get("risk_pct")}

📉 Market Context
- H1 เทรนด์: {context.get("h1_trend")} ({context.get("trend_strength")})
- EMA50 H1: {context.get("ema50_h1")}, EMA200 H1: {context.get("ema200_h1")}
- EMA Distance: 50={context.get("ema50_distance")}, 200={context.get("ema200_distance")}
- ATR M15: {context.get("atr_m15")} | Volatility: {context.get("volatility_percentile")}%
- RSI M15: {context.get("rsi_m15")}
- Pattern M5: {context.get("m5_pattern")}
- Session: {context.get("trading_session")}
- Pullback Depth: {context.get("pullback_depth")}
- Support: {context.get("support_level")}, Resistance: {context.get("resistance_level")}

📌 Technical
- Divergence: {tech.get("divergence_present")} ({tech.get("divergence_type")})
- BB Position: {tech.get("bb_position")}
- Price vs EMA50: {tech.get("price_vs_ema50")}
- Volatility Regime: {tech.get("volatility_regime")}
- Confluence Factors: {tech.get("confluence_factors")}

📊 Risk Assessment
- Session Quality: {risk.get("session_quality")}
- Trend Alignment: {risk.get("trend_alignment")}
- Volatility Favorable: {risk.get("volatility_favorable")}

🧠 บทบาทของคุณ:
- วิเคราะห์ว่าควรเข้าออเดอร์ไหม
- ถ้าเข้า: ให้ Entry, SL, TP1, TP2 ตามโครงสร้างจริง
- อย่าตั้ง SL/TP จาก RR อย่างเดียว ให้อิงแนวรับแนวต้าน
- เน้น TP1 ปลอดภัย, TP2 ใช้ momentum
- เตือนถ้ามีสัญญาณเสี่ยง เช่น wick trap, sideway, vol ต่ำ
- บอกด้วยว่าเป็น scalp หรือ hold กี่นาที
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
