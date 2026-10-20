# work in Progress
- nach jedem Update muss das Frontend zwangsweisen neu geladen werden (manuell)
- der Sensor "aktueller Arbeitspreis" wird nicht als Zahl für das Energy Dashboard erkannt
- auf schmalen Bildschirmen passt die Lovelace Karte noch nicht ganz
- Design der Karte ist noch nicht anpassbar

# Stromkostentracker
Datenbank zur Darstellung von historischen Tarifen, Abschlägen und Verbräuchen.
Eine Custom Integration für Home Assistant zur Berechnung von Stromkosten auf Basis des täglichen Energieverbrauchs.

# Konfiguration
Nach der Installation müssen Tarfie und Abschläge mit ihren entsprechenden Zeiträumen in den Einstellungen der Integration eingerichtet werden.

# Funktionen

- Täglichen Stromverbrauch erfassen
- Historische Arbeitspreise und Grundpreise importieren
- Tages- Monats- und Jahreskosten berechnen
- Kosten und Abschläge als Karte in einem Diagramm anzeigen

## Arbeitsweise

Die Integration liegt unter `custom_components/stromkostentracker`. Sie stellt in Home Assistant eine native Optionsverwaltung für Tarif- und Abschlagszeiträume bereit. Dort lassen sich Name, Gültigkeitsbeginn, optionales Gültigkeitsende und die jeweiligen Beträge hinzufügen, bearbeiten und löschen. Bei Abschlägen kann zusätzlich eine Anmerkung hinterlegt werden.

Der Sensor **Aktueller Arbeitspreis** stellt den Arbeitspreis des am heutigen lokalen Datum gültigen Tarifs in `EUR/kWh` bereit. Gibt es für heute keinen gültigen Tarif, ist sein Zustand `unknown`. Er wird beim Start, bei Tarifänderungen und um Mitternacht aktualisiert.

In den Integrationseinstellungen kannst du unter **Verbrauchserfassung konfigurieren** einen Sensor mit der Einheit `W` oder `kWh` und ein Erfassungsintervall von 1 bis 1440 Minuten (-> Messperiode) wählen. Ein Leistungssensor mit der EInheit `W` wird anhand der linken Riemann-Summe integriert und in kWh umgerechnet; ein Energie-Sensor mit der EInheit `kWh` wird durch Differenz zwischen Anfangs- und Endzählerstand der Messperiode ausgewertet. Die Daten werden am Ende jedes Intervalls in die Tabelle `meter_intervals` der Datenbank geschrieben. Als `source` wird die `entity_id` des ausgewählten Sensors gespeichert. Bei Zählerstandssensoren enthält `consumption_meter_start_kwh` den Startwert und `consumption_meter_kwh` den Endwert des Intervalls.

Nach einem Home-Assistant-Neustart beginnt ein neues Intervall ab dem Neustart; nicht beobachtete Leistung während der Ausfallzeit wird nicht geschätzt. Intervalle mit nicht verfügbaren Leistungswerten werden ausgelassen.

Die Tarifverwaltung liest und ändert direkt die Tabellen in `energy_cost_tracker.db`. Die Datenbank wird in den Home-Assistant-Konfigurationsordner neben `configuration.yaml` abgelegt.

## Lovelace-Karte
 Solange die Integration eingerichtet ist, wird das Kartenmodul automatisch im Home-Assistant-Frontend geladen. Füge die Karte im Dashboard-Editor über **Karte hinzufügen → Stromkostentracker** hinzu. Ansicht, Monat und Jahr werden über Dropdown-Felder gewählt; im Jahres-Dropdown stehen die Jahre mit gespeicherten Messdaten zur Verfügung. In der Monatsansicht werden tägliche Kosten und Tagesabschlag verglichen. In der Jahresansicht zeigt jeder Balken die Kosten eines Monats im Vergleich zum Monatsabschlag. Für den laufenden Monat werden Kosten und Abschlag bis heute verglichen; zukünftige Monate haben keine Verbrauchskosten.


# Datenstruktur
Alle User-Daten liegen in `energy_cost_tracker.db`. Die Datenbank enthält folgende Tabellen:

## meter_intervals
`[id, interval_start_utc, interval_end_utc, consumption_meter_kwh, feed_in_meter_kwh, consumption_delta_kwh, note, source, consumption_meter_start_kwh]`

## tariffs
`[id, name, valid_from, valid_until, work_price_per_kwh, base_price_per_month]`

## payments
`[id, name, valid_from, valid_until, amount_eur, note]`

## Import von historischen Daten

Historische Messdaten lassen sich in den Optionen der Integration unter **Altdaten importieren** als `.xlsx`-Datei hochladen. Home Assistant prüft vor dem Import die Spaltenüberschriften und Messwerte, zeigt eine Vorschau mit Zeitraum und möglichen Duplikaten und importiert erst nach Bestätigung. Bei fehlerhaften Zeilen wird der gesamte Import gestoppt; korrigiere die Datei und lade sie erneut hoch.

| Von (UTC nach ISO 8601) | Bis (UTC nach ISO 8601) | Zählerstand - Verbrauch (kWh) | Zählerstand - Einspeisung (kWh) | Delta (Verbrauch) in kWh | Anmerkung |
| :--- | :--- | ---: | ---: | ---: | :--- |
| 2025-07-25T00:00:00Z | 2025-07-25T00:14:59Z | 26087,284 | 275,367 | 0,135 | Abgelesen |

Bereits vorhandene Intervalle mit derselben Quelle werden übersprungen.
