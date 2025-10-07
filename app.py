import os
from flask import Flask, request, render_template
from dotenv import load_dotenv
from openai import OpenAI
from time import time

# Load environment variables
load_dotenv()

# --- Clear proxy settings that cause “proxies” errors ---
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Basic rate limiter ---
_BUCKET = {"tokens": 60, "ts": time()}
CAP = 60
REFILL = 60.0

def rate_limit():
    global _BUCKET
    now = time()
    elapsed = now - _BUCKET["ts"]
    if elapsed >= REFILL:
        _BUCKET["tokens"] = CAP
        _BUCKET["ts"] = now
    if _BUCKET["tokens"] <= 0:
        return False
    _BUCKET["tokens"] -= 1
    return True

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return "ok", 200

@app.post("/api/chat")
def chat():
    if not rate_limit():
        return ("Rate limit reached", 429)

    body = request.get_json(force=True) or {}
    messages = body.get("messages") or []

    system = (
        "You are Clinical Evidence Navigator Matt Adam Demo. "
        "Be concise. When asked for evidence, outline a PubMed and ClinicalTrials.gov "
        "search strategy with PMIDs/NCT IDs and links. Education only; no medical advice."
    )

    convo = [{"role": "system", "content": system}] + messages

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=convo,
        )
        text = resp.choices[0].message.content or ""
        return text, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        print("Error:", e)
        return f"Error: {e}", 500

if __name__ == "__main__":
    app.run(debug=True)
