# VERduurzaamd warmtesimulatie

Deze versie gebruikt het herstelde native Python-rekenmodel in `p2h_model/`.
De berekening draait zonder Excel, LibreOffice of workbook-conversies. De API en
website-output blijven compatibel met de bestaande front-end. Alle warmtebronnen
worden altijd berekend; de bronselectie in de interface is alleen een weergavefilter.

## Lokaal draaien

```bash
pip install -r requirements.txt
APP_SECRET_PATH='kies-een-lange-willekeurige-url-token' python app.py
```

Open daarna `http://localhost:5000/<APP_SECRET_PATH>`.

## Deploy

Render gebruikt Docker en `render.yaml`. De `APP_SECRET_PATH` wordt door Render
gegenereerd. De rekenengine is pure Python en heeft geen Excel- of LibreOffice-
installatie nodig.
