# Hardware und Zugang (Stand 2026-11-02)

## Geräte im WLAN (192.168.1.0/24)
| | Pi Zero W | Pi 3B |
|---|---|---|
| IP | **192.168.1.48** | **192.168.1.94** |
| Hostname | `pizero` | – |
| MAC | b8:27:eb:43:13:ce | b8:27:eb:7a:1b:5e |
| Modell | Raspberry Pi Zero W Rev 1.1: ARMv6, **1 Kern**, 426 MB RAM | Raspberry Pi 3 Model B Rev 1.2, 64-bit |
| OS | Raspbian 13, Kernel 6.18.50+rpt-rpi-v6 | Debian 13, Kernel 6.18.50 |
| libcamera / rpicam-apps | 0.7.2 / 1.13.0 | 0.7.2 / 1.14.0 |
| Benutzer | `tom` | `tom` |
| Kamera | OV9281, Bild steht auf dem Kopf (Kamera um 180° gedreht montiert) | OV9281 |
| Ergebnisse | [test-results-2026-11-02.md](test-reports/test-results-2026-11-02.md) | [test-results-2026-10-29.md](test-reports/test-results-2026-10-29.md) |

- **Die IPs kommen per DHCP und können sich ändern.** Am besten im Router fest reservieren.
- **Pi finden:** In der Geräteliste des Routers oder mit `arp -a` am PC. Raspberry Pis dieser Generation haben MAC-Adressen, die mit `b8-27-eb` beginnen.
- **Passwort:** nicht im Repo, im Team nachfragen. `sudo` verlangt ebenfalls das Passwort.

## Verbinden
```
ssh tom@192.168.1.48        # Zero
ssh tom@192.168.1.94        # 3B
```
**SSH-Schlüssel hinterlegen**, einmalig pro Pi (danach kein Passwort mehr nötig). Für die Windows-Eingabeaufforderung:
```
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh tom@<ip> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```
Stand 2026-11-03 ist auf beiden Pis ein Schlüssel vom Mac hinterlegt (SSH-Aliase `pi3` und `pizero`).

## Kamera-Konfiguration

CAM: https://www.bastelgarage.ch/1mp-ov9281-global-shutter-camera-79-fov-for-raspberry-pi-4b-5?search=OV9281

Die OV9281 wird **nicht automatisch erkannt**: `camera_auto_detect=1` gilt nur für offizielle Raspberry-Pi-Kameras. Auf beiden Pis steht deshalb in `/boot/firmware/config.txt`:
```
camera_auto_detect=0
dtparam=i2c_vc_baudrate=400000
dtoverlay=ov9281
```
Danach ist ein Neustart nötig. Prüfen mit `rpicam-hello --list-cameras`. Erwartet wird: `ov9281 [1280x800 10-bit MONO] (/base/soc/i2c0mux/i2c@1/ov9281@60)`.
Auf beiden Pis liegt eine Sicherung der vorherigen Datei als `config.txt.bak-2026-11-02`. Auf dem Zero ist es der Stand vor den Kamera-Einträgen, auf dem 3B der Stand vor der Umstellung auf I2C mit 400 kHz.
**I2C mit 400 kHz ist nötig**, damit das ROI ohne Drops verschoben werden kann (siehe [crop-evaluation.md](test-reports/crop-evaluation.md)).

**Pi 3B, DAC-Test (2026-11-16):** Zusätzlich `dtparam=i2c_arm_baudrate=400000` direkt unter `dtparam=i2c_arm=on` (Header-I2C, GPIO2/3, `/dev/i2c-1`), Sicherung als `config.txt.bak-2026-11-16`. Der GP8403-DAC antwortet auf Adresse 0x5F, Test: [tools/dac/dac_test.py](../tools/dac/dac_test.py), Latenz-Marker auf GPIO 27 (Pin 13).

Modi (beide Pis gleich):
| Format | 640x400 | 1280x720 | 1280x800 |
|---|---|---|---|
| R8 | 309,79 fps | 171,79 fps | 143,66 fps |
| R10 | 247,83 fps | 137,42 fps | 114,93 fps |

Die libcamera-Angaben für R8 sind ca. 4 % zu hoch, siehe die Messungen in [test-results-2026-10-29.md](test-reports/test-results-2026-10-29.md).
- 640x400 tastet das volle Sensorbild 2× ab (laut crop-evaluation Skipping, y_inc 2).
- Höhere Bildraten bekommt man per **Sensor-Crop (ROI)** über I2C, bis über 1000 fps (siehe [crop-evaluation.md](test-reports/crop-evaluation.md)).
- Der Treiber streamt mit **Mirror und Flip** (Register 0x3820/0x3821). Bildkoordinaten (Ausgabe-Pixel) und Sensor-Array-Koordinaten sind also gespiegelt; `tools/crop/roi.py` rechnet das um.

