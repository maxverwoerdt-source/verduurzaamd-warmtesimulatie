# VERduurzaamd Warmtesimulatie

Webapp voor het vergelijken van jaarlijkse kosten van verschillende warmteconcepten. De berekeningen worden uitgevoerd met het Excel-rekenmodel van VERduurzaamd.

## Installatie / deployment

De applicatie is ingericht voor deployment op Render via de meegeleverde `render.yaml` en Dockerfile. Stel de omgevingsvariabele `APP_SECRET_PATH` in op een willekeurige geheime URL-string van minimaal 20 tekens.

## Berekeningen en snelheid

LibreOffice wordt bij het starten van de service als permanente rekenservice gestart. Het Excel-rekenmodel wordt vervolgens één keer geladen en in het geheugen gehouden. Per aanvraag worden alleen de invoercellen bijgewerkt, het model herberekend en de uitkomsten uitgelezen. Aanvragen worden kort geserialiseerd zodat invoer en resultaten van verschillende gebruikers niet door elkaar lopen.

Alle 11 warmtebronnen worden in één run berekend. De berekening kan nog enkele seconden duren; bij een koude start kan de eerste aanvraag langer duren. De website toont hiervoor een melding aan de gebruiker.

De server logt per berekening de fasetijden: model klaarzetten, inputs schrijven, LibreOffice herberekenen, resultaten uitlezen en totale engine-tijd. Zoek in Render Logs naar `CALC PHASE` en `CALC TIMING`.

De warmtebron-checkboxes zijn uitsluitend grafiekfilters. Alle 11 bronnen worden altijd berekend en blijven beschikbaar in de resultaten-/CSV-tabel. Filters kunnen ook na een berekening worden aangepast.
