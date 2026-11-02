# Kamera-Grundlagen OV9281 (Stand 2026-11-02)

Antworten auf die Fragen, die beim Einrichten aufkamen, mit den **gemessenen** Werten der Zero-Kamera. Details und Messmethode stehen in [test-results-2026-11-02.md](testing%20documents/test-results-2026-11-02.md).

## Datenblatt (Shop: bastelgarage.ch, DFRobot SEN0634)
| | |
|---|---|
| Sensor | OV9281, monochrom, **Global Shutter** |
| Auflösung | 1280 × 800 (1 MP) |
| Pixelgröße | 3 µm × 3 µm |
| Sensorgröße | 1/4", also 3,84 mm × 2,40 mm |
| Brennweite / Blende | 2,85 mm / f/2.0, **fester Fokus** |
| FOV laut Shop | 79,3°, gemessen sind es **75,6° diagonal** (siehe unten) |
| Schnittstelle | MIPI CSI-2, 2 Lanes |

## Sind die Pixel quadratisch?
Bei fast allen modernen Sensoren ja, bei der OV9281 laut Datenblatt auch (3 × 3 µm).
- **Gemessen:** fx / fy = **1,0007**, also quadratisch. Der Unterschied liegt innerhalb der Messgenauigkeit.
- Ausnahmen gibt es bei anderen Kameras: alte Video-CCDs (PAL/NTSC, DV), Spezialsensoren und asymmetrisches Binning.
- In der Kameramatrix K stehen deshalb trotzdem fx und fy getrennt, und es gibt einen Skew-Wert. Der Skew ist bei modernen Sensoren 0.

## Brennweite horizontal / vertikal
Physikalisch gibt es **nur eine** Brennweite, f = 2,85 mm (gemessen: 2,855 mm). „Horizontal" und „vertikal" unterscheidet man nur **in Pixeln**:
```
fx = f / Pixelbreite,  fy = f / Pixelhöhe
Datenblatt: 2,85 mm / 0,003 mm = 950,000 px (beide)
gemessen:   fx = 951,831 px, fy = 951,130 px
```
Die **Pixelanzahl** (1280 × 800) spielt für die Brennweite keine Rolle. Sie bestimmt nur den **Bildwinkel**.

## Bildwinkel
Ohne Verzeichnung gilt FOV = 2 · atan(halbe Sensorgröße in px / f in px).

| | Datenblatt-Werte (f = 950 px) | **gemessen (mit Verzeichnung)** |
|---|---|---|
| horizontal | 67,935° | **66,650°** |
| vertikal | 45,667° | **44,834°** |
| diagonal | 76,930° | **75,555°** |

- **Die 79,3° aus dem Shop stimmen nicht.** Rechnerisch würden sie f = 2,732 mm (910,679 px) bedeuten, gemessen sind aber 2,855 mm.
- Eine frühere Vermutung war, dass Tonnenverzeichnung den Bildwinkel auf 79° vergrößert. **Das ist widerlegt:** Am Rand wirkt die Verzeichnung in die andere Richtung, der Bildwinkel wird etwas **kleiner**.
- **Für das Projekt:** Der Laser schwenkt bis zu 60°. Die Kamera sieht horizontal 66,7°, vertikal aber nur 44,8°. Die Schwenkrichtung des Lasers gehört also auf die **lange Bildseite**.

## Wie groß ist ein Pixel in der Entfernung Z?
Auf einer Ebene **senkrecht zur optischen Achse** sind im Lochkameramodell **alle Pixel gleich groß**, auch die am Rand. Ihre Größe wächst linear mit Z:
```
Pixelgröße(Z) = Z / f_px  ≈ Z / 951,5
```

| Abstand Z | Pixelgröße | Sichtfeld (B × H) |
|---|---|---|
| 0,1 m | 0,105 mm | 0,135 m × 0,084 m |
| 0,5 m | 0,526 mm | 0,673 m × 0,420 m |
| 1 m | 1,051 mm | 1,345 m × 0,841 m |
| 2 m | 2,102 mm | 2,691 m × 1,682 m |
| 5 m | 5,255 mm | 6,726 m × 4,204 m |
| 10 m | 10,510 mm | 13,453 m × 8,408 m |

- Das gilt erst **nach dem Entzerren**. Im Rohbild sind die Pixel am Rand wegen der Verzeichnung anders groß.
- Für eine **schräge Ebene** gilt es nicht, dort braucht man eine Homographie.
- Winkel pro Pixel: 1 px ≈ 1/951,5 rad ≈ **0,06°**. Bei 3 m sind das ca. 3,2 mm.

## Verzeichnung
Gemessen wurde so viel Versatz zwischen verzerrter und entzerrter Position:
- **Bildecken:** 18,4 px
- **Durchschnitt:** 7,6 px
- **Anteil der Pixel über 1 px Versatz:** 90 %

Außerhalb der Bildmitte ist Entzerren also Pflicht. Eine frühere Schätzung aus den Datenblattwerten (32 px in den Ecken) war zu hoch.

