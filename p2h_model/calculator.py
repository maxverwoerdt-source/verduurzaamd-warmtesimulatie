from .input_params import InputParams
from .kosten_bronnen import bereken_kosten_bron, BronResult
from .kosten_leidingwerk import bereken_leidingwerk, LeidingwerkResult
from .kosten_individueel import bereken_individueel, IndividueelResult
from .utils import _bet
from dataclasses import dataclass, asdict

@dataclass
class TotaalResult:
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

def bereken_totaal(inp: InputParams, bron_res: BronResult, lw_res: LeidingwerkResult) -> TotaalResult:
    inv = bron_res.investering_per_weq_eur + lw_res.investering_per_weq_eur
    kap = bron_res.kapitaallasten_per_weq_eur_per_jaar + lw_res.kapitaallasten_per_weq_eur_per_jaar
    bo = bron_res.bo_per_weq_eur_per_jaar + lw_res.bo_leidingwerk_per_weq_eur_per_jaar
    energie = bron_res.energiekosten_per_weq_eur_per_jaar
    sub = abs(_bet(inp.rendementseis, 30, inp.subsidie_lumpsum))
    tot = kap + bo + energie - sub
    co2 = bron_res.co2_kg_per_weq_now * inp.prijs_per_ton_co2 / 1000
    kwe_divisor = bron_res.kengetallen.kwe_divisor
    net = bron_res.cap_wp_mw / kwe_divisor * 1000 * inp.netverzwaring_kosten / inp.aantal_woningen

    return TotaalResult(
        investering_per_weq_eur=inv,
        kapitaallasten_per_weq_eur_per_jaar=kap,
        bo_per_weq_eur_per_jaar=bo,
        energiekosten_per_weq_eur_per_jaar=energie,
        subsidies_per_weq_eur_per_jaar=sub,
        totaal_per_weq_eur_per_jaar=tot,
        elec_kwh_per_weq=bron_res.elec_kwh_per_weq,
        gas_m3_per_weq=bron_res.gas_m3_per_weq,
        co2_kg_per_weq_now=bron_res.co2_kg_per_weq_now,
        co2_kg_per_weq_2030=bron_res.co2_kg_per_weq_2030,
        co2_kosten_per_weq_eur=co2,
        net_kosten_per_weq_eur=net,
    )

def bereken_model(input_vals: dict) -> dict:
    inp = InputParams.from_dict(input_vals)
    results = {}

    # Bereken collectieve opties
    for col_bron in ["TEA", "TEO", "REST", "CLWP", "OGEO", "P2H", "PVTE", "SOLAR"]:
        inp.bron = col_bron
        bron_res = bereken_kosten_bron(inp)
        lw_res = bereken_leidingwerk(inp)
        tot_res = bereken_totaal(inp, bron_res, lw_res)
        results[col_bron] = tot_res.to_dict()

    # Bereken individuele opties
    for ind_bron in ["GK", "LWP", "HWP"]:
        inp.bron = ind_bron
        results[ind_bron] = bereken_individueel(inp).to_dict()

    # Maak JS-plotvriendelijke series: [{name, x, y}, ...]
    metrics = list(next(iter(results.values())).keys())
    bronnen = list(results.keys())
    series = [
        {
            "name": metric,
            "x": bronnen,
            "y": [results[bron].get(metric, 0.0) for bron in bronnen],
        }
        for metric in metrics
    ]

    return series