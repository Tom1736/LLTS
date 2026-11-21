# Galvo analog stage: setup, 2026-11-18
This stage sits between the DAC and the galvo drivers ("Amplifier / level shift" in [system-architecture.md](system-architecture.md)). It turns the DAC's 0–10 V into ±5 V for the galvo inputs:

**V_out = V_DAC − V_ref**, with V_ref = 5 V.

| DAC | Output |
|---|---|
| 0 V | −5 V |
| 5 V | 0 V (galvo center) |
| 10 V | +5 V |

## Parts
| Part | Use |
|---|---|
| LM324N (quad op-amp, DIP-14) | A = reference buffer, B = X channel, C = Y channel, D = unused |
| ±12 V power supply (terminals +12 V, COM, −12 V) | Op-amp supply |
| MB102 breadboard power module | Clean 5 V reference (AMS1117-5.0) |
| USB-C PD trigger board, set to 9 V | Powers the MB102 through its barrel jack |
| Gravity I2C 2-channel 0–10 V DAC | X and Y signals, driven by the Pi |
| 8 × 10 kΩ (0.1 % if possible) | Ra, Rb, Rc, Rf for B and C |
| 2 × 10 kΩ or 4.7 kΩ | Rp, output pull-down to −12 V |
| 1 × 1 kΩ, 1 × 10 µF | Reference filter |
| 2 × 100 nF | Supply decoupling at pins 4 and 11 |

## Why it is built this way
- **The Pi's 5 V can't be the reference.** It's a supply rail, not a reference: ±5 % tolerance, load ripple from camera and CPU, and the Pi 3B logs undervoltage. A difference amp passes any error on V_ref 1:1 to the galvo.
- **A divider from the 12 V supply isn't good enough either.** The galvo drivers load that rail, so it sags whenever the mirrors move, and the divider passes the sag on.
- **PD trigger at 9 V → MB102 → AMS1117** gives a regulated 5 V that is separate from the galvo load. Don't feed the MB102 through its USB-A port: on these boards USB 5 V bypasses the regulator.
- **Channel A buffers the reference**, so the current drawn by B and C doesn't shift it. The 1 kΩ / 10 µF filter (≈16 Hz) removes remaining noise.
- **Rp keeps the LM324 out of crossover distortion.** The LM324's output stage has a small dead zone where it changes from sourcing to sinking current. Without Rp that change happens near 0 V, the galvo's center. Rp pulls a constant current to −12 V, so the output keeps sourcing across the range. With 10 kΩ the change point moves to about −4 V (assuming a ~10 kΩ galvo input); 4.7 kΩ moves it out of the ±5 V range entirely.

## Schematic
All of Ra, Rb, Rc, Rf, Rp = 10 kΩ. Pin numbers are LM324 pins.

```
Reference (channel A)

 MB102 5 V ──[1k]──┬──── 3 (+)
                   │           ▷ A ── 1 ──┬──► V_ref
                  ═══ 10 µF ┌── 2 (−)     │
                   │        └─────────────┘
                  GND

X channel (B)

                    ┌──────[Rf]──────┐
                    │                │
 V_ref ───[Rc]──────┴── 6 (−)        │
                          ▷ B ── 7 ──┴──┬──► X out (±5 V) → galvo X
 DAC X ───[Ra]──────┬── 5 (+)           │
                    │                  [Rp]
                   [Rb]                 │
                    │                 −12 V
                   GND

Y channel (C): same as B, with pins 9 (−), 10 (+), 8 (out) and DAC Y.
```

## LM324 pinout
DIP-14, notch at the top, pin 1 top left, counting counterclockwise.

| Pin | Function | Pin | Function |
|---|---|---|---|
| 1 | Output A (V_ref) | 14 | Output D |
| 2 | − input A | 13 | − input D |
| 3 | + input A | 12 | + input D |
| 4 | **+12 V** | 11 | **−12 V** (labelled GND in the datasheet) |
| 5 | + input B | 10 | + input C |
| 6 | − input B | 9 | − input C |
| 7 | Output B (**X**) | 8 | Output C (**Y**) |

Pin 11 is called GND in the datasheet only because the chip is meant for single-supply use. Here it goes to −12 V.

## Wiring
### 1. Power and ground
⚠️ **GND is the supply's COM terminal, not −12 V.** Find it with a multimeter before wiring: COM reads +12 V against one outer terminal and −12 V against the other.

