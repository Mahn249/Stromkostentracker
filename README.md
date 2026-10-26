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

In den Integrationseinstellungen kannst du unter **Verbrauchserfassung konfigurieren** einen Energiesensor mit der Geräteklasse `energy` und der Einheit `kWh` wählen. Die Zustandsklasse ist nicht eingeschränkt. Leistungssensoren und Energiesensoren mit einer anderen Einheit werden nicht unterstützt. Der Zählerstand wird fest alle 10 Minuten erfasst. Bei jeder Erfassung werden der letzte Checkpoint, der neue Zählerstand, das Intervall und die Differenz in einer SQLite-Transaktion gemeinsam gespeichert. Ein erster Messwert, ein Wechsel der Entität und ein Zählerrückgang erhalten eine unbekannte Differenz (`NULL`); es wird keine Differenz zwischen verschiedenen Zählern oder über einen Zählerrückgang hinweg berechnet. Ungültige oder nicht verfügbare Messwerte werden nicht gespeichert und verändern den Checkpoint nicht.

Tages- und Monatskosten basieren auf denselben Intervallen. Intervalle, die lokale Mitternacht, Monats- oder Tarifgrenzen überqueren, werden nach ihrer verstrichenen UTC-Zeit aufgeteilt. Das setzt gleichmäßigen Verbrauch im Intervall voraus; es ist keine zusätzliche Messung. Der letzte Teil erhält den verbleibenden Anteil, damit die Teilmengen zusammen dem ursprünglichen Verbrauch entsprechen. Berechnungen verwenden Dezimalzahlen ohne Zwischenrundung. Grundkosten werden nach der bestehenden Regel als Monatsgrundpreis geteilt durch die Kalendertage des Monats berechnet, auch wenn Verbrauchsdaten fehlen. Bekannte Grund- und Verbrauchskosten werden getrennt ausgewiesen; bei Lücken bleibt der nicht rekonstruierbare Verbrauch unbekannt.

Die Tarifverwaltung liest und ändert direkt die Tabellen in `energy_cost_tracker.db`. Die Datenbank wird in den Home-Assistant-Konfigurationsordner neben `configuration.yaml` abgelegt.

## Lovelace-Karte
 Solange die Integration eingerichtet ist, wird das Kartenmodul automatisch im Home-Assistant-Frontend geladen. Füge die Karte im Dashboard-Editor über **Karte hinzufügen → Stromkostentracker** hinzu. Ansicht, Monat und Jahr werden über Dropdown-Felder gewählt; im Jahres-Dropdown stehen die Jahre mit gespeicherten Messdaten zur Verfügung. In der Monatsansicht werden tägliche Kosten und Tagesabschlag verglichen. In der Jahresansicht zeigt jeder Balken die Kosten eines Monats im Vergleich zum Monatsabschlag. Für den laufenden Monat werden Kosten und Abschlag bis heute verglichen; zukünftige Monate haben keine Verbrauchskosten.


# Datenstruktur
Alle User-Daten liegen in `energy_cost_tracker.db`. Die Datenbank enthält folgende Tabellen:

## meter_intervals
`[id, interval_start_utc, interval_end_utc, consumption_meter_kwh, feed_in_meter_kwh, consumption_delta_kwh, note, source, consumption_meter_start_kwh]`

## meter_checkpoint
Enthält den zuletzt transaktional gespeicherten Zählerstand und die zugehörige Entität:
`[id, entity_id, value_kwh, timestamp_utc]`

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
