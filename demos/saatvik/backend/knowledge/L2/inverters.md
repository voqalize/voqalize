# Inverters — Uday on-grid and UDAY Plus hybrid

Sources (checked live 2026-10-14): https://www.saatvikgroup.com/inverters, /inverters/single-phase, /inverters/three-phase, /inverters/hybrid; PDFs saatvik-uday-series-single-phase-inverter-flyer pp 1–4 (p 1–2 single-phase, p 3–4 three-phase; p 4 is an image, its text is OCR), saatvik-hybrid-inverter-datasheet p 1, the user manuals saatvik-single-phase-1-1-3-3kw-inverter-user-manual, saatvik-single-phase-3-68-6kw-inverter-user-manual, saatvik-three-phase-6-12kw-inverter-user-manual, saatvik-three-phase-15-25kw-inverter-user-manual, saatvik-three-phase-30-50kw-inverter-user-manual, saatvik-hybrid-inverter-3-8kw-single-phase-user-manual, and saatvik-gti-inverter-wifi-setup-guide.

The pages and the datasheets disagree on several numbers. Where they do, both are written below: quote the page as the page's claim and the datasheet as the model's specification, and offer to open the datasheet.

## Uday Series, on-grid (grid-tie) string inverters
- From 1.1 kW single-phase units for homes to 50 kW three-phase units for commercial and industrial plants. Standard 10-year warranty (the pages; the manuals give the claim procedure, not the term). IP65 with anti-PID protection. Grid support: reactive-power compensation, low-voltage ride-through, anti-islanding. Certified to IEC 62109-1 and -2; IEC 61000 (EMC), CE, BIS; made in India.
- Efficiency: every page says "over 98.7% peak efficiency". The datasheets give maximum efficiency 97.5–97.9% for the single-phase models and 98.4–98.8% for the three-phase; 99.9% is their MPPT efficiency. If asked for a model's efficiency, give the datasheet figure.
- The /inverters stat strip also says "1500 V max system voltage"; the datasheets give a maximum PV input voltage of 500–600 V (single-phase) and 1100 V (three-phase).
- An on-grid inverter needs the grid: it shuts down in a power cut (anti-islanding). For backup, the UDAY Plus hybrid below.
- Monitoring: the Saatvik app "SAATVIK SOLAR INVERTERS" (Google Play / App Store), over a Wi-Fi, 4G or Ethernet module plugged into the inverter's COM port. Setup (Wi-Fi guide): create an account and a plant, add the inverter by serial number (typed or scanned), then Services → Configuration → Wifi-G2 with Bluetooth on, enter the home router's name and password, press Start; a "Linked Module" message appears and the Wi-Fi stick shows a constant green LED.

The page's comparison table (/inverters, "Compare Specifications"):
| | 1.1–3.3 kW | 3.68–6 kW | 6–12 kW | 15–25 kW | 30–50 kW |
|---|---|---|---|---|---|
| Phase | single | single | three | three | three |
| Max efficiency (page) | >98.7% | >98.7% | >98.7% | >98.7% | >98.7% |
| Max efficiency (datasheet) | 97.5–97.6% | 97.9% | 98.4–98.5% | 98.6% | 98.6–98.8% |
| MPPT channels (page) | 1 | 2 | 2 | 2–4 | 2–4 |
| MPPT trackers (datasheet) | 1 | 1 | 2 | 2 | 3 (30 kW), 4 (40, 50 kW) |
| MPPT voltage (page) | 80–500 V | 80–500 V | 200–800 V | 200–1000 V | 200–1000 V |
| MPPT voltage (datasheet) | 45–550 V | 80–550 V | 140–1000 V | 180–1000 V | 180–1000 V |
| Max PV input voltage (datasheet) | 500–550 V | 600 V | 1100 V | 1100 V | 1100 V |
| Communication (page) | Wi-Fi / RS485 | Wi-Fi / RS485 | Wi-Fi / RS485 | RS485 / Ethernet | RS485 / Ethernet |
| Communication (datasheet) | optional Wi-Fi, 4G, Ethernet | same | RS485, USB; optional Wi-Fi, 4G, Ethernet | same | same |
| Protection | IP65 | IP65 | IP65 | IP65 | IP65 |
| Warranty | 10 years | 10 years | 10 years | 10 years | 10 years |

### Single phase (/inverters/single-phase)
- For homes, villas and small establishments. The page: over 98.7% efficiency, "80–500 V MPPT window ... with 1–2 MPPT channels", built-in Wi-Fi ("no extra dongle required"), quieter than 25 dB, slim wall mount, IP65 with surge, islanding and earth-fault protection. Two ranges: 1.1–3.3 kW "for smaller homes" and 3.68–6 kW "for villas and small establishments".
- Flyer pp 1–2 (models SS-GTI-1P 1.1, 2.2, 2.5, 2.7, 3, 3.3, 3.68, 4, 5 and 6 kW): 150% PV input oversizing; one MPPT on every model; max PV current up to 25 A; max efficiency 97.5% (1.1–2.5 kW), 97.6% (2.7–3.3 kW), 97.9% (3.68–6 kW); Euro efficiency 96.9–97.2%; MPPT efficiency 99.9%; 220/230/240 V, 50/60 Hz; power factor 0.8 leading to 0.8 lagging; THDi under 3%; transformerless; natural cooling; LED + OLED display; communication optional Wi-Fi, 4G or Ethernet; optional AFCI; optional DC switch; built-in zero export (optional); Type II DC and AC surge protection; ambient −25 to +60 °C; up to 2000 m; night consumption under 1 W; noise under 25 dB; MC4 connectors; wall bracket. 1.1–3.3 kW: 290 × 220 × 119 mm, 5.5 kg. 3.68–6 kW: 353 × 320 × 150 mm, 10 kg.
- On Wi-Fi the page and the flyer differ: the page says built in, the flyer and manuals call Wi-Fi, 4G or Ethernet an optional module. Say monitoring is over Wi-Fi and let the dealer confirm what ships in the box.
- Documents on the page: "Download datasheet" and "Uday Series Single-Phase Flyer" (the flyer), the 1P 1.1–3.3 kW and 1P 3.68–6 kW user manuals, the GTI Wi-Fi settings guide, Solar PV installation do's and don'ts, and the on-grid solar kit installation guide.

