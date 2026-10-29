# work in Progress
- siehe changelog.md für Historie

# Stromkostentracker
Datenbank zur Darstellung von historischen Tarifen, Abschlägen und Verbräuchen.
Eine Custom Integration für Home Assistant zur Berechnung von Stromkosten auf Basis des täglichen Energieverbrauchs.

# Konfiguration
Nach der Installation müssen Tarfie und Abschläge mit ihren entsprechenden Zeiträumen in den Einstellungen der Integration eingerichtet werden.
In den Integrationseinstellungen wählst du unter **Verbrauchserfassung konfigurieren** einen Energiesensor mit der Geräteklasse `energy` und der Einheit `kWh`. Leistungssensoren und Energiesensoren mit einer anderen Einheit werden nicht unterstützt.
Dann fügst du Abschlagszeitraäume und Tarife inkl. ihrer Zeiträume hinzu.

Zu guter Letzt platzierst du die Lovelace-Karte auf einem deiner Dashboards.
Füge die Karte im Dashboard-Editor über **Karte hinzufügen → Stromkostentracker** hinzu.

# Funktionen

- Täglichen Stromverbrauch erfassen
- Historische Arbeitspreise und Grundpreise importieren
- Tages- Monats- und Jahreskosten berechnen
- Kosten und Abschläge als Karte in einem Diagramm anzeigen

## Arbeitsweise

Die Integration liegt unter `custom_components/stromkostentracker`. Sie stellt in Home Assistant eine native Optionsverwaltung für Tarif- und Abschlagszeiträume bereit. Dort lassen sich Name, Gültigkeitsbeginn, Gültigkeitsende(optional) und die jeweiligen Beträge hinzufügen, bearbeiten und löschen. Bei Abschlägen kann zusätzlich eine Anmerkung hinterlegt werden.

Der Sensor **Aktueller Arbeitspreis** stellt den Arbeitspreis des aktuell gültigen Tarifs in `EUR/kWh` bereit. Gibt es für heute keinen gültigen Tarif, ist sein Zustand `unknown`. Er wird beim Start, bei Tarifänderungen und um Mitternacht aktualisiert.

 Der Zählerstand wird alle 10 Minuten erfasst. Der Zählerstand am Intervallende und der vorherige Stand desselben Sensors werden in die Tabelle `meter_intervals`der Datenbank `energy_cost_tracker.db` gespeichert. Der erste Messpunkt eines Sensors hat keinen Startzählerstand; rückläufige Zählerstände ergeben in der Lovelace-Berechnung einen unbekannten Verbrauch. Ungültige oder nicht verfügbare Messwerte werden nicht gespeichert.

Tages- und Monatskosten basieren auf denselben Intervallen. Intervalle, die lokale Mitternacht, Monats- oder Tarifgrenzen überqueren, werden nach ihrer verstrichenen UTC-Zeit aufgeteilt. Das setzt gleichmäßigen Verbrauch im Intervall voraus; es ist keine zusätzliche Messung. Der letzte Teil erhält den verbleibenden Anteil, damit die Teilmengen zusammen dem ursprünglichen Verbrauch entsprechen. Berechnungen verwenden Dezimalzahlen ohne Zwischenrundung. Grundkosten werden nach der bestehenden Regel als Monatsgrundpreis geteilt durch die Kalendertage des Monats berechnet, auch wenn Verbrauchsdaten fehlen. Bekannte Grund- und Verbrauchskosten werden getrennt ausgewiesen; bei Lücken bleibt der nicht rekonstruierbare Verbrauch unbekannt.

Die Tarifverwaltung liest und ändert direkt die Tabellen in `energy_cost_tracker.db`. Die Datenbank wird in den Home-Assistant-Konfigurationsordner neben `configuration.yaml` abgelegt.

## Lovelace-Karte
 Solange die Integration eingerichtet ist, wird das Kartenmodul automatisch im Home-Assistant-Frontend geladen.  Ansicht, Monat und Jahr werden über Dropdown-Felder gewählt; im Jahres-Dropdown stehen die Jahre mit gespeicherten Messdaten zur Verfügung. In der Monatsansicht werden tägliche Kosten und Tagesabschlag verglichen. In der Jahresansicht zeigt jeder Balken die Kosten eines Monats im Vergleich zum Monatsabschlag. Für den laufenden Monat werden Kosten und Abschlag bis heute verglichen; zukünftige Monate haben keine Verbrauchskosten.


## Datenstruktur
Alle User-Daten liegen in `energy_cost_tracker.db`. Die Datenbank enthält folgende Tabellen:

### meter_intervals
`[id, interval_start_utc, interval_end_utc, consumption_meter_kwh, consumption_meter_start_kwh, note]`

### tariffs
`[id, name, valid_from, valid_until, work_price_per_kwh, base_price_per_month]`

### payments
`[id, name, valid_from, valid_until, amount_eur, note]`

# Import von historischen Daten

Historische Messdaten lassen sich in den Optionen der Integration unter **Altdaten importieren** als `.xlsx`-Datei hochladen. Home Assistant prüft vor dem Import die Spaltenüberschriften und Messwerte, zeigt eine Vorschau mit Zeitraum und möglichen Duplikaten und importiert erst nach Bestätigung. Bei fehlerhaften Zeilen wird der gesamte Import gestoppt; korrigiere die Datei und lade sie erneut hoch.

| Von (UTC nach ISO 8601) | Bis (UTC nach ISO 8601) | Zählerstand - Verbrauch (kWh) | Delta (Verbrauch) in kWh | Anmerkung |
| :--- | :--- | ---: | ---: | :--- |
| 2025-07-25T00:00:00Z | 2025-07-25T00:14:59Z | 26087,284 | 0,135 | Abgelesen |

Die Quelle wird nicht aus der Excel-Datei gelesen. Der Importer ergänzt `manual_import` in der Spalte `note`; automatisch erfasste Messwerte enthalten dort die Entity-ID des Zählersensors.

Bereits vorhandene importierte Intervalle werden übersprungen.

Die Lovelace-API berechnet den Verbrauch je Intervall als Differenz aus `consumption_meter_kwh` und `consumption_meter_start_kwh`. Beim Excel-Import wird der Startzählerstand aus Zählerstand minus Excel-Delta abgeleitet; das Delta wird nicht als eigene Datenbankspalte gespeichert.