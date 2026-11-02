# LLTS

Objekte in der Luft mit 2 Kameras tracken und mit einem Laser anleuchten (siehe [Zusammenfassung.md](Zusammenfassung.md)).

| Datei / Ordner | Inhalt |
|---|---|
| [Hardware-Setup.md](Hardware-Setup.md) | Pis, IPs, Zugang, Kamera-Konfiguration, Stolperfallen |
| [Kamera-Grundlagen.md](Kamera-Grundlagen.md) | OV9281: Pixel, Brennweite, Bildwinkel, Pixelgröße in der Entfernung, Verzeichnung, Fokus, Belichtung |
| [test-results-2026-10-29.md](test-results-2026-10-29.md) | Pi 3B: Bildraten, vblank, Belichtung, Crop (Timing-Tests) |
| [test-results-2026-11-02.md](test-results-2026-11-02.md) | Pi Zero W: Einrichtung, Bildqualität, Kalibrierung |
| [tools/](tools/) | Livebild, Kalibrier-Skripte, Anleitung ([tools/README.md](tools/README.md)) |
| [calib/](calib/) | Kalibrierbilder und Ergebnisse pro Kamera (`calibration.json`) |

## Stand 2026-11-02
- Zero-Kamera eingerichtet und kalibriert: fx 951,8 px, Bildwinkel 66,7° × 44,8° (diagonal 75,6°).
- **Offen:**
  - Kalibrierung der Pi-3B-Kamera (vorbereitet: `tools/calibrate_pi.sh`)
  - Leistungstest auf dem Zero (Test 8)
  - Stereo-Kalibrierung
  - PWM und Phasen-Lock (Tests 9–10)
  - Galvo/DAC (Test 11)
  - Beleuchtung für ≤ 1 ms Belichtung
