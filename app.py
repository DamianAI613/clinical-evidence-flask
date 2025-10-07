import os
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
from openai import OpenAI
from time import time

load_dotenv()

app = Flask(__name__)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

@app.post("/api/chat")
def chat():
    if not rate_limit():
        return ("Rate limit", 429)
    body = request.get_json(force=True) or {}
    messages = body.get("messages") or []
    system = (
        "You are Clinical Evidence Navigator Matt Adam Demo. "
        "Be concise. When asked for evidence, outline a PubMed and ClinicalTrials.gov search. "
        "Education only; no medical advice."
    )
    convo = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=convo,
    )
    return resp.choices[0].message.content or ""
    
if __name__ == "__main__":
    app.run(debug=True)
