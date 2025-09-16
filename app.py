import os
import time
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from openai import OpenAI
import requests
from dotenv import load_dotenv

# --- SETUP ---
# Load environment variables
load_dotenv()

# Configure logging to be more informative
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- INITIALIZE FLASK APP AND SERVICES ---
app = Flask(__name__)

# --- CONFIGURATION ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GPT_MODEL = "gpt-4o"

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# --- CACHE FOR DEDUPLICATION ---
last_signal_cache = {
    "fingerprint": None,
    "timestamp": 0
}
DEDUPLICATION_WINDOW_SECONDS = 5 # Ignore identical signals within 5 seconds

# ==============================================================================
# === MAIN WEBHOOK ENDPOINT ====================================================
# ==============================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Receives, processes, and acts on signals from TradingView."""
    
    raw_data = request.get_data(as_text=True)
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        logging.error("🔴 JSON DECODE ERROR: %s", e.msg)
        logging.error("   Error at Line: %d, Column: %d", e.lineno, e.colno)
        logging.error("   Received Raw Data: %s", raw_data)
        return jsonify({
            "status": "❌ Error", 
            "message": "Failed to parse JSON body.",
            "error_details": f"{e.msg} (at line {e.lineno} col {e.colno})"
        }), 400

    # --- Deduplication Logic ---
    current_fingerprint = str(data)
    current_timestamp = time.time()
    
    if (current_fingerprint == last_signal_cache["fingerprint"] and
        current_timestamp - last_signal_cache["timestamp"] < DEDUPLICATION_WINDOW_SECONDS):
        logging.info("🟡 Duplicate signal ignored: %s", current_fingerprint)
        return jsonify({"status": "🟡 Ignored", "message": "Duplicate signal."}), 200

    # Update cache
    last_signal_cache["fingerprint"] = current_fingerprint
    last_signal_cache["timestamp"] = current_timestamp
    logging.info("✅ New signal received: %s", json.dumps(data, indent=2))

    # --- Main Processing Logic ---
    try:
        prompt = build_prompt_from_pine(data)
        gpt_reply = ask_gpt(prompt)
        send_telegram_message(gpt_reply)
        logging.info("✅ Signal successfully processed and sent to Telegram.")
        return jsonify({"status": "✅ Sent to Telegram", "GPT_Response": gpt_reply}), 200
    except Exception as e:
        logging.error("🔴 An unexpected error occurred during processing: %s", e, exc_info=True)
        return jsonify({"status": "❌ Error", "message": str(e)}), 500

# ==============================================================================
# === HELPER FUNCTIONS =========================================================
# ==============================================================================

def build_prompt_from_pine(data):
    """Constructs a detailed prompt for OpenAI based on the received signal data."""
    symbol = data.get("symbol", "N/A")
    signal = data.get("signal", {})
    trade = data.get("trade_parameters", {})
    context = data.get("market_context", {})
    structure = data.get("market_structure", {})
    confidence_score = data.get("confidence_score", "N/A")
    
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
    """Sends the prompt to OpenAI and returns the response."""
    # ✅ UPGRADE: Made the instructions for the first line more specific and clear.
    system_prompt = """
คุณคือ GoldScalpGPT — นักวิเคราะห์และวางแผนกลยุทธ์ที่เชี่ยวชาญทองคำ หน้าที่ของคุณคือวิเคราะห์ข้อมูลทั้งหมด แล้วสรุปออกมาให้กระชับและเข้าใจง่ายที่สุดสำหรับเทรดเดอร์มืออาชีพ

**รูปแบบการตอบที่ต้องใช้เท่านั้น:**

1.  **[อีโมจิสัญญาณ] ประเภทสัญญาณ | [BUY/SELL] ด้วยกลยุทธ์ [ชื่อกลยุทธ์]:** สรุปภาพรวมของสัญญาณ 1 ประโยค
2.  **📈 คุณภาพสัญญาณ (Signal Grade):** [ให้เกรด A+, A, B+, B, C] พร้อมเหตุผลสั้นๆ
3.  **✅ ปัจจัยสนับสนุน (Pros):** (ลิสต์เป็นข้อๆ ไม่เกิน 2 ข้อ)
4.  **⚠️ ข้อควรระวัง (Cons):** (ลิสต์เป็นข้อๆ ไม่เกิน 2 ข้อ)
5.  **🎯 แผนการเทรด (Plan):**
    - Entry: [ราคา]
    - SL: [ราคา]
    - TP1: [ราคา]
    - TP2: [ราคา]
    - **R:R (TP2):** [คำนวณและประเมิน Risk:Reward Ratio สำหรับ TP2]
6.  **💡 คำแนะนำเพิ่มเติม (Pro-Tip):** [เช่น "ควรเลื่อน SL มากันทุนเมื่อถึง TP1" หรือ "ระวังข่าว Non-farm คืนนี้"]

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
    """Sends the formatted message to the specified Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        logging.error("🔴 Telegram API ERROR: %s", e)

# ==============================================================================
# === APP ROUTES & RUNNER ======================================================
# ==============================================================================
@app.route('/')
def hello():
    """A simple route to confirm the server is running."""
    logging.info("Health check successful.")
    return "Hello, Render! The webhook server is running."

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
