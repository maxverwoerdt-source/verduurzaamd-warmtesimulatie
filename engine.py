"""Native Python calculation engine using the recovered P2H calculation scripts."""
from __future__ import annotations
import time
import logging
from p2h_model.input_params import InputParams
from p2h_model.kosten_bronnen import bereken_kosten_bron
from p2h_model.kosten_leidingwerk import bereken_leidingwerk
from p2h_model.kosten_individueel import bereken_individueel
from p2h_model.calculator import bereken_totaal

logger = logging.getLogger(__name__)

SOURCE_ORDER = ["TEA", "TEO", "CLWP", "OGEO", "REST", "PVT", "SOLAR", "P2H", "GK", "LWP", "HWP"]
LABELS = {
    "TEA": "Thermische energie uit aquathermie",
    "TEO": "Thermische energie uit oppervlaktewater",
    "CLWP": "Centrale lucht-waterwarmtepomp",
    "OGEO": "Ondiepe geothermie",
    "REST": "Restwarmte",
    "PVT": "PVT",
    "SOLAR": "Zonthermie",
    "P2H": "Power-to-Heat",
    "GK": "Individuele gasketel",
    "LWP": "Individuele lucht-waterwarmtepomp",
    "HWP": "Individuele hybride warmtepomp",
}


def calculate(values):
    start = time.perf_counter()
    inp = InputParams.from_dict(values)
    raw = {}
    # Calculate every source. UI source toggles are only display filters.
    for source in ["TEA", "TEO", "REST", "CLWP", "OGEO", "P2H", "PVTE", "SOLAR"]:
        inp.bron = source
        source_result = bereken_kosten_bron(inp)
        pipe_result = bereken_leidingwerk(inp)
        raw[source] = bereken_totaal(inp, source_result, pipe_result).to_dict()
    for source in ["GK", "LWP", "HWP"]:
        inp.bron = source
        raw[source] = bereken_individueel(inp).to_dict()

    # Adapter preserves the existing website/API shape. Subsidy is represented
    # as a reduction of capital costs so the stacked chart sums to the total.
    results = []
    key_map = {"PVT": "PVTE"}
    for key in SOURCE_ORDER:
        data = raw[key_map.get(key, key)]
        capital = data["kapitaallasten_per_weq_eur_per_jaar"] - data["subsidies_per_weq_eur_per_jaar"]
        maintenance = data["bo_per_weq_eur_per_jaar"]
        energy = data["energiekosten_per_weq_eur_per_jaar"]
        co2 = data["co2_kosten_per_weq_eur"]
        grid = data["net_kosten_per_weq_eur"]
        results.append({
            "key": key,
            "label": LABELS[key],
            "capital": capital,
            "maintenance": maintenance,
            "energy": energy,
            "co2": co2,
            "grid": grid,
            "total": capital + maintenance + energy + co2 + grid,
            "detail": "Rechtstreeks berekend met het Python-rekenmodel",
        })
    logger.warning("CALC PHASE native_python=%.4fs sources=%d", time.perf_counter()-start, len(results))
    return results
