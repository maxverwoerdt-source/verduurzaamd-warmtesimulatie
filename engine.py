"""Excel-backed calculator. Workbook formulas remain the calculation source of truth."""
from __future__ import annotations
import math, os, shutil, subprocess, tempfile, threading, logging
from pathlib import Path
import openpyxl
from time import perf_counter

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MODEL_FILE = BASE_DIR / "model" / "rekenmodel.xlsm"
# A small bounded pool prevents Render's limited memory from being exhausted.
_CALC_SEMAPHORE = threading.BoundedSemaphore(int(os.getenv("CALC_CONCURRENCY", "2")))

COLLECTIVE = [
    ("TEA", "TEA", "TEA"), ("TEO", "TEO", "TEO"),
    ("CLWP", "Centrale lucht-waterwarmtepomp", "ctr. L. wp"),
    ("OGEO", "Ondiepe geothermie", "ond. Geothermie"),
    ("REST", "Restwarmte", "restwarmte (25grC)"), ("PVT", "PVT", "PVTe"),
    ("SOLAR", "Zonthermie", "Solar"), ("P2H", "Power-to-Heat", "P2H")]
INDIVIDUAL = [("GK", "Individuele gasketel", "L"), ("LWP", "Individuele lucht-waterwarmtepomp", "J"), ("HWP", "Individuele hybride warmtepomp", "K")]
SOURCE_COL = {"TEA":"E", "TEO":"F", "CLWP":"G", "OGEO":"H", "REST":"I", "PVT":"J", "SOLAR":"K", "P2H":"L"}
SELECTOR_TO_KEY = {selector:key for key,label,selector in COLLECTIVE}


def _finite(v, cell):
    if v is None: raise RuntimeError(f"Excel gaf geen waarde terug voor {cell}.")
    try: x=float(v)
    except Exception: raise RuntimeError(f"Excel-uitkomst {cell} is niet numeriek: {v!r}")
    if not math.isfinite(x): raise RuntimeError(f"Excel-uitkomst {cell} is ongeldig.")
    return x


def _set_inputs_direct(wb, values):
    """Write inputs to calculation sheets, not via the Input sheet lookups."""
    cost = wb["Kosten bronnen"]
    pipe = wb["Kosten leidingwerk"]
    # Direct inputs to the source model (these are the former Input-sheet links).
    cost["E3"] = values["eprijs_2030"] - 0.15
    cost["E4"] = values["gasprijs_2030"] - 0.4
    cost["M14"] = values["gasprijs_2030"]
    cost["N14"] = values["eprijs_2030"]
    cost["E18"] = values["aantal_woningen"]
    cost["B19"] = values["warmtevraag"]
    # Input B20-equivalent is calculated by the existing workbook formula from B19.
    # Directly update the pipe sizing factor and home-count thresholds.
    pipe["G1"] = (values["dorp_stad_factor"] / 100 * 3 + 1
                  + (1 - values["perc_appartementen"] / 100) * 5
                  + (pipe["H13"].value if values["aantal_woningen"] > pipe["G13"].value else
                     pipe["H14"].value if values["aantal_woningen"] > pipe["G14"].value else
                     pipe["H15"].value if values["aantal_woningen"] > pipe["G15"].value else pipe["H16"].value))
    pipe["G2"] = pipe["G1"].value
    # Keep Input sheet only as a result display/compatibility surface for remaining workbook formulas.
    inp = wb["Input"]
    inp["B22"] = values["aantal_woningen"]
    inp["B23"] = values["warmtevraag"]
    inp["B24"] = values["dorp_stad_factor"] / 100
    inp["B25"] = values["perc_appartementen"] / 100
    inp["B29"] = values["gasprijs_2030"]
    inp["B30"] = values["eprijs_2030"]
    inp["B31"] = values["rendementseis"] / 100
    inp["B32"] = values["subsidie"]
    inp["B33"] = values["prijs_per_ton_co2"]
    inp["B34"] = values["netverzwaring_kosten"]
    cost["E2"] = values["rendementseis"] / 100
    return inp, cost


