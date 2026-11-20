"""
Kosten individueel
"""

from dataclasses import dataclass, asdict
from .input_params import InputParams
from .utils import _bet
from typing import Dict, Optional, Tuple

@dataclass
class IndividueelResult:
    investering_per_weq_eur: float
    kapitaallasten_per_weq_eur_per_jaar: float
    bo_per_weq_eur_per_jaar: float
    energiekosten_per_weq_eur_per_jaar: float
    subsidies_per_weq_eur_per_jaar: float
    totaal_per_weq_eur_per_jaar: float
    elec_kwh_per_weq: float
    gas_m3_per_weq: float
    co2_kg_per_weq_now: float
    co2_kg_per_weq_2030: float
    co2_kosten_per_weq_eur: float
    net_kosten_per_weq_eur: float

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IndividueelKengetallen:
    naam: str
    cap_per_weq_cv: float = 6.7
    cap_per_weq_wtap: float = 28.0
    losses_div: float = 0.0 # no losses assumed
    cap_per_weq_kw:float = 0.0
    bo_fix: float = 408.0
    bo_var: float = 0.0
    subsidie: float = 0.0
    life_time: float = 15.0
    scop: float = 1.0
    co2_elec_kg_per_kwh_now: float = 0.34
    co2_elec_kg_per_kwh_2030: float = 0.07
    co2_gas_kg_per_m3: float = 1.79
    co2_multiplier_elec: float = 1.0   # P2H: 0.4 op elektra-CO2
    co2_multiplier_gas: float = 1.0    # in max.py blijft gas op 1.0 (ook bij P2H)
    gas_lhv_mj_per_m3: float = 35.17


BRONNEN: Dict[str, IndividueelKengetallen] = {
    "LWP": IndividueelKengetallen(
        naam="LWP",
        cap_per_weq_kw=3.35,
        bo_fix=0.0,
        bo_var=0.02,
        life_time=15.0,
        scop=2.6
    ),
    "HWP": IndividueelKengetallen(
        naam="HWP",
        cap_per_weq_kw=2.0,
        bo_fix=285.6,
        bo_var=0.02,
        life_time=15.0,
        scop=2.7
    ),
    "GK": IndividueelKengetallen(
        naam="GK",
        cap_per_weq_kw = 0.0,
        bo_fix=408.0,
        bo_var=0.0,
        life_time=12.0
    ),
}


def _capaciteitsvraag_per_weq_kw(warmtevraag_per_weq_gj: float, kg: IndividueelKengetallen) -> float:
    # max.py: warmtevraag*277/1200
    return max(warmtevraag_per_weq_gj * 277.0 / 1200.0, kg.cap_per_weq_cv), kg.cap_per_weq_wtap

def _bereken_investering(bron: str, cap_per_weq_cv: float) -> float:
    if bron == "GK":
        return 2200.0
    elif bron == "LWP":
        return 14032 + 673.66 * cap_per_weq_cv - 2553
    elif bron == "HWP":
        return (4200 * (cap_per_weq_cv ** -0.6)) * cap_per_weq_cv + 2200.0
    else:
        return 0.0

def _bereken_bo(inv: float, bo_fix: float, bo_var: float) -> float:
    return inv * bo_var + bo_fix

def _bereken_energie(inp: InputParams, kg: IndividueelKengetallen) -> tuple[float, float]:
    verbruik_gj = inp.warmtevraag_inschatting
    bron = inp.bron
    if bron == "GK":
        return 0.0, verbruik_gj * 1000 / kg.gas_lhv_mj_per_m3 / 0.9
    elif bron == "LWP":
        return verbruik_gj / kg.scop * 1000 / 3.6, 0.0
    elif bron == "HWP":
        return 0.7 * verbruik_gj / kg.scop * 1000 / 3.6, 0.3 * verbruik_gj * 1000 / kg.gas_lhv_mj_per_m3 / 0.9
    else:
        return 0.0

def _bereken_co2(inp: InputParams, kg: IndividueelKengetallen, elec_kwh: float, gas_m3: float, when: str) -> float:
    bron = inp.bron
    if bron == "GK":
        return gas_m3 * kg.co2_gas_kg_per_m3
    elif bron == "LWP":
        if when == "now":
            return elec_kwh * kg.co2_elec_kg_per_kwh_now
        else:
            return  elec_kwh * kg.co2_elec_kg_per_kwh_2030
    elif bron == "HWP":
        if when == "now":
            elec = elec_kwh * kg.co2_elec_kg_per_kwh_now
        else:
            elec = elec_kwh * kg.co2_elec_kg_per_kwh_2030
        gas = gas_m3 * kg.co2_gas_kg_per_m3
        return elec + gas
    else:
        return 0.0

def bereken_individueel(inp: InputParams) -> IndividueelResult:
    """Bereken individuele bronkosten."""
    if inp.bron not in BRONNEN:
        raise ValueError(f"Onbekend brontype: {inp.bron!r}. Beschikbaar: {list(BRONNEN.keys())}")

    kg = BRONNEN[inp.bron]

    # Basis
    aantal_weq = float(inp.aantal_woningen)
    warmtevraag_per_weq_gj = float(inp.warmtevraag_inschatting)

    cap_cv_per_weq_kw, cap_wtap_per_weq_kw = _capaciteitsvraag_per_weq_kw(warmtevraag_per_weq_gj, kg)

    warmtevraag_totaal_gj = aantal_weq * warmtevraag_per_weq_gj
    warmtevraag_verliezen_gj = (1.0 / kg.losses_div - 1.0) * warmtevraag_totaal_gj if kg.losses_div > 0 else 0.0
    warmtevraag_incl_verlies_gj = warmtevraag_totaal_gj + warmtevraag_verliezen_gj

    inv = _bereken_investering(inp.bron, cap_cv_per_weq_kw)
    kap = _bet(0.03, kg.life_time, inv)
    bo = _bereken_bo(inv, kg.bo_fix, kg.bo_var)
    sub = abs(_bet(0.03, 15, kg.subsidie))

    elec_kwh_per_weq, gas_m3_per_weq = _bereken_energie(inp, kg)
    energie = elec_kwh_per_weq * inp.eprijs_2030 + gas_m3_per_weq * inp.gasprijs_2030
    tot = kap + bo + energie - sub

    co2_kg_per_weq_now = _bereken_co2(inp, kg, elec_kwh_per_weq, gas_m3_per_weq, "now")
    co2_kg_per_weq_2030 = _bereken_co2(inp, kg, elec_kwh_per_weq, gas_m3_per_weq, "2030")

    co2_kosten_per_weq_eur = co2_kg_per_weq_now * inp.prijs_per_ton_co2 / 1000
    net = kg.cap_per_weq_kw * inp.netverzwaring_kosten

    return IndividueelResult(
        investering_per_weq_eur=inv,
        kapitaallasten_per_weq_eur_per_jaar=kap,
        bo_per_weq_eur_per_jaar=bo,
        energiekosten_per_weq_eur_per_jaar=energie,
        subsidies_per_weq_eur_per_jaar=sub,
        totaal_per_weq_eur_per_jaar=tot,
        elec_kwh_per_weq=elec_kwh_per_weq,
        gas_m3_per_weq=gas_m3_per_weq,
        co2_kg_per_weq_now=co2_kg_per_weq_now,
        co2_kg_per_weq_2030=co2_kg_per_weq_2030,
        co2_kosten_per_weq_eur=co2_kosten_per_weq_eur,
        net_kosten_per_weq_eur=net,
    )