## Frame-Sync-Verkabelung
Der Pi 3 gibt auf GPIO18 einen 10-Hz-PWM-Takt aus. Beide Pis lesen ihn auf GPIO17 ein und regeln ihre Kamera darauf (siehe [tools/sync/README.md](../tools/sync/README.md)).
| Von | Nach |
|---|---|
| Pi 3 Pin 12 (GPIO18, PWM) | Pi 3 Pin 11 (GPIO17), Brücke |
| Pi 3 Pin 12 (GPIO18) | Pi Zero Pin 11 (GPIO17), optional über 1 kΩ |
| Pi 3 Pin 14 (GND) | Pi Zero Pin 14 (GND) |

- Frei gehalten für später: GPIO14/15 (UART Zero → Pi 3) und GPIO7-11 (SPI0 für den DAC).
- GPIO17 ist auf dem Zero auch SPI1 CE1. Wird SPI1 einmal gebraucht, den Eingang mit `camsync -l <pin>` verlegen.

## Galvo-Spiegel
- **Bestellt:** ZJ15K Galvo-Scanner, [AliExpress 1005010190669822](https://de.aliexpress.com/item/1005010190669822.html)

| | Laut Händler |
|---|---|
| Modell | ZJ15K. Titel: „15 kHz SLA 3D 400–700 nm 450 nm Laser-Galvo-Scanner 15 kpps Scannen Galvanometer Galvo-Spiegel DIY Animation Bühnenlicht“ |
| Geschwindigkeit | bis 15 kpps |
| Wellenlänge | 400–700 nm (sichtbarer Bereich), im Text zusätzlich 450 nm genannt. Prüfen, ob unser Laser in diesem Bereich liegt. |
| Versorgung | 12 V DC |
| Steuerung | „DMX-kompatibel“, eher Werbetext. Galvo-Treiber nehmen normalerweise ein analoges X/Y-Signal. |
| Paket | 13 × 8 × 9 cm, 0,400 kg |
| Zertifizierung | CE |

- **Noch unbekannt:** Erst am Gerät bzw. am Treiber ablesen oder messen.
  - Scanwinkel
  - Eingangssignal: Spannungsbereich (oft ±5 V oder ±10 V), differentiell oder single-ended
  - Treiberplatine dabei? Wie sieht die 12-V-Versorgung genau aus (Händler schreibt „integriertes Netzteil“)?
  - Einschwingzeit / Step-Response
  - Spiegelgröße / Apertur
  - Max. Laserleistung
  - Anschlussbelegung
- Davon hängen DAC und Verstärker ab: Spannungsbereich, differentiell oder nicht. Die Einschwingzeit geht in die Vorhaltezeit des Prädiktors ein (siehe [system-architecture.md](system-architecture.md)).

## Wichtig
- ⚠️ **Das Kamerakabel nie unter Strom ab- oder anstecken.** Danach liefert der Sensor nichts mehr (`stream on failed in subdev`, `Device timeout`). Nur ein Neustart hilft, und das Abstecken kann die Hardware beschädigen.
- **Zero W:**
  - **Nur 2,4-GHz-WLAN.**
  - **Kleiner 22-poliger Kameraanschluss**, braucht ein Adapterkabel von 22 auf 15 Pins.
  - Nur 1 langsamer Kern. Das Livebild in 1280x800 lastet ihn zu ca. 100 % aus.
  - Als Kamera-Knoten B (Test 8, [Ergebnisse](test-reports/test-results-2026-11-02-test8.md)): Die Aufnahme schafft dieselben Bildraten wie der 3B, ohne Drops. Mit einem ROI bis 320 px Breite kommt er auch bei 678–1721 fps mit. Bei voller Breite und bei 640x400 mit Detektion (max. ~150 fps) ist die CPU zu langsam.
  - ⚠️ Eine SCHED_FIFO-Schleife, die nicht hinterherkommt, legt den Zero komplett lahm, auch SSH. Timeouts deshalb mit höherer Priorität starten, siehe `tools/bench/test8.sh`.
- **Pi 3B:** Es wird noch **Unterspannung** geloggt, das Netzteil muss geprüft werden (crop-evaluation, Next steps).
- **Der Treiber schaltet den Sensor aus, wenn nicht gestreamt wird.** Register sind erst nach STREAMON erreichbar, und jedes STREAMON schreibt den Modus neu. Ein ROI muss deshalb nach jedem Start neu gesetzt werden.
- **Livebild / Fokus / Kalibrierung:** `tools/calib/live.py` auf dem Pi starten und `http://<ip>:8000` öffnen. Anleitung: [tools/calib/README.md](../tools/calib/README.md). Auf dem Zero liegt es auch unter `~/t/live.py`.
- **PowerShell und SSH:** Mehrzeilige Befehle aus PowerShell kommen mit BOM und CRLF beim Pi an, und bash versteht sie dann nicht. Besser Git Bash oder die Windows-Eingabeaufforderung verwenden.