def _run_workbook(values, source, temp):
    if not MODEL_FILE.exists(): raise RuntimeError("Het Excel-rekenmodel ontbreekt op de server.")
    userprofile=Path(temp)/"lo-profile"
    inp=Path(temp)/"input.xlsm"
    outdir=Path(temp)/"recalc"; outdir.mkdir()
    shutil.copy2(MODEL_FILE,inp)
    wb=openpyxl.load_workbook(inp,keep_vba=True)
    ws,cost=_set_inputs_direct(wb,values)
    # Replace XLOOKUPs with direct source-column references. This removes the
    # compatibility failure in LibreOffice without changing model calculations.
    col=SOURCE_COL[source]
    ws["B26"] = source
    ws["I26"] = f"='Kosten bronnen'!{col}30"
    ws["I27"] = f"='Kosten bronnen'!{col}31"
    ws["I28"] = f"='Kosten bronnen'!{col}32"
    ws["I29"] = f"='Kosten bronnen'!{col}33-'Kosten bronnen'!{col}34"
    ws["I40"] = f"='Kosten bronnen'!{col}138"
    ws["I41"] = f"='Kosten bronnen'!{col}139"
    ws["I43"] = f"='Kosten bronnen'!{col}27*1000/'Kosten bronnen'!{col}18"
    wb.calculation.fullCalcOnLoad=True; wb.calculation.forceFullCalc=True; wb.calculation.calcMode="auto"
    wb.save(inp); wb.close()
    cmd=["libreoffice",f"-env:UserInstallation=file://{userprofile}","--headless","--convert-to","xlsx","--outdir",str(outdir),str(inp)]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
    resultfile=outdir/"input.xlsx"
    if run.returncode!=0 or not resultfile.exists():
        raise RuntimeError("Excel-rekenmodel kon niet worden herberekend: "+(run.stderr or run.stdout)[-700:])
    resultwb=openpyxl.load_workbook(resultfile,data_only=True,read_only=True)
    return resultwb,resultwb["Input"]


def _read_source(ws,col,label,key):
    capital=_finite(ws[f"{col}32"].value,f"{col}32")
    maintenance=_finite(ws[f"{col}33"].value,f"{col}33")
    energy=_finite(ws[f"{col}34"].value,f"{col}34")
    subsidy=_finite(ws[f"{col}36"].value,f"{col}36") if col=="I" else 0
    co2=_finite(ws[f"{col}45"].value,f"{col}45")
    grid=_finite(ws[f"{col}46"].value,f"{col}46")
    total=sum((capital+subsidy,maintenance,energy,co2,grid))
    return {"key":key,"label":label,"capital":capital+subsidy,"maintenance":maintenance,
            "energy":energy,"co2":co2,"grid":grid,"total":total,
            "detail":"Rechtstreeks berekend door het Excel-rekenmodel"}