### Three phase (/inverters/three-phase)
- For commercial and industrial solar, 6–50 kW (models 6, 8, 10, 12, 15, 20, 25, 30, 40 and 50 kW): multi-MPPT (up to 4), active/reactive power control, LVRT, anti-PID, smart cooling, RS485/Ethernet and SCADA integration. 6–12 kW for commercial rooftops, 15–25 kW for industry and factories, 30–50 kW for large C&I and carport plants.
- The page says a "200–1500 V operating window" and "built-in PID recovery"; the datasheet (flyer p 4) says MPPT 140–1000 V (6–12 kW) or 180–1000 V (15–50 kW), max PV input 1100 V, and PID recovery "Optional".
- Flyer p 4: 150% PV oversizing; max efficiency 98.4% (6 kW), 98.5% (8–12 kW), 98.6% (15–30 kW), 98.8% (40–50 kW); Euro 97.5–98.2%; MPPT 99.9%; 3/N/PE 220/380 or 230/400 V; string current monitoring, Type II DC and AC SPD, DC switch integrated; AFCI optional; zero export optional. 6–12 kW: 428 × 385 × 185 mm, 15 kg, natural cooling. 15–25 kW: 520 × 412 × 200 mm, 22 kg, fan. 30–50 kW: 585 × 480 × 220 mm, 37 kg, fan. Noise under 35 dB. Communication RS485 and USB, Wi-Fi, 4G or Ethernet optional. Manuals add a meter/CT export limit and RS485 networking of up to 112 inverters with the optional EMB-100.
- The page's "Download datasheet" button opens the 15–25 kW user manual, not a datasheet. The three-phase spec table is page 4 of the single-phase flyer (open_document saatvik-uday-series-single-phase-inverter-flyer, page 4).

## UDAY Plus hybrid inverter (/inverters/hybrid)
- One unit that manages solar panels, the grid and a battery, keeping essential loads running in a power cut. Single phase. Works with lead-acid and lithium-ion batteries (a 48 V-class bank: battery voltage range 40–60 V). Dual MPPT, "up to 99% MPPT efficiency" (the hero image and datasheet say over 99%). 200% PV input oversizing. IP65, installable outdoors. Monitoring via Wi-Fi / 4G. 5-year warranty. IEC, BIS, CE, ISO 9001 & 14001, made in India.
- For homes, shops, offices, small businesses, schools, clinics, and areas with frequent power cuts.
- Sizes: the page says 3.6 kW to 8 kW. The datasheet and manual list nine models, 3, 3.6, 4, 5, 6, 6.6, 7, 7.5 and 8 kW (SS-HYB-LV-…-1PH-A1); the datasheet's banner says "3.6 - 10 kw". Quote 3.6–8 kW and let the team confirm a 3 kW or larger unit.
- Datasheet figures: max efficiency 97.6%, Euro 97.0%; MPPT 90–450 V, max PV input 500 V; max battery charge/discharge current 70 A (3 kW) to 190 A (7.5–8 kW); battery communication CAN; switchover under 10 ms; backup output equal to the rated power, with a peak of 1.5 × rated for 10 s (the manual: an air conditioner can start at 3–6 × its rating, so check start loads); up to 6 units in parallel; 598 × 364 × 246.5 mm; 28 kg; LED + LCD; RS485, CAN, dry contact, optional Wi-Fi, 4G or Ethernet; −30 to +60 °C (derating above 45 °C); natural cooling and under 30 dB on the smaller models, fan and under 50 dB on the larger; standby under 15 W; IEC 61727, IEC 62116, IEC 62109-1/-2, EN IEC 61000-6-1/-6-3, EN 62920. Altitude: datasheet under 3000 m, manual 4000 m with derating above 2000 m.
- Warranty (user manual p 43–44): "Warranty is available for 5 Years from the date of purchase", for manufacturing and material defects only; register the product on saatvikgroup.com within 30 days of purchase; surge protection devices are excluded; it is void if serviced by unqualified technicians or installed without proper ACDB/DCDB, earthing and lightning arrester. Claims: 1800-547-1151 and sales@saatvikgroup.com.
- Pairs with the UDAY Shakti battery (topic `batteries`).

## Booking
- Each inverter page's "Book now" opens Saatvik's two-step booking: /book?product=uday-single-phase (also the /inverters overview's button), /book?product=uday-three-phase, /book?product=uday-plus-hybrid. Step 1 picks the installation type, residential or commercial; step 2 takes full name, mobile, email, address, state, city, pincode and a consent tick, then "Confirm booking". "No payment is needed now. Confirm your details and a Saatvik specialist will call you to size the system and share a quote." The battery and BESS pages have no booking.

## Service
- Inverter after-sales: toll-free 1800-547-1151 and the pan-India service network. For an on-grid warranty claim the manuals ask for the model and serial number, a copy of the invoice and warranty certificate, the error on the screen and the system details. Out of warranty, Saatvik charges a site visit fee, parts, labour and logistics.
