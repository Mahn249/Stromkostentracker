# Stromkostentracker
Datenbank zur Darstellung von historischen Tarifen, Abschlägen und Verbräuchen.
Eine Custom Integration für Home Assistant zur Berechnung von Stromkosten auf Basis des täglichen Energieverbrauchs.

## Geplante Funktionen

- Täglichen Stromverbrauch erfassen
- Historische Arbeitspreise und Grundpreise speichern
- Tages- und Monatskosten berechnen
- Kosten und Abschläge in Home Assistant anzeigen

## Home Assistant: Tarifverwaltung (erster Schritt)

Die Integration liegt unter `custom_components/stromkostentracker`. Sie stellt in Home Assistant eine native Optionsverwaltung für Tarif- und Abschlagszeiträume bereit. Dort lassen sich Name, Gültigkeitsbeginn, optionales Gültigkeitsende und die jeweiligen Beträge hinzufügen, bearbeiten und löschen. Bei Abschlägen kann zusätzlich eine Anmerkung hinterlegt werden.

Der Sensor **Aktueller Arbeitspreis** stellt den Arbeitspreis des am heutigen lokalen Datum gültigen Tarifs in `EUR/kWh` bereit. Gibt es für heute keinen gültigen Tarif, ist sein Zustand `unknown`. Er wird beim Start, bei Tarifänderungen und um Mitternacht aktualisiert.

In den Integrationseinstellungen kannst du unter **Verbrauchserfassung konfigurieren** einen Sensor mit der Einheit `W` oder `kWh` und ein Erfassungsintervall von 1 bis 1440 Minuten wählen. Ein `W`-Sensor wird anhand der linken Riemann-Summe integriert und durch Division von Wattsekunden durch 3.600.000 in kWh umgerechnet; ein `kWh`-Sensor wird durch Differenz zwischen Anfangs- und Endzählerstand ausgewertet. Die Daten werden am Ende jedes Intervalls in `meter_intervals` geschrieben. Als `source` wird die `entity_id` des ausgewählten Sensors gespeichert. Bei Zählerstandssensoren enthält `consumption_meter_start_kwh` den Startwert und `consumption_meter_kwh` den Endwert des Intervalls.

Nach einem Home-Assistant-Neustart beginnt ein neues Intervall ab dem Neustart; nicht beobachtete Leistung während der Ausfallzeit wird nicht geschätzt. Intervalle mit nicht verfügbaren Leistungswerten werden ausgelassen.

Die Tarifverwaltung liest und ändert direkt die Tabellen in `energy_cost_tracker.db`. Lege `energy_cost_tracker.db` in den Home-Assistant-Konfigurationsordner neben `configuration.yaml`; die Integration legt absichtlich keine neue Datenbank an, wenn die Datei fehlt.

Zum lokalen Testen kopiere den Ordner `custom_components/stromkostentracker` und eine separate Testkopie von `energy_cost_tracker.db` in einen eigenen Home-Assistant-Konfigurationsordner. So bleibt die Originaldatenbank unangetastet. Starte Home Assistant mit diesem Testordner und füge die Integration hinzu. Füge anschließend „Stromkostentracker“ über **Einstellungen → Geräte & Dienste → Integration hinzufügen** hinzu. Über die Optionen des Eintrags kannst du Tarifzeiträume verwalten.

# Datenstruktur
Alle bisherigen Daten liegen in `energy_cost_tracker.db`. Die Datenbank enthält folgende Tabellen:

## meter_intervals
`[id, interval_start_utc, interval_end_utc, consumption_meter_kwh, feed_in_meter_kwh, consumption_delta_kwh, note, source, consumption_meter_start_kwh]`

## tariffs
`[id, name, valid_from, valid_until, work_price_per_kwh, base_price_per_month]`

## payments
`[id, name, valid_from, valid_until, amount_eur, note]`

## Import von historischen Daten

Der Import erfolgt mit `imports/import_excel.py`. Dafür muss eine `historische_verbraeuche.xlsx` im beschriebenen Format vorliegen:

| Von (UTC nach ISO 8601) | Bis (UTC nach ISO 8601) | Zählerstand - Verbrauch (kWh) | Zählerstand - Einspeisung (kWh) | Delta (Verbrauch) in kWh | Anmerkung |
| :--- | :--- | ---: | ---: | ---: | :--- |
| 2025-07-25T00:00:00Z | 2025-07-25T00:14:59Z | 26087,284 | 275,367 | 0,135 | Abgelesen |

Der Import kann im Anschluss mit `inspect_database.py` geprüft werden.
