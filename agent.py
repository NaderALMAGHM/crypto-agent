import yfinance as yf
import requests
import os
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

COINS = [
    ("BTC-USD", "bitcoin"),
    ("ETH-USD", "ethereum"),
    ("SOL-USD", "solana"),
    ("BNB-USD", "bnb"),
    ("ADA-USD", "cardano"),
]

def get_crypto_data(symbol):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="3mo")
    df.columns = [c.lower() for c in df.columns]
    return df[['open','high','low','close','volume']]

def add_indicators(df):
    close = df['close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
    return df

def run_ai_analysis(df, symbol):
    price = df['close'].iloc[-1]
    change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    rsi = df['RSI'].iloc[-1]

    prompt = f"""Analyze {symbol}:
- Price: ${price:.2f}
- 24h Change: {change:.2f}%
- RSI: {rsi:.1f}

Reply ONLY in this format:
Recommendation: [BUY/SELL/WAIT]
Confidence: [XX%]
Reason: [one sentence]
Risk: [LOW/MEDIUM/HIGH]"""

    models = ["gemini-2.5-flash", "gemini-1.5-flash"]
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200}
            }, timeout=20)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except:
            continue

    if rsi < 35:   return "Recommendation: BUY\nConfidence: 65%\nReason: RSI oversold.\nRisk: MEDIUM"
    elif rsi > 70: return "Recommendation: SELL\nConfidence: 65%\nReason: RSI overbought.\nRisk: HIGH"
    else:          return "Recommendation: WAIT\nConfidence: 50%\nReason: Mixed signals.\nRisk: MEDIUM"

def parse_ai(text):
    result = {"recommendation": "WAIT", "confidence": "50%", "reason": "-", "risk": "MEDIUM"}
    for line in text.splitlines():
        if "Recommendation:" in line: result["recommendation"] = line.split(":")[-1].strip()
        elif "Confidence:"    in line: result["confidence"]    = line.split(":")[-1].strip()
        elif "Reason:"        in line: result["reason"]        = line.split(":",1)[-1].strip()
        elif "Risk:"          in line: result["risk"]          = line.split(":")[-1].strip()
    return result

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except: pass

def run_full_analysis():
    results = []
    tg_msg = f"<b>Crypto Daily Report</b>\n{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    for symbol, coin_name in COINS:
        try:
            df = get_crypto_data(symbol)
            df = add_indicators(df)
            price  = df['close'].iloc[-1]
            change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
            rsi    = df['RSI'].iloc[-1]
            macd   = df['MACD'].iloc[-1]
            ai_raw = run_ai_analysis(df, symbol)
            ai     = parse_ai(ai_raw)

            results.append({
                "symbol": symbol,
                "name": coin_name.capitalize(),
                "price": round(price, 4),
                "change": round(change, 2),
                "rsi": round(rsi, 1),
                "macd": round(macd, 4),
                **ai
            })

            em = "🟢" if ai["recommendation"] == "BUY" else "🔴" if ai["recommendation"] == "SELL" else "🟡"
            tg_msg += f"{em} <b>{coin_name.upper()}</b> ${price:,.2f} ({change:+.1f}%)\n"
            tg_msg += f"   {ai['recommendation']} · {ai['confidence']} · Risk: {ai['risk']}\n\n"

        except Exception as e:
            print(f"Error {symbol}: {e}")

    send_telegram(tg_msg)
    return results