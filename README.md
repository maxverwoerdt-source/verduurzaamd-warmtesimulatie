# VERduurzaamd Warmtesimulatie

Webapp voor het vergelijken van jaarlijkse kosten van verschillende warmteconcepten. De berekeningen worden uitgevoerd met het Excel-rekenmodel van VERduurzaamd.

## Installatie / deployment

De applicatie is ingericht voor deployment op Render via de meegeleverde `render.yaml` en Dockerfile. Stel de omgevingsvariabele `APP_SECRET_PATH` in op een willekeurige geheime URL-string van minimaal 20 tekens.

## Berekeningen

Alle warmtebronnen worden in één run van het Excel-rekenmodel doorgerekend. De berekening kan tientallen seconden duren. De website toont hiervoor een melding aan de gebruiker.

## Warmtebronnen

Collectief: TEA, TEO, centrale lucht-waterwarmtepomp, ondiepe geothermie, restwarmte, PVT, zonthermie en Power-to-Heat.

Individuele referenties: lucht-waterwarmtepomp, hybride warmtepomp en gasketel.
