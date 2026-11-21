# Kamera kalibrieren (OV9281)

Jede Kamera muss **einzeln** kalibriert werden. Gleiches Modell heißt nicht gleiche Werte. Die Bildmitte allein lag beim Zero schon 29 px daneben, das sind ca. 1,8° Richtungsfehler. Ergebnisse und Erfahrungen vom Zero: [test-results-2026-11-02.md](../../docs/test-reports/test-results-2026-11-02.md), Grundlagen: [Kamera-Grundlagen.md](../../docs/kamera-grundlagen.md).

## Vorher prüfen
- **Kamera wird erkannt:** `rpicam-hello --list-cameras` auf dem Pi zeigt `ov9281`. Falls nicht, braucht `/boot/firmware/config.txt` diese Zeilen (danach Neustart):
  ```
  camera_auto_detect=0
  dtparam=i2c_vc_baudrate=400000
  dtoverlay=ov9281
  ```
- **SSH-Zugang** zum Pi, am besten mit Schlüssel (sonst fragt das Skript mehrmals nach dem Passwort):
  ```
  type %USERPROFILE%\.ssh\id_ed25519.pub | ssh tom@<ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
  ```
- **Python-Pakete** auf dem PC: `python -m pip install -r tools/calib/requirements.txt`
- **Nicht mehr am Objektiv drehen.** Fokus vorher einstellen (Livebild, Schärfewert). Jede Drehung danach macht die Kalibrierung ungültig.

## Ablauf
In Git Bash im Ordner `LLTS`:
```
tools/calib/calibrate_pi.sh <pi-ip> <name>        # z. B. tools/calib/calibrate_pi.sh 192.168.1.94 pi3b-2026-11-03
```
1. Das Skript startet das Livebild auf dem Pi und die automatische Aufnahme.
2. **Tablet:** `http://<pi-ip>:8000/board` öffnen und antippen (Vollbild). Helligkeit ca. 50 %, Auto-Sperre aus.
3. **Handy/Laptop:** `http://<pi-ip>:8000` zeigt das Livebild mit Statuszeile.
4. Brett bewegen (siehe unten), bis die Seite **FERTIG** meldet. Dann im Terminal **Strg+C**.
5. Das Skript berechnet die Kalibrierung und den Stabilitätstest. Ergebnis: `calib/<name>/calibration.json`.

Unterbrochen? Einfach denselben Befehl noch einmal starten. Die vorhandenen Bilder werden weiterverwendet.

## Was die Person mit dem Tablet tun soll
- **Pro Position ca. 1 s stillhalten**, bis das Livebild **grün blinkt**. Verwackelte Bilder werden nicht gespeichert.
- **Das Brett muss immer ganz im Bild sein.**
- **Nicht näher als ca. 70 cm** an die Kamera. Näher ist das Bild unscharf (fester Fokus), dann wird das Brett nicht erkannt.
- Das **3×3-Raster** auf der Seite zeigt, was noch fehlt. Ziel: jedes Feld mindestens 3.
  - Die **äußeren Felder** zählen nur, wenn das Brett **wirklich bis an den Bildrand** reicht. **Ecken sind am wichtigsten**, vor allem die unteren. Beim Zero fehlten genau die.
  - **Mitte = „nah":** Das Brett ist groß im Bild, aber noch scharf.
- Dabei **kippen** (20–40° in alle Richtungen) und ab und zu **drehen**. Es darf auch die Kamera bewegt werden statt des Tablets, nur nicht während einer Aufnahme.
- Richtungen gelten **wie auf der Webseite**. Ist die Kamera auf dem Kopf montiert, ist links und rechts bzw. oben und unten vertauscht.

## Typische Probleme
| Meldung / Symptom | Ursache | Lösung |
|---|---|---|
| „Brett nicht erkannt" | Tablet zeigt nicht `/board`, Rand abgeschnitten oder zu nah (unscharf) | `/board` öffnen, ganz ins Bild, ≥ 70 cm |
| „Zu hell" bzw. Weiß ausgefressen | Raum dunkel, die Belichtung regelt auf den Raum | Tablet dunkler stellen oder Raumlicht an |
| Heller Streifen auf dem Brett | Lampe spiegelt sich im Tablet | Tablet etwas kippen oder drehen |
| Bleibt bei „stillhalten …" | Belichtung lang, Hand zittert | Tablet anlehnen oder mehr Licht |
| Livebild friert ein, `stream on failed` | **Kamerakabel im Betrieb gezogen** | Pi neu starten. Kabel nie unter Strom ab- oder anstecken |

## Gutes Ergebnis erkennen
- RMS-Reprojektionsfehler **< 0,3 px** (Zero: 0,148).
- Stabilität (Bootstrap): fx **< ±5 px**, Verzeichnung in den Ecken **< ±2 px** (Zero: ca. ±3–4 / ±1,5; die Schätzung selbst schwankt um ca. 20 % zwischen Läufen).
- Messpunkte reichen bis **> 90 %** des Eckradius. Sind es weniger, sind die Ecken nur hochgerechnet.
- Zum Vergleich der Zero: fx 951,8, cx/cy 626,9/428,3, diagonal 75,6°. Eine zweite Kamera sollte bei fx ähnlich liegen (± wenige %). cx/cy dürfen deutlich abweichen.

## Dateien
| Datei | Läuft auf | Zweck |
|---|---|---|
| `live.py` | Pi | Livebild, Schärfewert, Schachbrett-Seite `/board`, Status `/status` |
| `calibrate_pi.sh` | PC (Git Bash) | ganzer Ablauf in einem Befehl |
| `calib_capture.py` | PC | automatische Aufnahme (stillstehend und neue Position) |
| `calib_solve.py` | PC | Kalibrierung, Ausreißer, Bildwinkel, Verzeichnung |
| `stability.py` | PC | Bootstrap-Stabilität und Abdeckung |
| `quality.py` | PC | Kantenschärfe, Kontrast, Rauschen (`ROI=y0,y1,x0,x1`) |
