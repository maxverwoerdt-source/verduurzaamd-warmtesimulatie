from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from .input_params import InputParams

# -----------------------------
# Helpers
# -----------------------------
def _bet(rente: float, afschrijftermijn_jr: float, investering: float) -> float:
    """Equivalent van Excel: =-BET(rente; nper; pv) met jaarlijkse perioden.

    We hanteren hier een positieve annuïteit (€/jaar) op basis van:
        A = r * PV / (1 - (1 + r)^(-n))

    - rente: jaarlijkse discontovoet (bv. 0.06)
    - afschrijftermijn_jr: aantal jaren
    - investering: positief bedrag (EUR)
    """
    if investering <= 0:
        return 0.0
    if rente <= 0:
        return investering / afschrijftermijn_jr if afschrijftermijn_jr > 0 else 0.0
    return rente * investering / (1 - (1 + rente) ** (-afschrijftermijn_jr))