def calculate(values):
    selected=set(values.get("sources") or [x[0] for x in COLLECTIVE+INDIVIDUAL])
    allowed={x[0] for x in COLLECTIVE+INDIVIDUAL}
    if not selected or not selected<=allowed: raise ValueError("Selecteer minimaal één geldige warmtebron.")
    results=[]
    # One workbook/LibreOffice recalculation per request: the source-cost columns
    # already calculate all collective concepts side-by-side.
    request_started = perf_counter()
    queue_started = perf_counter()
    with _CALC_SEMAPHORE:
        queue_seconds = perf_counter() - queue_started
        with tempfile.TemporaryDirectory(prefix="verduurzaamd-calc-") as t:
            if not MODEL_FILE.exists(): raise RuntimeError("Het Excel-rekenmodel ontbreekt op de server.")
            userprofile=Path(t)/"lo-profile"; inp=Path(t)/"input.xlsm"; outdir=Path(t)/"recalc"; outdir.mkdir()
            phase_started = perf_counter()
            shutil.copy2(MODEL_FILE,inp)
            logger.warning("CALC PHASE copy_model=%.3fs", perf_counter()-phase_started)
            phase_started = perf_counter()
            wb=openpyxl.load_workbook(inp,keep_vba=True)
            ws,cost=_set_inputs_direct(wb,values)
            logger.warning("CALC PHASE openpyxl_load_and_inputs=%.3fs", perf_counter()-phase_started)
            # No selector lookup: helper result rows calculate source-specific
            # outputs using direct references to the source and pipe worksheets.
            for key,label,selector in COLLECTIVE:
                col=SOURCE_COL[key]
                ws[f"{col}50"] = f"='Kosten bronnen'!{col}30"  # source investment
                ws[f"{col}51"] = f"='Kosten bronnen'!{col}31"  # annual capital charges
                ws[f"{col}52"] = f"='Kosten bronnen'!{col}32"  # O&M
                ws[f"{col}53"] = f"='Kosten bronnen'!{col}33-'Kosten bronnen'!{col}34"  # energy
                ws[f"{col}54"] = f"=$B$33*'Kosten bronnen'!{col}138/1000"
                ws[f"{col}55"] = f"=$B$34*'Kosten bronnen'!{col}27*1000/'Kosten bronnen'!{col}18"
                ws[f"{col}56"] = "=$I$23"
                ws[f"{col}57"] = "=$I$24"
                ws[f"{col}58"] = "=PMT($B$31,30,$B$32)"
                ws[f"{col}59"] = f"={col}51+{col}56+{col}52+{col}57+{col}53+{col}58+{col}54+{col}55"
                ws[f"{col}60"] = f"={col}51+{col}56+{col}58"
            # Keep the original input cells populated for legacy workbook formulas
            # and individual alternatives, but no XLOOKUP formulas are relied on.
            ws["B26"]="P2H"
            wb.calculation.fullCalcOnLoad=True; wb.calculation.forceFullCalc=True; wb.calculation.calcMode="auto"
            save_started = perf_counter()
            wb.save(inp); wb.close()
            save_seconds = perf_counter() - save_started
            logger.warning("CALC PHASE workbook_save=%.3fs", save_seconds)
            cmd=["libreoffice",f"-env:UserInstallation=file://{userprofile}","--headless","--convert-to","xlsx","--outdir",str(outdir),str(inp)]
            lo_started = perf_counter()
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
            lo_seconds = perf_counter() - lo_started
            logger.warning("CALC PHASE libreoffice=%.3fs returncode=%s stdout=%s stderr=%s", lo_seconds, run.returncode, (run.stdout or "")[-300:], (run.stderr or "")[-300:])
            resultfile=outdir/"input.xlsx"
            if run.returncode!=0 or not resultfile.exists():
                raise RuntimeError("Excel-rekenmodel kon niet worden herberekend: "+(run.stderr or run.stdout)[-700:])
            phase_started = perf_counter()
            resultwb=openpyxl.load_workbook(resultfile,data_only=True,read_only=True)
            rws=resultwb["Input"]
            logger.warning("CALC PHASE result_load=%.3fs", perf_counter()-phase_started)
            for key,label,selector in COLLECTIVE:
                if key not in selected: continue
                col=SOURCE_COL[key]
                capital=_finite(rws[f"{col}60"].value,f"{col}60")
                maintenance=_finite(rws[f"{col}52"].value,f"{col}52")+_finite(rws[f"{col}57"].value,f"{col}57")
                energy=_finite(rws[f"{col}53"].value,f"{col}53")
                co2=_finite(rws[f"{col}54"].value,f"{col}54")
                grid=_finite(rws[f"{col}55"].value,f"{col}55")
                total=sum((capital,maintenance,energy,co2,grid))
                results.append({"key":key,"label":label,"capital":capital,"maintenance":maintenance,"energy":energy,"co2":co2,"grid":grid,"total":total,"detail":"Rechtstreeks berekend door het Excel-rekenmodel"})
            # Individual alternatives remain calculated by the workbook's native
            # formulas, also in this same recalculation.
            for key,label,col in INDIVIDUAL:
                if key in selected: results.append(_read_source(rws,col,label,key))
            resultwb.close()
            logger.warning("CALC TIMING queue=%.3fs workbook_save=%.3fs libreoffice=%.3fs total=%.3fs sources=%d", queue_seconds, save_seconds, lo_seconds, perf_counter()-request_started, len(results))
    return results
