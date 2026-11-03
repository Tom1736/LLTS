# LLTS

Objekte in der Luft mit 2 Kameras tracken und mit einem Laser anleuchten (siehe [Zusammenfassung.md](Zusammenfassung.md)).

| Datei / Ordner | Inhalt |
|---|---|
| [Hardware-Setup.md](Hardware-Setup.md) | Pis, IPs, Zugang, Kamera-Konfiguration, Stolperfallen |
| [Kamera-Grundlagen.md](Kamera-Grundlagen.md) | OV9281: Pixel, Brennweite, Bildwinkel, Pixelgröße in der Entfernung, Verzeichnung, Koordinaten und ROI, Fokus, Belichtung |
| [System Architecture/](System%20Architecture/system-architecture.md) | Blockdiagramm: Kamera-Knoten, Sync, ROI-Rückkopplung, Triangulation, Prädiktor, DAC/Galvo, Watchdog |
| [testing documents/test-results-2026-10-29.md](testing%20documents/test-results-2026-10-29.md) | Pi 3B: Bildraten, vblank, Belichtung, Timing |
| [testing documents/crop-evaluation.md](testing%20documents/crop-evaluation.md) | Pi 3B: Sensor-Crop (ROI) über I2C, bis über 1000 fps, Latenzkette |
| [testing documents/test-results-2026-11-02.md](testing%20documents/test-results-2026-11-02.md) | Pi Zero W: Einrichtung, Bildqualität, intrinsische Kalibrierung |
| [testing documents/frame-sync-2026-11-03.md](testing%20documents/frame-sync-2026-11-03.md) | Frame-Sync beider Kameras: PWM-Takt, vblank-Phasen-Lock, Bildschirm-Blitztest |
| [tools/calib/](tools/calib/README.md) | Livebild, Fokus, Kalibrierung (`calibrate_pi.sh`), Anleitung |
| [tools/crop/](tools/crop/) | ROI setzen und prüfen (`roi.py`, `verify_roi.py`, `roi_test.c`) |
| [tools/track/](tools/track/) | Tracking (`track.c`, `view.py`) |
| [tools/sync/](tools/sync/README.md) | Frame-Sync (`camsync.c`, `pulse.sh`), Blitztest (`flash.html`, `run_flash_test.sh`), Anleitung und Verkabelung |
| [calib/](calib/) | Kalibrierbilder und Ergebnisse pro Kamera (`calibration.json`) |

## Stand 2026-11-02
- **Pi 3B:**
  - Bildraten und Timing gemessen.
  - Sensor-Crop funktioniert pixelgenau: 678 fps bei 128 Zeilen, über 1000 fps bei 64 Zeilen.
- **Frame-Sync (2026-11-03):** beide Kameras per vblank-Phasen-Lock auf einen 10-Hz-PWM-Takt vom Pi 3 synchronisiert, bei 640x400 / 100 fps auf ±8 µs (eine Sensorzeile). Bildschirm-Blitztest: 60/61 Blitze im selben Bild, optisch auf ±40 µs bestätigt.
- **Pi Zero W:** Kamera eingerichtet und kalibriert. fx 951,8 px, Bildwinkel 66,7° × 44,8° (diagonal 75,6°), Reprojektionsfehler 0,148 px.
- **Offen:**
  - Kalibrierung der Pi-3B-Kamera (vorbereitet: `tools/calib/calibrate_pi.sh`)
  - Leistungstest auf dem Zero (Test 8): Aufnahme, ROI-Kopie und Schwerpunkt im Takt
  - Stereo-Kalibrierung, dafür die Feldgröße des Bretts messen
  - Frame-Sync mit Sensor-Crop (678+ fps) testen, mit LED statt Bildschirm genauer nachmessen
  - Galvo, DAC und Verstärker auswählen (Test 11)
  - Beleuchtung für ≤ 1 ms Belichtung
  - Netzteil des Pi 3B (Unterspannung)
