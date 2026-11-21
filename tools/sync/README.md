# Frame-Sync der beiden Kameras

Der Pi 3 erzeugt mit seiner Hardware-PWM einen 10-Hz-Takt auf GPIO18. Dieser Takt geht an GPIO17 **beider** Pis. Jeder Pi stempelt die Flanken in seiner eigenen Uhr und regelt das vblank seines Sensors so, dass kurz nach jeder Flanke ein Bild beginnt.
Ergebnis: beide Kameras liegen innerhalb von ca. ±8 µs (eine Sensorzeile). Wie es funktioniert und alle Messwerte: [frame-sync-2026-11-03.md](../../docs/test-reports/frame-sync-2026-11-03.md).

## Verkabelung
| Von | Nach | Wozu |
|---|---|---|
| Pi 3 Pin 12 (GPIO18, PWM) | Pi 3 Pin 11 (GPIO17) | Der Pi 3 stempelt seinen eigenen Takt (Brücke zwischen den Nachbarpins) |
| Pi 3 Pin 12 (GPIO18) | Pi Zero Pin 11 (GPIO17) | Takt zum Zero, optional über 1 kΩ |
| Pi 3 Pin 14 (GND) | Pi Zero Pin 14 (GND) | Gemeinsame Masse |

## Dateien
| Datei | Läuft auf | Inhalt |
|---|---|---|
| `camsync.c` | beiden Pis (`~/sync`) | Aufnahme und Phasen-Lock. Bauen: `gcc -O2 -Wall -o camsync camsync.c -lm` |
| `pulse.sh` | Pi 3 | PWM-Takt starten (`sudo ./pulse.sh`) und stoppen (`sudo ./pulse.sh stop`). Nicht dauerhaft, nach einem Neustart weg |
| `flash.html` | PC/Laptop | Blinkender Balken für den Bildschirmtest. ↑/↓ = Helligkeit, A = Dauerlicht zum Ausrichten |
| `run_flash_test.sh` | PC/Laptop | Nimmt auf beiden Pis gleichzeitig auf, holt die Daten nach `results/` und wertet aus |
| `flash_analyze.py` | PC/Laptop | Paart die Bilder über die gemeinsamen Flanken und misst den Versatz aus den Blitzen (braucht numpy) |

## Ablauf
1. Takt starten: `ssh pi3 'sudo ~/sync/pulse.sh'`
2. Lock prüfen, auf beiden Pis: `cd ~/sync && sudo ./camsync -t 10`. Jede Sekunde muss `LOCKED` mit e max unter ca. 10 µs erscheinen.
3. Bildschirmtest:
   1. `flash.html` öffnen, beide Kameras auf den Balken richten (`snap.pgm` jeder Aufnahme zeigt das Bild).
   2. Der Balken darf in keiner Kamera übersteuern. Bei 100 % war er auf beiden Kameras gesättigt, 60 % passte.
   3. Seite anklicken (Vollbild, das Blinken startet), dann `tools/sync/run_flash_test.sh 30`.
   4. Zum Vergleich ohne Lock: `tools/sync/run_flash_test.sh 30 -u`
4. Takt stoppen: `ssh pi3 'sudo ~/sync/pulse.sh stop'`

`run_flash_test.sh` nutzt die SSH-Aliase `pi3` und `pizero` aus `~/.ssh/config`.

## camsync-Optionen
| Option | Standard | |
|---|---|---|
| `-f` | 100 | Bildrate, muss ein ganzzahliges Vielfaches des Takts sein |
| `-p` | 10 | Takt in Hz |
| `-o` | 0,35 Bild | Versatz Flanke → Bildbeginn in µs. Auf beiden Pis gleich lassen |
| `-e` / `-g` | VTS − 50 / Treiber | Belichtung in Zeilen / Verstärkung |
| `-t` | 60 | Dauer in s |
| `-d` | `sync_<host>_<zeit>` | Ausgabeordner |
| `-u` | | Ohne Regelung, misst nur die Phase |
| `-s` | | Künstlicher Takt aus der eigenen Uhr, Test ohne Kabel |
| `-l` / `-c` | 17 / `/dev/gpiochip0` | Eingangspin / GPIO-Chip |

## Wichtig
- **Immer mit `sudo`** starten (Echtzeit-Priorität). Ohne sie hat ein vblank-Schreibzugriff auf dem Zero einmal 9 ms gedauert.
- **Der Bildbeginn darf nicht auf der Flanke liegen.** Auf dem Zero (1 Kern) verzögern sich dann der GPIO- und der Kamera-Interrupt gegenseitig um ca. 23 µs. Deshalb der Standard-Versatz von 0,35 Bild.
- Nur bei 640x400 und 100 fps getestet. Mit Sensor-Crop (678+ fps) noch offen, siehe das Dokument oben.
