### ATIS → Markdown
```json
{
  "source_format": "atis",
  "target_format": "markdown",
  "data": "KSFO ATIS INFO NOVEMBER 1956Z. 28015KT 10SM FEW015 BKN030 14/08 A2992. ILS RWY 28L APCH IN USE. DEPTG RWY 28L. NOTAM BIRDS IN VICINITY."
}
```
Returns:
```
## ATIS — KSFO INFO NOVEMBER
**Flight Category:** 🟢 VFR
**Wind:** 280deg at 15kt
**Visibility:** 10.0 SM
**Sky:** FEW @ 1500ft, BKN @ 3000ft
**Runways In Use:** 28L
**Departure Runway:** 28L
**NOTAMs:** BIRDS IN VICINITY
```
