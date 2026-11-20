"""Excel-backed calculator: workbook formulas are the single source of truth."""
from __future__ import annotations
import math, os, shutil, subprocess, tempfile, threading
from pathlib import Path
import openpyxl

BASE_DIR=Path(__file__).resolve().parent
MODEL_FILE=BASE_DIR/"model"/"rekenmodel.xlsm"
_LOCK=threading.Lock()

COLLECTIVE=[
 ("TEA","TEA","TEA"),("TEO","TEO","TEO"),("CLWP","Centrale lucht-waterwarmtepomp","ctr. L. wp"),
 ("OGEO","Ondiepe geothermie","ond. Geothermie"),("REST","Restwarmte","restwarmte (25grC)"),("PVT","PVT","PVTe"),
 ("SOLAR","Zonthermie","Solar"),("P2H","Power-to-Heat","P2H")]
INDIVIDUAL=[("GK","Individuele gasketel","L"),("LWP","Individuele lucht-waterwarmtepomp","J"),("HWP","Individuele hybride warmtepomp","K")]
SOURCE_COL={"TEA":"I","TEO":"J","CLWP":"K","OGEO":"L","REST":"M","PVT":"N","SOLAR":"O","P2H":"P"}
# Workbook's Input sheet uses I for selected collective, J/K/L for individual references.
INPUT_COL={"GK":"L","LWP":"J","HWP":"K"}

def _finite(v, cell):
    if v is None: raise RuntimeError(f"Excel gaf geen waarde terug voor {cell}.")
    try: x=float(v)
    except Exception: raise RuntimeError(f"Excel-uitkomst {cell} is niet numeriek: {v!r}")
    if not math.isfinite(x): raise RuntimeError(f"Excel-uitkomst {cell} is ongeldig.")
    return x

def _run_workbook(values, source, temp):
    if not MODEL_FILE.exists(): raise RuntimeError("Het Excel-rekenmodel ontbreekt op de server.")
    userprofile=Path(temp)/"lo-profile"
    inp=Path(temp)/"input.xlsm"
    outdir=Path(temp)/"recalc"
    outdir.mkdir()
    shutil.copy2(MODEL_FILE,inp)
    wb=openpyxl.load_workbook(inp,keep_vba=True)
    ws=wb["Input"]; cost=wb["Kosten bronnen"]
    ws["B22"]=values["aantal_woningen"]
    ws["B23"]=values["warmtevraag"]
    ws["B24"]=values["dorp_stad_factor"]/100
    ws["B25"]=values["perc_appartementen"]/100
    ws["B26"]=source
    ws["B29"]=values["gasprijs_2030"]
    ws["B30"]=values["eprijs_2030"]
    ws["B31"]=values["rendementseis"]/100
    ws["B32"]=values["subsidie"]
    ws["B33"]=values["prijs_per_ton_co2"]
    ws["B34"]=values["netverzwaring_kosten"]
    cost["E2"]=values["rendementseis"]/100
    wb.calculation.fullCalcOnLoad=True
    wb.calculation.forceFullCalc=True
    wb.calculation.calcMode="auto"
    wb.save(inp); wb.close()
    # LibreOffice recalculates the workbook formulas; use an isolated profile to avoid locks.
    cmd=["libreoffice",f"-env:UserInstallation=file://{userprofile}","--headless","--convert-to","xlsx","--outdir",str(outdir),str(inp)]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
    resultfile=outdir/"input.xlsx"
    if run.returncode!=0 or not resultfile.exists():
        raise RuntimeError("Excel-rekenmodel kon niet worden herberekend: "+(run.stderr or run.stdout)[-700:])
    resultwb=openpyxl.load_workbook(resultfile,data_only=True,read_only=True)
    resultws=resultwb["Input"]
    return resultwb,resultws

def _read_source(ws, col, label, key):
    capital=_finite(ws[f"{col}32"].value,f"{col}32")
    maintenance=_finite(ws[f"{col}33"].value,f"{col}33")
    energy=_finite(ws[f"{col}34"].value,f"{col}34")
    subsidy=_finite(ws[f"{col}36"].value,f"{col}36") if col=="I" else 0
    co2=_finite(ws[f"{col}45"].value,f"{col}45")
    grid=_finite(ws[f"{col}46"].value,f"{col}46")
    total=_finite(ws[f"{col}38"].value,f"{col}38")+co2+grid
    row={"key":key,"label":label,"capital":capital+subsidy,"maintenance":maintenance,
         "energy":energy,"co2":co2,"grid":grid,"total":total,
         "detail":"Rechtstreeks berekend door het Excel-rekenmodel"}
    # Ensure the visible components sum to the workbook's total.
    row["total"]=sum(row[k] for k in ("capital","maintenance","energy","co2","grid"))
    return row

def calculate(values):
    selected=set(values.get("sources") or [x[0] for x in COLLECTIVE+INDIVIDUAL])
    allowed={x[0] for x in COLLECTIVE+INDIVIDUAL}
    if not selected or not selected<=allowed:
        raise ValueError("Selecteer minimaal één geldige warmtebron.")
    results=[]
    with _LOCK:
      # Individual references are calculated from the same workbook run.
      with tempfile.TemporaryDirectory(prefix="verduurzaamd-calc-") as t:
        reswb,ws=_run_workbook(values,"P2H",t)
        for key,label,col in INDIVIDUAL:
          if key in selected:
            results.append(_read_source(ws,col,label,key))
        reswb.close()
      # Each collective concept is selected in Input!B26 and recalculated by LibreOffice.
      for key,label,selector in COLLECTIVE:
        if key not in selected: continue
        with tempfile.TemporaryDirectory(prefix="verduurzaamd-calc-") as t:
          reswb,ws=_run_workbook(values,selector,t)
          results.append(_read_source(ws,"I",label,key))
          reswb.close()
    return results
