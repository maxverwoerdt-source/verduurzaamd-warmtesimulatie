# VERduurzaamd warmtesimulatie

De rekenuitkomsten blijven gebaseerd op het Excel-rekenmodel. Python verzorgt invoer, bronselectie, tijdelijke werkbestanden, herberekening via LibreOffice en presentatie van resultaten.

## Rekenen
- De berekeningsinvoer wordt rechtstreeks gezet op `Kosten bronnen` en `Kosten leidingwerk`.
- De collectieve bronnen worden in één LibreOffice-herberekening naast elkaar berekend. De oude `X.ZOEKEN`-formules in de actieve Input-uitvoer worden niet meer gebruikt.
- Individuele alternatieven worden in dezelfde workbook-run berekend.
- Iedere berekening heeft eigen tijdelijke bestanden en een eigen LibreOffice-profiel.
- Gelijktijdigheid is begrensd via `CALC_CONCURRENCY` (standaard 2).

## Logging
Elke berekening krijgt een ID, start/eindtijd, status, duur, parameters, geselecteerde bronnen en eventuele foutmelding. Logging gebeurt in SQLite. De beveiligde endpoint `/<APP_SECRET_PATH>/api/logs` geeft de laatste 100 berekeningen terug.

`LOG_DIR` kan worden ingesteld op een persistent volume. Zonder persistent Render-disk zijn logs lokaal op de container en kunnen ze bij herstart/deploy verloren gaan.

## Deploy
Render gebruikt Docker en LibreOffice Calc. Stel `APP_SECRET_PATH` in (Render genereert deze via `render.yaml`).
