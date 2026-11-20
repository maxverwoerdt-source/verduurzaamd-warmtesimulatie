import hmac
import math
import os
import time
import logging
import re
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request

from engine import calculate as calculate_python_model

BASE_DIR = Path(__file__).resolve().parent
SECRET_PATH = os.environ.get("APP_SECRET_PATH", "")

if not SECRET_PATH or not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", SECRET_PATH):
    raise RuntimeError("Stel APP_SECRET_PATH in op een willekeurige tekenreeks van minimaal 20 tekens.")

app = Flask(__name__)

DEFAULTS = {
    "aantal_woningen": 1000,
    "warmtevraag": 30,
    "gasprijs_2030": 1.70,
    "eprijs_2030": 0.25,
    "rendementseis": 6.0,
    "subsidie": 5000,
    "prijs_per_ton_co2": 200,
    "netverzwaring_kosten": 100,
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
    if not isinstance(selected_sources, list) or any(x not in allowed_sources for x in selected_sources):
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
    request_start=time.perf_counter()
    try:
        validation_start=time.perf_counter()
        values = _validate(request.get_json(silent=True) or {})
        app.logger.warning("CALC PHASE validation=%.3fs",time.perf_counter()-validation_start)
        calculation_start=time.perf_counter()
        results = calculate_python_model(values)
        app.logger.warning("CALC PHASE engine=%.3fs",time.perf_counter()-calculation_start)
        app.logger.warning("CALC REQUEST success duration=%.3fs sources=%d",time.perf_counter()-request_start,len(results))
        return _secure_response(make_response(jsonify({"inputs": values, "results": results})))
    except ValueError as exc:
        app.logger.warning("CALC REQUEST validation_error duration=%.3fs error=%s",time.perf_counter()-request_start,exc)
        return _secure_response(make_response(jsonify({"error": str(exc)}), 400))
    except Exception:
        app.logger.exception("Python-berekening mislukt; duration=%.3fs",time.perf_counter()-request_start)
        return _secure_response(make_response(jsonify({"error": "De berekening is niet gelukt. Controleer de invoer of probeer het opnieuw."}), 500))


@app.get("/health")
def health():
    return _secure_response(make_response("ok", 200))


@app.get("/robots.txt")
def robots():
    return _secure_response(make_response("User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain"}))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
