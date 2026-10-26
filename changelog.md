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

# Version 0.2.0
- Die Verbrauchserfassung akzeptiert Energiesensoren mit Geräteklasse `energy` und Einheit `kWh`, unabhängig von der Zustandsklasse.
- Messwert, Verbrauchsintervall und Checkpoint werden gemeinsam in einer SQLite-Transaktion gespeichert.
- Fehlende, ungültige oder nicht rekonstruierbare Verbräuche bleiben unbekannt; Zählerwechsel erzeugen keine Differenz zwischen verschiedenen Entitäten.
- Das Erfassungsintervall ist fest auf 10 Minuten gesetzt; die Option wurde aus den Einstellungen entfernt.
- Tages- und Monatskosten verwenden dieselbe zeitanteilige Intervallaufteilung über lokale Tages-, Monats- und Tarifgrenzen; Grund- und Verbrauchskosten werden getrennt berechnet.
