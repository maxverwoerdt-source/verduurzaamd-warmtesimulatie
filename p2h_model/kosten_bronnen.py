"""
Kosten bronnen – rekenmodel per bronconcept.

Deze module vervangt de eerdere "kengetallen-only" benadering door een
generieke implementatie op basis van de (meer gedetailleerde) formules in
`max.py`. De bedoeling is:

- Eén generieke `bereken_kosten_bron(inp)` die op basis van `inp.bron`
  (conceptcode) alle bron-investeringen en -kosten berekent.
- Concept-specifieke *getallen* zitten in `BRONNEN` (de `kg` dict).
  De rekenstructuur is verder gelijk.

Belangrijk:
- De veldnamen in `BronResult` blijven compatibel met de bestaande code.
- In `max.py` worden CO₂-factoren als "2025" benoemd. Hier gebruiken we
  de bestaande velden `co2_2023_kg_per_weq` en `co2_2030_kg_per_weq`.
  (Dus: `co2_2023_*` volgt de "huidige" factor uit max.py.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from .input_params import InputParams
from .utils import _bet

# -----------------------------
# Concept-kengetallen
# -----------------------------
@dataclass(frozen=True)
class BronKengetallen:
    """Alle concept-specifieke constanten die in de max.py formules voorkomen."""
    naam: str

    # Vermogen / sizing
    ontwerpvermogen_mult: float = 0.55 # CV gelijktijdigheid
    cap_per_weq_cv: float = 6.7
    cap_per_weq_wtap: float = 28.0

    # Aandeel vermogen (MW) t.o.v. ontwerpvermogen (kW)
    cap_wp_frac: float = 0.30  # is SCOP 3.33 voor elektrisch aansluitvermogen
    cap_gk_frac: float = 1.00

    # Efficiëntie / energie
    scop: float = 2.4                 # "COP" in de energieregel: warmtevraag / COP
    elec_frac: float = 0.85          # fractie warmtevraag via elektra
    gas_frac: float = 0.15           # fractie warmtevraag via gas
    elec_overfactor: float = 1.10    # (1.1) opslag uit max.py
    losses_div: float = 0.75         # warmtevraag_incl_verlies = warmtevraag / 0.75
    gas_lhv_mj_per_m3: float = 35.17
    gas_eta: float = 0.85

    # Kostenfactoren (P2H had 0.4 op energiekosten; in max.py ook op eur_m3)
    energy_cost_multiplier_elec: float = 1.0
    energy_cost_multiplier_gas: float = 1.0

    # CO2 factoren
    co2_elec_kg_per_kwh_now: float = 0.34
    co2_elec_kg_per_kwh_2030: float = 0.07
    co2_gas_kg_per_m3: float = 1.79
    co2_multiplier_elec: float = 1.0   # P2H: 0.4 op elektra-CO2
    co2_multiplier_gas: float = 1.0    # in max.py blijft gas op 1.0 (ook bij P2H)

    # CAPEX scaling / multipliers (P2H heeft ~1.05 op veel posten)
    capex_multiplier: float = 1.0

    # Warmtepomp kost per kW: threshold en parameters
    wp_threshold_kw: float = 4500.0
    wp_perkw_if_large: float = 259.0
    wp_perkw_base: float = 3600.0
    wp_perkw_div: float = 3.0
    wp_perkw_exp: float = -0.36

    # kWe-voeding: 110 €/kW_e * (Cap_WP / divisor) * 1000
    kwe_divisor: float = 2.4

    # Uitkoppeling / WKO – concept-specifieke flags en parameters
    uitkoppel_mode: str = "none"  # none | tea | teo | fixed | pvte | solar
    uitkoppel_fixed_eur: float = 0.0

    teo_outlet_factor: float = 2.0
    teo_uitkoppel_const: float = 142000.0
    teo_uitkoppel_exp: float = -0.79

    tea_uitkoppel_base: float = 123000.0
    tea_uitkoppel_slope: float = 1440.0
    tea_uitkoppel_cap: float = 250.0
    tea_uitkoppel_mult1: float = 1.05
    tea_uitkoppel_mult2: float = 1.5

    # WKO (alleen TEO in max.py)
    wko_enabled: bool = False
    wko_base: float = 45000.0
    wko_exp: float = -0.52
    wko_ref: float = 150.0

    # OGEO speciale sizing/uitkoppeling
    ogeo_min_cap_wp_mw: float = 8.0
    ogeo_uitkoppeling_eur_per_mw: float = 3500.0 * 1000.0  # €/MW

    # SOLAR extra: (..)*0.95 en +230*...
    solar_inv_uitkoppeling_mult: float = 0.95
    solar_extra_230: float = 230.0

    # B&O parameters (percentages op investeringen)
    bo_uitkoppeling_frac_default: float = 0.025
    bo_uitkoppeling_frac_ogeo: float = 0.005
    bo_uitkoppeling_frac_pvte: float = 0.010
    bo_uitkoppeling_frac_solar: float = 0.003
    bo_wp_frac_clwp: float = 0.05
    bo_wp_frac_default: float = 0.03

    # Vastrechten / aansluitkosten (per kW_th / kW_e)
    bo_gas_vr_per_kw: float = 4.75
    bo_kwe_voeding_per_kw: float = 50.0
    bo_kwe_divisor: float = 3.0  # delingsgetal in max.py voor BO_kWevoeding


BRONNEN: Dict[str, BronKengetallen] = {
    "TEA": BronKengetallen(
        naam="TEA",
        scop=3.0,
        uitkoppel_mode="tea",
        kwe_divisor=3.0,
        wp_perkw_base=3600.0,
        wp_threshold_kw=4500.0,
        capex_multiplier=1.0,
    ),
    "TEO": BronKengetallen(
        naam="TEO",
        scop=2.8,
        uitkoppel_mode="teo",
        wko_enabled=True,
        kwe_divisor=2.8,
        wp_perkw_base=3600.0,
        wp_threshold_kw=4500.0,
        capex_multiplier=1.0,
    ),
    "CLWP": BronKengetallen(
        naam="ctr. L. wp",
        scop=2.4,
        uitkoppel_mode="none",
        kwe_divisor=2.4,
        wp_perkw_base=4500.0,  # max.py gebruikt 4500 hier
        capex_multiplier=1.0,
    ),
    "OGEO": BronKengetallen(
        naam="ond. Geothermie",
        scop=3.7,
        uitkoppel_mode="ogeo",
        kwe_divisor=3.6,
        wp_perkw_base=4500.0,
        capex_multiplier=1.0,
    ),
    "REST": BronKengetallen(
        naam="restwarmte (25grC)",
        scop=3.2,
        uitkoppel_mode="fixed",
        uitkoppel_fixed_eur=20000.0,
        kwe_divisor=3.2,
        wp_perkw_base=3600.0,
        capex_multiplier=1.0,
    ),
    "PVTE": BronKengetallen(
        naam="PVTe",
        scop=3.8,
        uitkoppel_mode="pvte",
        kwe_divisor=3.8,
        wp_threshold_kw=4000.0,
        wp_perkw_if_large=215.0,
        wp_perkw_base=3600.0,
        capex_multiplier=1.0,
    ),
    "SOLAR": BronKengetallen(
        naam="Solar",
        scop=4.5,
        elec_frac=0.77,         # max.py
        uitkoppel_mode="solar",
        kwe_divisor=4.5,
        wp_threshold_kw=4000.0,
        wp_perkw_if_large=215.0,
        wp_perkw_base=3600.0,
        capex_multiplier=1.0,
    ),
    "P2H": BronKengetallen(
        naam="P2H",
        scop=2.6,  # BO_kWevoeding deelt door 2.6 in max.py
        uitkoppel_mode="none",
        kwe_divisor=50,
        wp_perkw_base=4500.0,
        capex_multiplier=1.05,
        energy_cost_multiplier_elec=0.4,
        energy_cost_multiplier_gas=0.4,   # volgt max.py (eur_m3 * 0.4)
        co2_multiplier_elec=0.4,
        co2_multiplier_gas=1.0,
    ),
}


# -----------------------------
# Output-structuur
# -----------------------------
@dataclass
class BronResult:
    concept: str

    # Basis per weq
    aantal_weq: float
    warmtevraag_per_weq_gj: float
    capaciteitsvraag_per_weq_kw: float

    # Warmtevraag en vermogen totaal
    warmtevraag_totaal_gj: float
    warmtevraag_verliezen_gj: float
    warmtevraag_incl_verlies_gj: float
    ontwerpvermogen_kw: float
    cap_wp_mw: float

    # Financieel per weq
    investering_per_weq_eur: float
    kapitaallasten_per_weq_eur_per_jaar: float
    bo_per_weq_eur_per_jaar: float
    energiekosten_per_weq_eur_per_jaar: float

    # Energieverbruik per weq
    elec_kwh_per_weq: float
    gas_m3_per_weq: float

    # CO₂
    co2_kg_per_weq_now: float
    co2_kg_per_weq_2030: float

    # Kengetallen van de bron
    kengetallen: BronKengetallen

    def to_dict(self) -> dict:
        return asdict(self)

# -----------------------------
# Interne rekenstappen
# -----------------------------
def _capaciteitsvraag_per_weq_kw(warmtevraag_per_weq_gj: float, kg: BronKengetallen) -> float:
    # max.py: warmtevraag*277/1200
    return max(warmtevraag_per_weq_gj * 277.0 / 1200.0, kg.cap_per_weq_cv), kg.cap_per_weq_wtap


def _ontwerpvermogen_kw(aantal_weq: float, cap_cv_per_weq_kw: float, cap_wtap_per_weq_kw: float, kg: BronKengetallen) -> float:
    # max.py: cap_per_weq_kw*aantal_weq*0.55 + 28*sqrt(aantal_weq)
    return cap_cv_per_weq_kw * aantal_weq * kg.ontwerpvermogen_mult + cap_wtap_per_weq_kw * math.sqrt(aantal_weq)


def _cap_wp_gk_mw(ontwerpvermogen_kw: float, kg: BronKengetallen) -> tuple[float, float]:
    cap_wp_mw = kg.cap_wp_frac * ontwerpvermogen_kw / 1000.0
    cap_gk_mw = kg.cap_gk_frac * ontwerpvermogen_kw / 1000.0
    return cap_wp_mw, cap_gk_mw


def _wp_perkw(cap_wp_mw: float, kg: BronKengetallen) -> float:
    cap_kw = cap_wp_mw * 1000.0
    if cap_kw > kg.wp_threshold_kw:
        return kg.wp_perkw_if_large
    # max.py: base * ( (cap_kw/div) ** exp )
    return kg.wp_perkw_base * (cap_kw / kg.wp_perkw_div) ** (kg.wp_perkw_exp)


def _uitkoppeling_en_wko(
    aantal_weq: float,
    warmtevraag_incl_verlies_gj: float,
    cap_wp_mw: float,
    kg: BronKengetallen,
) -> tuple[float, float]:
    """Bereken INV_Uitkoppeling en INV_WKO volgens max.py, concept-gedreven."""
    mode = kg.uitkoppel_mode.lower()

    # Flow proxy uit max.py: (Cap_WP/4.18/5*3.6*1000)
    # (Cap_WP in MW)
    flow_proxy = cap_wp_mw / 4.18 / 5.0 * 3.6 * 1000.0

    inv_wko = 0.0

    if mode == "none":
        inv_uit = 100000.0 * (cap_wp_mw ** 0.3)

    elif mode == "tea":
        # max.py TEA: unit cost per "flow", cap op 250
        if flow_proxy > kg.tea_uitkoppel_cap:
            unit = (kg.tea_uitkoppel_base + kg.tea_uitkoppel_slope * kg.tea_uitkoppel_cap) * kg.tea_uitkoppel_mult1 * kg.tea_uitkoppel_mult2 / kg.tea_uitkoppel_cap
        else:
            unit = (kg.tea_uitkoppel_base + kg.tea_uitkoppel_slope * flow_proxy) * kg.tea_uitkoppel_mult1 * kg.tea_uitkoppel_mult2 / (flow_proxy if flow_proxy > 0 else 1.0)
        inv_uit = 100000.0 * (cap_wp_mw ** 0.3) + flow_proxy * unit

    elif mode == "teo":
        # max.py TEO: Uitkoppel op (flow*2), exponent -0.79 en additionele WKO
        flow2 = flow_proxy * kg.teo_outlet_factor
        if flow2 > 250:
            unit = kg.teo_uitkoppel_const * (250.0 ** (kg.teo_uitkoppel_exp))  # dit is letterlijk wat in max.py staat (maar is dimensioneel vreemd)
        else:
            unit = kg.teo_uitkoppel_const * (flow2 ** (kg.teo_uitkoppel_exp))
        inv_uit = 100000.0 * (cap_wp_mw ** 0.3) + flow2 * unit

        if kg.wko_enabled:
            if flow_proxy < kg.wko_ref:
                inv_wko = kg.wko_base * (flow_proxy ** (kg.wko_exp)) * flow_proxy
            else:
                inv_wko = kg.wko_base * (kg.wko_ref ** (kg.wko_exp)) * flow_proxy

    elif mode == "fixed":
        inv_uit = 100000.0 * (cap_wp_mw ** 0.3) + kg.uitkoppel_fixed_eur

    elif mode == "pvte":
        # max.py PVTE: functie van warmtevraag
        inv_extra = warmtevraag_incl_verlies_gj / 17287.0 * 74994.0 + warmtevraag_incl_verlies_gj / 17287.0 / 2.0 * 2101333.0
        inv_uit = 100000.0 * (cap_wp_mw ** 0.3) + inv_extra

    elif mode == "solar":
        # max.py SOLAR: complexe functie van warmtevraag
        x = warmtevraag_incl_verlies_gj * (0.77 + 0.08) / 1.55 / 0.85
        inv_extra = (
            x * 353.0
            + x * 2.0 / 10000.0 * 75000.0
            + x * 2.34 * (6000.0 * (x * 2.34) ** (-0.44))
        )
        inv_uit = (100000.0 * (cap_wp_mw ** 0.3) + inv_extra + kg.solar_extra_230 * x) * kg.solar_inv_uitkoppeling_mult

    elif mode == "ogeo":
        # max.py OGEO: minimum Cap_WP 8 MW en uitkoppeling ~ Cap_WP * 3500k€/MW, WP=0
        cap_eff = max(cap_wp_mw, kg.ogeo_min_cap_wp_mw)
        inv_uit = cap_eff * kg.ogeo_uitkoppeling_eur_per_mw

    else:
        raise ValueError(f"Onbekende uitkoppel_mode: {kg.uitkoppel_mode!r}")

    # Concept multiplier (bijv. 1.05 voor P2H in max.py) – op de uitkoppeling en wko toepassen
    inv_uit *= kg.capex_multiplier
    inv_wko *= kg.capex_multiplier

    return inv_uit, inv_wko


def _bereken_investeringen(aantal_weq: float, warmtevraag_incl_verlies_gj: float, cap_wp_mw: float, cap_gk_mw: float, subsidie: float, kg: BronKengetallen) -> dict:
    """Returneert een dict met alle investeringscomponenten + INV_Totaal."""
    inv_uit, inv_wko = _uitkoppeling_en_wko(aantal_weq, warmtevraag_incl_verlies_gj, cap_wp_mw, kg)

    # Warmtepomp investering: OGEO heeft in max.py INV_WP=0
    inv_wp = 0.0
    if kg.uitkoppel_mode.lower() != "ogeo":
        inv_wp = cap_wp_mw * _wp_perkw(cap_wp_mw, kg) * 1000.0 * kg.capex_multiplier

    inv_appwp = 200.0 * cap_wp_mw * 1000.0 * kg.capex_multiplier
    inv_kwe = 110.0 * cap_wp_mw / kg.kwe_divisor * 1000.0 * kg.capex_multiplier

    inv_piekketel = 65.0 * 1000.0 * cap_gk_mw * kg.capex_multiplier
    inv_leidingcv = 50.0 * 1000.0 * cap_gk_mw * kg.capex_multiplier
    inv_gasleiding = 5.0 * 1000.0 * cap_gk_mw * kg.capex_multiplier
    inv_waterbehandeling = 5.0 * 1000.0 * cap_gk_mw * kg.capex_multiplier

    inv_regeling = 0.15 * (
        inv_wp + inv_appwp + inv_kwe + inv_piekketel + inv_leidingcv + inv_gasleiding + inv_waterbehandeling
    )

    inv_gebouw = 283104.0  # max.py: constant
    inv_transportpompen = 50.0 * 1000.0 * cap_gk_mw  # geen 1.05 in max.py
    inv_expansievoorziening = 15.0 * (aantal_weq ** 0.8) * 4.0 * 10.0

    inv_subsidie = -subsidie * aantal_weq

    inv_toeslag = 0.30 * (
        inv_uit
        + inv_wp
        + inv_appwp
        + inv_kwe
        + inv_piekketel
        + inv_leidingcv
        + inv_gasleiding
        + inv_waterbehandeling
        + inv_regeling
        + inv_gebouw
        + inv_transportpompen
        + inv_expansievoorziening
    )

    inv_totaal = (
        inv_uit
        + inv_wp
        + inv_appwp
        + inv_kwe
        + inv_piekketel
        + inv_leidingcv
        + inv_gasleiding
        + inv_waterbehandeling
        + inv_regeling
        + inv_gebouw
        + inv_transportpompen
        + inv_expansievoorziening
        + inv_toeslag
        + inv_wko
        + inv_subsidie
    )

    return {
        "INV_Uitkoppeling": inv_uit,
        "INV_WKO": inv_wko,
        "INV_WP": inv_wp,
        "INV_appWP": inv_appwp,
        "INV_kWe": inv_kwe,
        "INV_piekketel": inv_piekketel,
        "INV_LeidingCV": inv_leidingcv,
        "INV_gasleiding": inv_gasleiding,
        "INV_Waterbehandeling": inv_waterbehandeling,
        "INV_regeling": inv_regeling,
        "INV_gebouw": inv_gebouw,
        "INV_transportpompen": inv_transportpompen,
        "INV_expansievoorziening": inv_expansievoorziening,
        "INV_toeslag": inv_toeslag,
        "INV_subsidie": inv_subsidie,
        "INV_Totaal": inv_totaal,
    }


def _bereken_kapitaallasten(inv: dict, kg: BronKengetallen, rendementseis: float) -> float:
    # Termijnen uit max.py (jaren)
    kap = 0.0
    kap += _bet(rendementseis, 30, inv["INV_Uitkoppeling"])
    kap += _bet(rendementseis, 30, inv["INV_WKO"])
    kap += _bet(rendementseis, 20, inv["INV_WP"])
    kap += _bet(rendementseis, 30, inv["INV_appWP"])
    kap += _bet(rendementseis, 30, inv["INV_kWe"])
    kap += _bet(rendementseis, 25, inv["INV_piekketel"])
    kap += _bet(rendementseis, 30, inv["INV_LeidingCV"])
    kap += _bet(rendementseis, 30, inv["INV_gasleiding"])
    kap += _bet(rendementseis, 20, inv["INV_Waterbehandeling"])
    kap += _bet(rendementseis, 20, inv["INV_regeling"])
    kap += _bet(rendementseis, 50, inv["INV_gebouw"])
    kap += _bet(rendementseis, 15, inv["INV_transportpompen"])
    kap += _bet(rendementseis, 20, inv["INV_expansievoorziening"])
    kap -= _bet(rendementseis, 30, abs(inv["INV_subsidie"]))
    return kap * 1.10  # max.py: *1.1


def _bereken_bo_kosten(inv: dict, kg: BronKengetallen, cap_wp_mw: float, cap_gk_mw: float) -> float:
    # Uitkoppeling-fractie per concept (max.py if-else)
    if kg.uitkoppel_mode.lower() == "ogeo":
        bo_uit = kg.bo_uitkoppeling_frac_ogeo * inv["INV_Uitkoppeling"]
    elif kg.uitkoppel_mode.lower() == "pvte":
        bo_uit = kg.bo_uitkoppeling_frac_pvte * inv["INV_Uitkoppeling"]
    elif kg.uitkoppel_mode.lower() == "solar":
        bo_uit = kg.bo_uitkoppeling_frac_solar * inv["INV_Uitkoppeling"]
    else:
        bo_uit = kg.bo_uitkoppeling_frac_default * inv["INV_Uitkoppeling"]

    bo_wko = 0.05 * inv["INV_WKO"]

    if kg.naam.lower().startswith("ctr."):
        bo_wp = kg.bo_wp_frac_clwp * inv["INV_WP"]
    else:
        bo_wp = kg.bo_wp_frac_default * inv["INV_WP"]

    bo_appwp = 0.005 * inv["INV_appWP"]
    bo_kwe = 0.005 * inv["INV_kWe"]
    bo_piekketel = 0.04 * inv["INV_piekketel"]
    bo_leidingcv = 0.005 * inv["INV_LeidingCV"]
    bo_gasleiding = 0.005 * inv["INV_gasleiding"]
    bo_waterbehandeling = 0.05 * inv["INV_Waterbehandeling"]
    bo_regeling = 0.02 * inv["INV_regeling"]
    bo_gebouw = 0.008 * inv["INV_gebouw"]
    bo_transportpompen = 0.03 * inv["INV_transportpompen"]
    bo_expansie = 0.03 * inv["INV_expansievoorziening"]

    # Vastrechten uit max.py:
    bo_gasvr = kg.bo_gas_vr_per_kw * cap_gk_mw * 1000.0
    bo_kwe_voeding = kg.bo_kwe_voeding_per_kw * 1000.0 * cap_wp_mw / kg.bo_kwe_divisor

    return (
        bo_uit
        + bo_wko
        + bo_wp
        + bo_appwp
        + bo_kwe
        + bo_piekketel
        + bo_leidingcv
        + bo_gasleiding
        + bo_waterbehandeling
        + bo_regeling
        + bo_gebouw
        + bo_transportpompen
        + bo_expansie
        + bo_gasvr
        + bo_kwe_voeding
    )


def bereken_kosten_bron(inp: InputParams) -> BronResult:
    """Bereken bronkosten conform de opzet van max.py, generiek per concept."""
    if inp.bron not in BRONNEN:
        raise ValueError(f"Onbekend brontype: {inp.bron!r}. Beschikbaar: {list(BRONNEN.keys())}")

    kg = BRONNEN[inp.bron]

    # Basis
    aantal_weq = float(inp.aantal_woningen)
    warmtevraag_per_weq_gj = float(inp.warmtevraag_inschatting)

    cap_cv_per_weq_kw, cap_wtap_per_weq_kw = _capaciteitsvraag_per_weq_kw(warmtevraag_per_weq_gj, kg)

    warmtevraag_totaal_gj = aantal_weq * warmtevraag_per_weq_gj
    warmtevraag_verliezen_gj = (1.0 / kg.losses_div - 1.0) * warmtevraag_totaal_gj
    warmtevraag_incl_verlies_gj = warmtevraag_totaal_gj + warmtevraag_verliezen_gj

    ontwerpvermogen_kw = _ontwerpvermogen_kw(aantal_weq, cap_cv_per_weq_kw, cap_wtap_per_weq_kw, kg)
    cap_wp_mw, cap_gk_mw = _cap_wp_gk_mw(ontwerpvermogen_kw, kg)

    # Investeringen
    inv = _bereken_investeringen(aantal_weq, warmtevraag_incl_verlies_gj, cap_wp_mw, cap_gk_mw, inp.subsidie_lumpsum, kg)
    investering_per_weq = inv["INV_Totaal"] / aantal_weq if aantal_weq > 0 else 0.0

    # Kapitaallasten / jaar
    kap_total = _bereken_kapitaallasten(inv, kg, inp.rendementseis)
    kap_per_weq = kap_total / aantal_weq if aantal_weq > 0 else 0.0

    # B&O / jaar
    bo_total = _bereken_bo_kosten(inv, kg, cap_wp_mw, cap_gk_mw)
    bo_per_weq = bo_total / aantal_weq if aantal_weq > 0 else 0.0

    # Energie (jaar)
    elec_kwh = kg.elec_frac * warmtevraag_incl_verlies_gj / kg.scop * 1000.0 / 3.6 * kg.elec_overfactor
    gas_m3 = kg.gas_frac * warmtevraag_incl_verlies_gj * 1000.0 / kg.gas_lhv_mj_per_m3 / kg.gas_eta

    eprijs_grootverbruik = max(inp.eprijs_2030 - 0.15, 0.08)
    gprijs_grootverbruik = max(inp.gasprijs_2030 - 0.4, 0.04)

    eur_elec = elec_kwh * eprijs_grootverbruik * kg.energy_cost_multiplier_elec
    eur_gas = gas_m3 * gprijs_grootverbruik * kg.energy_cost_multiplier_gas

    energiekosten_per_weq = (eur_elec + eur_gas) / aantal_weq if aantal_weq > 0 else 0.0

    elec_kwh_per_weq = elec_kwh / aantal_weq if aantal_weq > 0 else 0.0
    gas_m3_per_weq = gas_m3 / aantal_weq if aantal_weq > 0 else 0.0

    # CO2
    co2_now = elec_kwh * kg.co2_elec_kg_per_kwh_now * kg.co2_multiplier_elec + gas_m3 * kg.co2_gas_kg_per_m3 * kg.co2_multiplier_gas
    co2_2030 = elec_kwh * kg.co2_elec_kg_per_kwh_2030 * kg.co2_multiplier_elec + gas_m3 * kg.co2_gas_kg_per_m3 * kg.co2_multiplier_gas

    co2_per_weq_now = co2_now / aantal_weq if aantal_weq > 0 else 0.0
    co2_per_weq_2030 = co2_2030 / aantal_weq if aantal_weq > 0 else 0.0

    return BronResult(
        concept=inp.bron,
        aantal_weq=aantal_weq,
        warmtevraag_per_weq_gj=warmtevraag_per_weq_gj,
        capaciteitsvraag_per_weq_kw=cap_cv_per_weq_kw,
        warmtevraag_totaal_gj=warmtevraag_totaal_gj,
        warmtevraag_verliezen_gj=warmtevraag_verliezen_gj,
        warmtevraag_incl_verlies_gj=warmtevraag_incl_verlies_gj,
        ontwerpvermogen_kw=ontwerpvermogen_kw,
        investering_per_weq_eur=investering_per_weq,
        kapitaallasten_per_weq_eur_per_jaar=kap_per_weq,
        bo_per_weq_eur_per_jaar=bo_per_weq,
        energiekosten_per_weq_eur_per_jaar=energiekosten_per_weq,
        elec_kwh_per_weq=elec_kwh_per_weq,
        gas_m3_per_weq=gas_m3_per_weq,
        co2_kg_per_weq_now=co2_per_weq_now,
        co2_kg_per_weq_2030=co2_per_weq_2030,
        cap_wp_mw=cap_wp_mw,
        kengetallen=kg
    )
