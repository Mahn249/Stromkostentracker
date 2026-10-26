# Version 0.1.0
erste Alpha Verion zum live testen.
## Known Bugs:
- nach jedem Update muss das Frontend zwangsweisen neu geladen werden (manuell)
- der Sensor "aktueller Arbeitspreis" wird nicht als Zahl für das Energy Dashboard erkannt
- auf schmalen Bildschirmen passt die Lovelace Karte noch nicht ganz

## geplante Ädnerungen
- Verbrauchserfassung über Leistung entfernen, da nicht genau genug: zu kleine Verbrauchsbereiche werden als 0 gezählt und daher nicht zur Berechnung herangezogen.
  - Nutzer mit ausschlißlich Watt Sensoren müssen sich einen eigenen Helfer in HA erzeugen, (am besten dergleiche, der auch im HA-Energy-Dashboard herangezogen wird.)
- Nur gültige Zählerstände in die Datenbank schreiben, so bleiben veraltete Checkpoints gültig
- Schalter "Entwickleransicht" in den Integrationseinstellungen = zusätzlich auf der Karte anzeigen: 
  - letzter gespeicherter Messpunkt (Zeitpunkt und Delta zum vorherigen Messpunkt)
  - Datenqualität ( längster Zeitrum zwischen einzelnen Checkpoints in den letzten 24h)
  - Zeitraum der Karte über [HA-Funktion, energy-Date-Picker](https://www.home-assistant.io/dashboards/energy/#energy-date-picker) anpassbar gestalten.
  

