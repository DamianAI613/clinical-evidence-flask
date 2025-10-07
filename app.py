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
    "You are a clinical evidence assistant. When a user asks a question, "
    "you will: (1) create a PubMed query (MeSH + keywords), "
    "(2) create a ClinicalTrials.gov query, "
    "(3) list a few PMIDs/NCT IDs if possible, "
    "(4) summarize the main findings clearly. "
    "Always remind users this is for education only."
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
import requests
from urllib.parse import urlencode

BASE_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_KEY = os.getenv("NCBI_API_KEY")
CTG_V2 = "https://clinicaltrials.gov/api/v2/studies"

def eutils_params(**kw):
    params = {k: v for k, v in kw.items() if v is not None}
    if NCBI_KEY:
        params["api_key"] = NCBI_KEY
    return params

@app.post("/api/pubmed/search")
def pubmed_search():
    body = request.get_json(force=True)
    term = body.get("term", "")
    retmax = body.get("retmax", 20)
    sort = body.get("sort", "pub+date")
    params = eutils_params(db="pubmed", term=term, retmode="json", retmax=retmax, sort=sort)
    url = f"{BASE_EUTILS}/esearch.fcgi?{urlencode(params)}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    j = r.json()
    return {
        "pmids": j.get("esearchresult", {}).get("idlist", []),
        "count": j.get("esearchresult", {}).get("count"),
        "endpoint": url
    }

@app.post("/api/pubmed/fetch")
def pubmed_fetch():
    body = request.get_json(force=True)
    pmids = body.get("pmids") or []
    if not pmids: return ("Missing pmids", 400)
    params = eutils_params(db="pubmed", retmode="json", id=",".join(pmids))
    url = f"{BASE_EUTILS}/esummary.fcgi?{urlencode(params)}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    j = r.json()
    result = [v for k, v in j.get("result", {}).items() if k != "uids"]
    return {"items": result, "endpoint": url}

@app.post("/api/ctgov/search")
def ctgov_search():
    body = request.get_json(force=True)
    query = body.get("query")
    page_size = body.get("pageSize", 20)
    params = {"query": query, "pageSize": page_size}
    url = f"{CTG_V2}?{urlencode(params)}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    return r.json()

# ----- Evidence fetch helpers (PubMed + CT.gov) -----
import requests
from urllib.parse import urlencode

BASE_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_KEY = os.getenv("NCBI_API_KEY")
CTG_V2 = "https://clinicaltrials.gov/api/v2/studies"

def eutils_params(**kw):
    params = {k: v for k, v in kw.items() if v is not None}
    if NCBI_KEY:
        params["api_key"] = NCBI_KEY
    return params

@app.post("/api/pubmed/fetch")
def pubmed_fetch():
    body = request.get_json(force=True)
    pmids = body.get("pmids") or []
    if not pmids: return ("Missing pmids", 400)
    params = eutils_params(db="pubmed", retmode="json", id=",".join(pmids))
    url = f"{BASE_EUTILS}/esummary.fcgi?{urlencode(params)}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    j = r.json()
    items = [v for k, v in j.get("result", {}).items() if k != "uids"]
    # Minimal fields we’ll render in the table
    out = []
    for it in items:
        out.append({
            "pmid": str(it.get("uid","")),
            "title": it.get("title",""),
            "source": it.get("fulljournalname") or it.get("source",""),
            "year": it.get("pubdate","")[:4],
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{it.get('uid','')}/"
        })
    return {"items": out}

@app.post("/api/ctgov/fetch")
def ctgov_fetch():
    body = request.get_json(force=True)
    nct_ids = body.get("nctIds") or []
    if not nct_ids: return ("Missing nctIds", 400)
    q = " OR ".join(f"NCTId:{i}" for i in nct_ids)
    params = {"query": q, "pageSize": len(nct_ids), "fields": "NCTId,BriefTitle,OverallStatus,Phase"}
    url = f"{CTG_V2}?{urlencode(params)}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    data = r.json().get("studies", [])
    items = []
    for s in data:
        rec = {f["field"]: f["value"] for f in s.get("protocolSection", {}).get("identificationModule", {}).get("orgStudyIdInfo", [])}
        nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId") or s.get("studies", [{}])[0].get("NCTId")
        items.append({
            "nct": s.get("protocolSection", {}).get("identificationModule", {}).get("nctId") or s.get("NCTId"),
            "title": s.get("protocolSection", {}).get("identificationModule", {}).get("briefTitle") or s.get("BriefTitle"),
            "status": s.get("protocolSection", {}).get("statusModule", {}).get("overallStatus") or s.get("OverallStatus"),
            "phase": (s.get("protocolSection", {}).get("designModule", {}) or {}).get("phases") or s.get("Phase"),
        })
    # Fallback simple parser if v2 shape varies
    if not items and "studies" in (r.json() or {}):
        items = [{"nct": x.get("NCTId"), "title": x.get("BriefTitle"), "status": x.get("OverallStatus"), "phase": x.get("Phase")} for x in r.json()["studies"]]
    # Add links
    for it in items:
        if it.get("nct"):
            it["link"] = f"https://clinicaltrials.gov/study/{it['nct']}"
    return {"items": items}


if __name__ == "__main__":
    app.run(debug=True)