**Der Raspberry Pi rechnet die Verzeichnung nicht heraus.** libcamera korrigiert nur Belichtung und Vignettierung, nicht die Geometrie. Das muss man selbst machen, mit K und `dist` aus `calib/<kamera>/calibration.json`:
```python
import cv2, json, numpy as np
c = json.load(open("calib/zero-2026-11-02/calibration.json"))
K, dist = np.array(c["K"]), np.array(c["dist"])

# a) nur Punkte entzerren (schnell, keine Interpolation), z. B. erkannte Objekte:
pts_u = cv2.undistortPoints(pts.reshape(-1, 1, 2).astype(np.float64), K, dist, P=K)

# b) ganzes Bild entzerren (Maps einmal berechnen, dann pro Bild remap):
newK, roi = cv2.getOptimalNewCameraMatrix(K, dist, (1280, 800), alpha=0)
m1, m2 = cv2.initUndistortRectifyMap(K, dist, None, newK, (1280, 800), cv2.CV_16SC2)
img_u = cv2.remap(img, m1, m2, cv2.INTER_LINEAR)   # danach gilt newK, nicht K
```
- Mit `alpha=0` wird so zugeschnitten, dass keine schwarzen Ränder entstehen; dabei geht etwas Bildwinkel verloren. Mit `alpha=1` bleibt alles erhalten, dafür gibt es schwarze Ecken.
- Die Verzeichnung ist **kein Schärfeverlust**, sondern nur ein Lagefehler. Nach der Kalibrierung lässt er sich bis auf ca. 0,15 px herausrechnen.
- **Koordinaten:** Die Kalibrierung gilt für **1280x800 in Ausgabe-Pixeln**, also für das Bild so, wie V4L2 es liefert, mit Mirror und Flip des Treibers und ohne weitere Drehung. Das sind dieselben Koordinaten, die `tools/crop/roi.py` benutzt.
- **Mit Sensor-Crop (ROI)** ab (x0, y0): fx, fy und `dist` bleiben gleich, nur die Bildmitte verschiebt sich auf cx − x0, cy − y0. Das gilt, weil der Crop pixelgenau ist ([crop-evaluation.md](testing%20documents/crop-evaluation.md)). Zum Entzerren eines ROI-Punkts also erst x0/y0 addieren und dann mit dem vollen K rechnen.
- **640x400** (2× Skipping): K mit etwa 0,5 skalieren. Der genaue Halbpixel-Versatz ist nicht geprüft.

## Fokus und Schärfentiefe
- Fester Fokus. Die hyperfokale Distanz bei f = 2,85 mm, f/2 und 3 µm Unschärfe beträgt **≈ 1,36 m**. Auf diese Entfernung fokussiert ist alles von **≈ 0,7 m bis unendlich** auf etwa 1 Pixel scharf.
- **Näher als ca. 0,7 m wird es unscharf.** Bei der Kalibrierung war das Brett aus der Nähe nicht mehr erkennbar.
- Gemessene Kantenschärfe: 2,3 px (10–90 %), in beiden Richtungen gleich. Die Linse sitzt also gerade.
- **Nach der Kalibrierung nicht mehr am Objektiv drehen.** Sonst stimmen fx, fy und die Verzeichnung nicht mehr.

## Belichtung und Bewegungsunschärfe
- Im Innenraum regelt die Automatik auf **≥ 10 ms**. Ein Objekt mit 5 m/s bewegt sich in 10 ms um **5 cm**.
- Für das Tracking ist eine Belichtung von **≤ 1 ms** nötig, also etwa **10× mehr Licht** oder eine starke Beleuchtung. Am 3B gemessen: Bei 100–200 µs braucht es kräftige Beleuchtung oder hohe Verstärkung.
- Licht sauber einstellen:
  - Raum dunkel und nur ein heller Bildschirm im Bild → **Übersteuerung**: Weiß ist abgeschnitten und strahlt in die dunklen Bereiche, Kanten werden 1–2 px breiter.
  - Lampen spiegeln sich in glänzenden Flächen.
  - Bestes Ergebnis: Raumlicht an, keine Spiegelung, nichts übersteuert.
- Der Schärfewert auf der Livebild-Seite hängt vom Kontrast ab (mit dem Quadrat). Er ist nur bei **gleicher Szene und gleichem Licht** vergleichbar.

## Muss jede Kamera einzeln kalibriert werden?
**Ja.** Gleiches Modell heißt nicht gleiche Werte:

| | Unterschied zwischen Exemplaren | Fehler, wenn man Werte einer anderen Kamera nimmt |
|---|---|---|
| Bildmitte cx/cy | groß: beim Zero 12 bzw. 29 px neben der Mitte | 30 px ≈ **1,8°**, bei 3 m ca. 9 cm |
| Brennweite | 1–3 % (hängt vom Einschrauben und Fokus ab) | 2 % ≈ 12 px am Rand ≈ 0,7° |
| Verzeichnung | eher klein (gleiche Linse) | taugt als Startwert |

Für die Stereo-Kalibrierung (beide Kameras zueinander) zuerst jede Kamera einzeln kalibrieren, dann gemeinsame Aufnahmen machen. Dafür muss auch die **Feldgröße des Bretts** gemessen werden. Anleitung: [tools/calib/README.md](tools/calib/README.md).

## Genauigkeit der Zero-Kalibrierung
- RMS-Reprojektionsfehler 0,148 px.
- Unsicherheit (Bootstrap): fx ≈ ±3–4 px (0,3–0,4 %), Bildmitte ≈ ±1,5–2 px, Verzeichnung in den Ecken ≈ ±1,5 px. Das sind **unter 0,1°**.
- Mehr Bilder würden daran nur wenig ändern. Am ehesten helfen noch Bilder mit dem Brett ganz in den **unteren Ecken**.
