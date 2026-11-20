"""Persistent LibreOffice/UNO Excel calculator. Workbook is loaded once per service."""
from __future__ import annotations
import math, os, sys, threading, time, logging
from pathlib import Path

# Debian's LibreOffice UNO bindings are installed outside the pip environment.
for _uno_path in ("/usr/lib/python3/dist-packages", "/usr/lib/libreoffice/program"):
    if _uno_path not in sys.path:
        sys.path.append(_uno_path)

import uno
from com.sun.star.beans import PropertyValue

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
MODEL_FILE = BASE_DIR / "model" / "rekenmodel.xlsm"
UNO_PORT = int(os.environ.get("UNO_PORT", "2002"))
_LOCK = threading.Lock()
_DOC = None
_SHEET = None
_DESKTOP = None
_REMOTE_CTX = None

SOURCES = [
    ("TEA", "TEA", "I", True), ("TEO", "TEO", "J", True),
    ("CLWP", "Centrale lucht-waterwarmtepomp", "K", True),
    ("OGEO", "Ondiepe geothermie", "L", True), ("REST", "Restwarmte", "M", True),
    ("PVT", "PVT", "N", True), ("SOLAR", "Zonthermie", "O", True),
    ("P2H", "Power-to-Heat", "P", True),
    ("LWP", "Individuele lucht-waterwarmtepomp", "Q", False),
    ("HWP", "Individuele hybride warmtepomp", "R", False),
    ("GK", "Individuele gasketel", "S", False),
]

INPUT_CELLS = {
    "B22": "aantal_woningen", "B23": "warmtevraag",
    "B24": "dorp_stad_factor", "B25": "perc_appartementen",
    "B29": "gasprijs_2030", "B30": "eprijs_2030",
    "B31": "rendementseis", "B32": "subsidie",
    "B33": "prijs_per_ton_co2", "B34": "netverzwaring_kosten",
}


def _property(name, value):
    prop = PropertyValue(); prop.Name = name; prop.Value = value
    return prop


def _connect_uno():
    global _REMOTE_CTX, _DESKTOP
    if _DESKTOP is not None:
        return _DESKTOP
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx)
    connect_url = (f"uno:socket,host=127.0.0.1,port={UNO_PORT};urp;"
                   "StarOffice.ComponentContext")
    last_error = None
    for _ in range(20):
        try:
            _REMOTE_CTX = resolver.resolve(connect_url)
            _DESKTOP = _REMOTE_CTX.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", _REMOTE_CTX)
            return _DESKTOP
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"LibreOffice UNO-service niet beschikbaar: {last_error}")


def _load_model():
    global _DOC, _SHEET
    if _DOC is not None:
        return _DOC, _SHEET
    if not MODEL_FILE.exists():
        raise RuntimeError("Het Excel-rekenmodel ontbreekt op de server.")
    desktop = _connect_uno()
    model_url = uno.systemPathToFileUrl(str(MODEL_FILE))
    start = time.perf_counter()
    doc = desktop.loadComponentFromURL(
        model_url, "_blank", 0,
        (_property("Hidden", True), _property("ReadOnly", False),
         _property("UpdateDocMode", 3), _property("MacroExecutionMode", 0),
         _property("NoAutoSave", True)))
    if doc is None:
        raise RuntimeError("LibreOffice kon het rekenmodel niet openen.")
    try:
        doc.enableAutomaticCalculation(False)
    except Exception:
        pass
    _DOC = doc
    _SHEET = doc.Sheets.getByName("Input")
    logger.warning("CALC PHASE persistent_model_load=%.3fs", time.perf_counter()-start)
    return _DOC, _SHEET


def _finite(cell, address):
    error = cell.getError()
    if error:
        formula = cell.getFormula()
        raise RuntimeError(f"Excel-uitkomst {address} bevat foutcode {error}: {formula}")
    value = cell.getValue()
    if not math.isfinite(float(value)):
        raise RuntimeError(f"Excel-uitkomst {address} is ongeldig: {value!r}")
    return float(value)


def _read_source(sheet, key, label, col, collective):
    capital = _finite(sheet.getCellRangeByName(f"{col}32"), f"{col}32")
    if collective:
        capital += _finite(sheet.getCellRangeByName(f"{col}36"), f"{col}36")
    maintenance = _finite(sheet.getCellRangeByName(f"{col}33"), f"{col}33")
    energy = _finite(sheet.getCellRangeByName(f"{col}34"), f"{col}34")
    co2 = _finite(sheet.getCellRangeByName(f"{col}45"), f"{col}45")
    grid = _finite(sheet.getCellRangeByName(f"{col}46"), f"{col}46")
    return {"key": key, "label": label, "capital": capital,
            "maintenance": maintenance, "energy": energy, "co2": co2,
            "grid": grid, "total": sum((capital, maintenance, energy, co2, grid)),
            "detail": "Rechtstreeks berekend door het Excel-rekenmodel"}


def calculate(values):
    # The workbook is shared and kept warm in memory. Serialize requests to prevent
    # one user's inputs/results from mixing with another user's calculation.
    with _LOCK:
        request_start = time.perf_counter()
        t = time.perf_counter()
        doc, sheet = _load_model()
        logger.warning("CALC PHASE persistent_model_ready=%.3fs", time.perf_counter()-t)

        t = time.perf_counter()
        for cell, key in INPUT_CELLS.items():
            value = values[key]
            if key in ("dorp_stad_factor", "perc_appartementen", "rendementseis"):
                value = float(value) / 100.0
            sheet.getCellRangeByName(cell).setValue(float(value))
        logger.warning("CALC PHASE input_write=%.3fs", time.perf_counter()-t)

        t = time.perf_counter()
        doc.calculateAll()
        logger.warning("CALC PHASE libreoffice_recalc=%.3fs", time.perf_counter()-t)

        t = time.perf_counter()
        results = [_read_source(sheet, *source) for source in SOURCES]
        logger.warning("CALC PHASE results_read=%.3fs", time.perf_counter()-t)
        logger.warning("CALC TIMING persistent_engine_total=%.3fs sources=%d",
                       time.perf_counter()-request_start, len(results))
        return results
