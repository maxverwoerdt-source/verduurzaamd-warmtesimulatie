import hmac
import math
import os
import re
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request

from engine import calculate as calculate_python_model

BASE_DIR = Path(__file__).resolve().parent
SECRET_PATH = os.environ.get("APP_SECRET_PATH", "")

if not SECRET_PATH or not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", SECRET_PATH):
    raise RuntimeError("Stel APP_SECRET_PATH in op een willekeurige tekenreeks van minimaal 20 tekens.")

app = Flask(__name__)

# Render persistent disk should be mounted at /var/data. If not available, logs
# remain local to the container (and are lost on redeploy/restart).
LOG_DIR = Path(os.getenv("LOG_DIR", "/var/data" if Path("/var/data").exists() else str(BASE_DIR / "data")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_DB = LOG_DIR / "calculations.sqlite3"

def _init_log_db():
    with sqlite3.connect(LOG_DB, timeout=20) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS calculations (
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, duration_seconds REAL, inputs_json TEXT NOT NULL,
            selected_sources TEXT NOT NULL, error TEXT)""")
        db.commit()

def _log_start(inputs):
    calc_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(LOG_DB, timeout=20) as db:
        db.execute("INSERT INTO calculations(id,started_at,status,inputs_json,selected_sources) VALUES(?,?,?,?,?)",
                   (calc_id, started, "running", json.dumps(inputs, ensure_ascii=False), json.dumps(inputs.get("sources", []))))
        db.commit()
    return calc_id, perf_counter()

def _log_finish(calc_id, started_clock, status, error=None):
    finished = datetime.now(timezone.utc).isoformat()
    duration = round(perf_counter() - started_clock, 3)
    with sqlite3.connect(LOG_DB, timeout=20) as db:
        db.execute("UPDATE calculations SET finished_at=?,status=?,duration_seconds=?,error=? WHERE id=?",
                   (finished, status, duration, (error or "")[:1500], calc_id))
        db.commit()

_init_log_db()

DEFAULTS = {
    "aantal_woningen": 1000,
    "warmtevraag": 30,
    "gasprijs_2030": 5.00,
    "eprijs_2030": 0.25,
    "rendementseis": 6.0,
    "subsidie": 5000,
    "prijs_per_ton_co2": 100,
    "netverzwaring_kosten": 50,
    "dorp_stad_factor": 30,
    "perc_appartementen": 80,
}

LIMITS = {
    "aantal_woningen": (1, 100000),
    "warmtevraag": (1, 200),
    "gasprijs_2030": (0, 10),
    "eprijs_2030": (0, 5),
    "rendementseis": (0, 25),
    "subsidie": (0, 50000),
    "prijs_per_ton_co2": (0, 2000),
    "netverzwaring_kosten": (0, 10000),
    "dorp_stad_factor": (0, 100),
    "perc_appartementen": (0, 100),
}


def _validate(payload):
    clean = {}
    for key, (low, high) in LIMITS.items():
        try:
            raw = payload.get(key, DEFAULTS[key])
            if isinstance(raw, bool):
                raise ValueError
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Controleer het invoerveld '{key}'.")
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"'{key}' moet tussen {low} en {high} liggen.")
        clean[key] = int(value) if key == "aantal_woningen" else value
    allowed_sources = {"TEA", "TEO", "CLWP", "OGEO", "REST", "PVT", "SOLAR", "P2H", "GK", "LWP", "HWP"}
    selected_sources = payload.get("sources")
    if selected_sources is None:
        selected_sources = list(allowed_sources)
    if not isinstance(selected_sources, list) or not selected_sources or any(x not in allowed_sources for x in selected_sources):
        raise ValueError("Selecteer minimaal één geldige warmtebron.")
    clean["sources"] = selected_sources
    return clean


def _secure_response(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.get("/<secret>")
def index(secret):
    if not hmac.compare_digest(secret, SECRET_PATH):
        abort(404)
    return _secure_response(make_response(render_template("index.html", defaults=DEFAULTS, secret=SECRET_PATH)))


@app.post("/<secret>/api/calculate")
def api_calculate(secret):
    if not hmac.compare_digest(secret, SECRET_PATH):
        abort(404)
    try:
        values = _validate(request.get_json(silent=True) or {})
        calc_id, started_clock = _log_start(values)
        try:
            results = calculate_python_model(values)
            _log_finish(calc_id, started_clock, "success")
            return _secure_response(make_response(jsonify({"calculation_id": calc_id, "inputs": values, "results": results})))
        except Exception as exc:
            _log_finish(calc_id, started_clock, "failed", str(exc))
            raise
    except ValueError as exc:
        return _secure_response(make_response(jsonify({"error": str(exc)}), 400))
    except Exception:
        app.logger.exception("Python-berekening mislukt")
        return _secure_response(make_response(jsonify({"error": "De berekening is niet gelukt. Controleer de invoer of probeer het opnieuw."}), 500))



@app.get("/<secret>/api/logs")
def api_logs(secret):
    if not hmac.compare_digest(secret, SECRET_PATH):
        abort(404)
    with sqlite3.connect(LOG_DB, timeout=20) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,started_at,finished_at,status,duration_seconds,inputs_json,selected_sources,error FROM calculations ORDER BY started_at DESC LIMIT 100").fetchall()
    records=[]
    for row in rows:
        item=dict(row)
        item["inputs"] = json.loads(item.pop("inputs_json"))
        records.append(item)
    return _secure_response(make_response(jsonify({"calculations": records})))

@app.get("/health")
def health():
    return _secure_response(make_response("ok", 200))


@app.get("/robots.txt")
def robots():
    return _secure_response(make_response("User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain"}))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
