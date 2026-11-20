from dataclasses import dataclass, asdict

@dataclass
class InputParams:
    """Parameters zoals ingevuld in Input!B22–B34.

    Velden:
        B22: aantal_woningen
        B23: warmtevraag_inschatting (GJ/jaar per woning)
        B24: dorp_stad_factor       (0–1, meer stedelijk = hoger)
        B25: perc_appartementen     (0–1)
        # B26: bron                   (bv. "P2H")
        B29: gasprijs_2030          (€/m3)
        B30: eprijs_2030            (€/kWh)
        B31: rendementseis          (fractie, bv. 0.04)
        B32: subsidie_lumpsum       (€/weq of totaalproject, afhankelijk van model)
        B33: prijs_per_ton_co2      (€/ton)
        B34: netverzwaring_kosten   (€/kW)
    """

    aantal_woningen: float
    warmtevraag_inschatting: float
    dorp_stad_factor: float
    perc_appartementen: float
    bron: str
    gasprijs_2030: float
    eprijs_2030: float
    rendementseis: float
    subsidie_lumpsum: float
    prijs_per_ton_co2: float
    netverzwaring_kosten: float

    @classmethod
    def from_dict(self, d: dict) -> "InputParams":
        return self(
            aantal_woningen      = max(1, min(10000000, float(d["aantal_woningen"]))),
            warmtevraag_inschatting = max(1, min(1000, float(d.get("warmtevraag", 30.0)))),
            dorp_stad_factor     = max(0, min(1, float(d.get("dorp_stad_factor", 0.0)/100))),
            perc_appartementen   = max(0, min(1, float(d.get("perc_appartementen", 0.0)/100))),
            bron                 = "",
            gasprijs_2030        = max(0.001, min(1000, float(d.get("gasprijs_2030", 1.7)))),
            eprijs_2030          = max(0.001, min(1000, float(d.get("eprijs_2030", 0.25)))),
            rendementseis        = max(0, min(1, float(d.get("rendementseis", 0.0)/100))),
            subsidie_lumpsum     = max(0, min(10000, float(d.get("subsidie", 0.0)))),
            prijs_per_ton_co2    = max(0, min(10000, float(d.get("prijs_per_ton_co2", 0.0)))),
            netverzwaring_kosten = max(0, min(10000, float(d.get("netverzwaring_kosten", 0.0)))),
        )

    def to_dict(self) -> dict:
        return asdict(self)