- Supply COM → GND rail
- Supply +12 V → pin 4
- Supply −12 V → pin 11
- 100 nF from pin 4 to GND, 100 nF from pin 11 to GND, close to the chip
- MB102 GND → GND rail
- DAC GND → GND rail (this also ties in the Pi's GND)
- Galvo driver signal GND → GND rail

All grounds meet at one point.

### 2. Reference (channel A)
- MB102 5 V → 1 kΩ → pin 3
- Pin 3 → 10 µF → GND (electrolytic: − leg to GND)
- Pin 1 → pin 2
- Pin 1 is V_ref.

### 3. X channel (B)
- Pin 1 (V_ref) → Rc → pin 6
- Pin 6 → Rf → pin 7
- DAC X → Ra → pin 5
- Pin 5 → Rb → GND
- Pin 7 → Rp → −12 V
- Pin 7 → galvo X input

### 4. Y channel (C)
- Pin 1 (V_ref) → Rc → pin 9
- Pin 9 → Rf → pin 8
- DAC Y → Ra → pin 10
- Pin 10 → Rb → GND
- Pin 8 → Rp → −12 V
- Pin 8 → galvo Y input

### 5. Unused channel D
- Pin 12 → GND
- Pin 13 → pin 14

### 6. Galvo input
- Single-ended input (signal + GND): pin 7 / pin 8 → signal, GND rail → driver signal GND.
- Differential input (X+ / X−): pin 7 → X+, GND → X−, same for Y.

## DAC range
**Set the Gravity DAC to its 0–10 V range in software.** In the 0–5 V range the circuit can only output −5 … 0 V.

## Testing (galvo not connected)
1. Power on without the LM324. Measure against GND: pin 4 = +12 V, pin 11 = −12 V, pin 3 ≈ 5 V. If "+12 V" reads 24 V and "−12 V" reads 0 V, GND is on the wrong terminal (see step 1 of the wiring).
2. Power off, insert the LM324, power on. Pin 1 should match pin 3 to within a few mV. Write the value down as V_ref for calibration.
3. Set the DAC to 0 V, 5 V, 10 V. Pins 7 and 8 should read ≈ −5 V, 0 V, +5 V.
4. Play a 0–10 V sine on the DAC. Pins 7 and 8 should show a sine from −5 V to +5 V.
5. Only then connect the galvo. Start with small DAC changes around 5 V, laser off.

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| Both outputs sit at a constant ≈ 0.6 V; − input constant ≈ 2.8 V; sine visible on + input | Op-amp has no negative supply (pin 11 is at GND), and the output can't go below GND. The LM324 output can't get closer than ≈ 0.6 V to V− while it sinks current. | Connect GND to the supply's COM and pin 11 to −12 V. |
| "+12 V" reads 24 V, "−12 V" reads 0 V | The supply's −12 V terminal is used as GND | Same as above. Don't connect the galvo drivers until fixed: their reference would be 12 V away from the circuit's GND. |
| Output only swings −5 … 0 V | DAC in 0–5 V range | Switch the DAC to 0–10 V. |
| Output clips at the top | LM324 swings only to ≈ V+ − 1.5 V | Fine for ±5 V. For ±10 V, see the open points. |
| Small glitches when the output passes 0 V | Crossover distortion, Rp missing | Fit Rp (10 kΩ or 4.7 kΩ to −12 V). |

## Open points
- **Galvo input range and impedance are not confirmed.** If the drivers expect ±10 V, change Rb and Rf to 20 kΩ (gain 2: V_out = 2 · (V_DAC − 5 V)). The LM324 reaches +10 V on +12 V with little margin, so test at full scale.
- **Check whether the galvo input is differential.** If it is, X− can take V_ref directly and the subtractor isn't needed.
- **Resistor tolerance:** with 1 % resistors expect offset/gain errors of a few tens of mV. Calibrate them out, or use 0.1 % parts.
- **LM324 slew rate is 0.5 V/µs**, so a 10 V step takes ≈ 20 µs. Add this to the predictor's lead time.
- **Check whether the DAC updates X and Y at the same moment.** The architecture plans a simultaneous update (LDAC). Over I2C the two channels may change one after the other; measure the delay between them on the scope.
