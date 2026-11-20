"""Excel-backed calculator. All heat sources are calculated in one workbook run."""
from __future__ import annotations
import math, shutil, subprocess, tempfile, threading, time, logging
from pathlib import Path
import openpyxl

BASE_DIR=Path(__file__).resolve().parent
logger=logging.getLogger(__name__)

def _memory_snapshot():
    """Return Linux process/cgroup memory metrics when available."""
    metrics=[]
    try:
        with open('/proc/self/status', encoding='utf-8') as f:
            for line in f:
                if line.startswith(('VmRSS:', 'VmHWM:')):
                    metrics.append(line.strip().replace(' ', '='))
    except OSError:
        pass
    for label, path in (('cgroup_current', '/sys/fs/cgroup/memory.current'),
                        ('cgroup_peak', '/sys/fs/cgroup/memory.peak')):
        try:
            with open(path, encoding='utf-8') as f:
                metrics.append(f'{label}={int(f.read().strip())/1024/1024:.1f}MB')
        except (OSError, ValueError):
            pass
    return ' '.join(metrics) or 'memory_metrics_unavailable'

MODEL_FILE=BASE_DIR/"model"/"rekenmodel.xlsm"
_LOCK=threading.Lock()
SOURCES=[
 ("TEA","TEA","I",True),("TEO","TEO","J",True),
 ("CLWP","Centrale lucht-waterwarmtepomp","K",True),
 ("OGEO","Ondiepe geothermie","L",True),
 ("REST","Restwarmte","M",True),("PVT","PVT","N",True),
 ("SOLAR","Zonthermie","O",True),("P2H","Power-to-Heat","P",True),
 ("LWP","Individuele lucht-waterwarmtepomp","Q",False),
 ("HWP","Individuele hybride warmtepomp","R",False),
 ("GK","Individuele gasketel","S",False),
]

def _finite(v, cell):
    if v is None: raise RuntimeError(f"Excel gaf geen waarde terug voor {cell}.")
    try: x=float(v)
    except Exception: raise RuntimeError(f"Excel-uitkomst {cell} is niet numeriek: {v!r}")
    if not math.isfinite(x): raise RuntimeError(f"Excel-uitkomst {cell} is ongeldig.")
    return x

def _run_workbook(values, temp):
    total_start=time.perf_counter()
    if not MODEL_FILE.exists(): raise RuntimeError("Het Excel-rekenmodel ontbreekt op de server.")
    profile=Path(temp)/"lo-profile"
    inp=Path(temp)/"input.xlsm"
    outdir=Path(temp)/"recalc"; outdir.mkdir()
    t=time.perf_counter(); shutil.copy2(MODEL_FILE,inp); logger.warning("CALC PHASE model_copy=%.3fs memory=%s",time.perf_counter()-t,_memory_snapshot())
    t=time.perf_counter(); wb=openpyxl.load_workbook(inp,keep_vba=True); ws=wb["Input"]
    inputs={
      "B22":values["aantal_woningen"],"B23":values["warmtevraag"],
      "B24":values["dorp_stad_factor"]/100,"B25":values["perc_appartementen"]/100,
      "B29":values["gasprijs_2030"],"B30":values["eprijs_2030"],
      "B31":values["rendementseis"]/100,"B32":values["subsidie"],
      "B33":values["prijs_per_ton_co2"],"B34":values["netverzwaring_kosten"]}
    for cell,value in inputs.items(): ws[cell]=value
    wb.calculation.fullCalcOnLoad=True; wb.calculation.forceFullCalc=True; wb.calculation.calcMode="auto"
    logger.warning("CALC PHASE model_load_and_inputs=%.3fs memory=%s",time.perf_counter()-t,_memory_snapshot())
    t=time.perf_counter(); wb.save(inp); wb.close(); logger.warning("CALC PHASE workbook_save=%.3fs memory=%s",time.perf_counter()-t,_memory_snapshot())
    t=time.perf_counter(); cmd=["libreoffice",f"-env:UserInstallation=file://{profile}","--headless","--convert-to","xlsx","--outdir",str(outdir),str(inp)]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
    resultfile=outdir/"input.xlsx"
    logger.warning("CALC PHASE libreoffice=%.3fs returncode=%s memory=%s",time.perf_counter()-t,run.returncode,_memory_snapshot())
    if run.returncode!=0 or not resultfile.exists():
      raise RuntimeError("Excel-rekenmodel kon niet worden herberekend: "+(run.stderr or run.stdout)[-700:])
    t=time.perf_counter(); resultwb=openpyxl.load_workbook(resultfile,data_only=True,read_only=True); ws_result=resultwb["Input"]
    logger.warning("CALC PHASE results_load=%.3fs memory=%s",time.perf_counter()-t,_memory_snapshot())
    logger.warning("CALC TIMING workbook_total=%.3fs memory=%s",time.perf_counter()-total_start,_memory_snapshot())
    return resultwb,ws_result

def _read_source(ws,key,label,col,collective):
    capital=_finite(ws[f"{col}32"].value,f"{col}32")
    if collective: capital += _finite(ws[f"{col}36"].value,f"{col}36")
    maintenance=_finite(ws[f"{col}33"].value,f"{col}33")
    energy=_finite(ws[f"{col}34"].value,f"{col}34")
    co2=_finite(ws[f"{col}45"].value,f"{col}45")
    grid=_finite(ws[f"{col}46"].value,f"{col}46")
    return {"key":key,"label":label,"capital":capital,"maintenance":maintenance,
      "energy":energy,"co2":co2,"grid":grid,
      "total":sum((capital,maintenance,energy,co2,grid)),
      "detail":"Rechtstreeks berekend door het Excel-rekenmodel"}

def calculate(values):
    results=[]
    # All sources are always calculated; the source checkboxes are display filters only.
    with _LOCK:
      with tempfile.TemporaryDirectory(prefix="verduurzaamd-calc-") as temp:
        wb,ws=_run_workbook(values,temp)
        for key,label,col,collective in SOURCES:
          results.append(_read_source(ws,key,label,col,collective))
        wb.close()
    return results
