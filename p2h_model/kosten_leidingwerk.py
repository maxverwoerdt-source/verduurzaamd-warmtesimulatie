"""
Kosten leidingwerk – generieke benadering van G1–G9 uit de sheet.

In Excel:
- G1 = Input!B24*3 + 1 + (1-Input!B25)*5 + een opslag die afhangt van Input!B22
       en drempelwaarden G13..G16 / H13..H16.
- G2 = G1
- G3..G8 = B3 + (E3-B3)/10 * $G$2  (lineaire interpolatie tussen B- en E-waardes)
- G9 = SUM(G3:G8)

Hier nemen we:
- B3..B8 en E3..E8 over als constante kengetallen;
- G1 wordt benaderd zoals de Excel-logica, met een eenvoudig drempelmodel;
- Daarmee volgt G9 de structuur van de Excel-sheet goed genoeg voor
  scenario-analyse op basis van B22 (aantal woningen), B24 (dorp/stad),
  B25 (% appartementen).
"""

from dataclasses import dataclass
from .input_params import InputParams
from .utils import _bet

@dataclass
class LeidingwerkResult:
    factor: float
    primair_net_per_weq_eur: float
    secundair_net_per_weq_eur: float
    aansluiting_per_weq_eur: float
    onderstation_per_weq_eur: float
    inpandig_per_weq_eur: float
    afleverset_per_weq_eur: float
    investering_per_weq_eur: float
    kapitaallasten_per_weq_eur_per_jaar: float
    bo_leidingwerk_per_weq_eur_per_jaar: float


B_VALUES = {
    "Primair net": 1500.0,
    "Secundair net": 4000.0,
    "Aansluitleidingen": 4800.0,
    "Onderstation": 125000/250,
    "Inpandig": 500.0,
    "Afleverset": 1250.0,
}

E_VALUES = {
    "Primair net": 8000.0,
    "Secundair net": 8400.0,
    "Aansluitleidingen": 9000.0,
    "Onderstation": 125000/150,
    "Inpandig": 1000.0,
    "Afleverset": 1250.0,
}

THRESHOLDS = [
    (999, 0.0),
    (749, 0.5),
    (499, 1.5),
    (0,   2.5),  # "onder"
]


def _extra_factor_aantal_woningen(aantal_woningen: float) -> float:
    """Benader de IF-structuur in G1 op basis van G13..G16 / H13..H16."""
    for grens, factor in THRESHOLDS:
        if aantal_woningen > grens:
            return factor
    return 2.5  # fallback


def bereken_leidingwerk(inp: InputParams) -> LeidingwerkResult:
    """Reken de G1..G9 structuur van 'Kosten leidingwerk' door.

    Output g9_sum kan gebruikt worden als eenheidsbedrag voor I22 in de Input-sheet.
    """
    opslag = _extra_factor_aantal_woningen(inp.aantal_woningen)
    factor = inp.dorp_stad_factor * 3 + 1 + (1 - inp.perc_appartementen) * 5 + opslag

    labels = [
        "Primair net",
        "Secundair net",
        "Aansluitleidingen",
        "Onderstation",
        "Inpandig",
        "Afleverset",
    ]

    g_values = []
    for label in labels:
        b = B_VALUES[label]
        e = E_VALUES[label]
        g = b + (e - b) / 10.0 * factor
        g_values.append(g)

    primair_net_per_weq, secundair_net_per_weq, aansluiting_per_weq, onderstation_per_weq, inpandig_per_weq, afleverset_per_weq = g_values
    investering_per_weq = sum(g_values)
    bo_leidingwerk = investering_per_weq * 0.009

    return LeidingwerkResult(
        factor=factor,
        primair_net_per_weq_eur=primair_net_per_weq,
        secundair_net_per_weq_eur=secundair_net_per_weq,
        aansluiting_per_weq_eur=aansluiting_per_weq,
        onderstation_per_weq_eur=onderstation_per_weq,
        inpandig_per_weq_eur=inpandig_per_weq,
        afleverset_per_weq_eur=afleverset_per_weq,
        investering_per_weq_eur=investering_per_weq,
        kapitaallasten_per_weq_eur_per_jaar=_bet(inp.rendementseis, 30, investering_per_weq),
        bo_leidingwerk_per_weq_eur_per_jaar=bo_leidingwerk
    )
