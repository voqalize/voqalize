# PET-CT (oncológico y neuro)

Sources: https://www.clini.cl/imagenes/examen-pet-ct-con-fonasa-nivel-1 (sections "Examen PET-CT", "Encuentra el PET-CT que necesitas", "¿Qué detecta el PET-CT?", "¿Dónde estamos?", "Precios del PET-CT", "Preguntas frecuentes del PET-CT", "Cuida tu salud sin complicaciones"); https://www.clini.cl/indicaciones-pet (section "Indicaciones para exámenes PET-CT", dropdowns per radiotrazador); https://www.clini.cl/agendamiento-imagenes (card "PET-CT Desde: $322.016"); https://www.clini.cl/ (home tab "Imágenes": "PET-CT Desde: $316.416"); https://www.clini.cl/centro-oncologico; cotizador catalogue (L3/prices.json, servicio PET-CT); agenda-web.clini.cl servicio 71.

## What the site says
- Page /imagenes/examen-pet-ct-con-fonasa-nivel-1, h1 "Examen PET-CT", "Valor Fonasa nivel 1 en la Región Metropolitana". PET-CT combines tomografía por emisión de positrones with a tomografía; the site calls it "fundamental en la detección temprana del cáncer" and for monitoring treatment.
- Hero **"VALOR FONASA DESDE $322.016"** ("COPAGO PROMEDIO CON BONIFICACIÓN DE CONVENIOS VIGENTES"; "Otros centros: $805.040"), "+10.000 PACIENTES", **"2-3 HORAS DURACIÓN"**.
- Fine print: the special price is "un 20% de descuento sobre el arancel Fonasa", valid until 31 December 2026, only for FONASA B, C, D affiliates of the convenio entities listed at www.clini.cl/convenios; not combinable; "no aplica para los exámenes PET-CT PR04 ni FAN".
- Form "Solicita una reserva para tu examen PET-CT:" (`#wf-form-from_pet`: name, documento, email, phone, previsión, orden upload) — "nuestro equipo de imagenología se contacte con usted". The visitor submits it.
- "¿Dónde estamos?": **only at Centro Médico CLINI Providencia, Luis Thayer Ojeda 073, Providencia, a una cuadra del Metro Tobalaba.**
- It belongs to the Centro Oncológico CLINI ("PET-CT, tomografías y resonancia magnética para tu diagnóstico y seguimiento"; topic `oncologia`).

## Types (section "Encuentra el PET-CT que necesitas")
- PET CT oncología general con 18F-FDG — Valor fonasa $402.520.
- PET CT por cáncer de próstata 18F-PSMA — $402.520.
- PET CT neuro con 18F-FDG / 18F-PR4 / 18F-FBB — $402.520 (FDG metabolismo de glucosa; FBB beta-amiloide; PR4 proteína Tau).
- PET CT tumores neuroendocrinos 18F-NOTA-OCTREOTIDE — $402.250.
"¿Qué detecta el PET-CT?": tumores malignos y su actividad, metástasis, función celular y metabólica, lesiones en etapas tempranas. Never interpret anyone's case.

## Prices (section "Precios del PET-CT"), Copago Fonasa / Particular
PET-CT FLORBETABEN $402.540 / $805.040; PET-CT PR04 $402.540 / $805.040; PET-CT NOTA (FAN) $402.540 / $805.040; PET-CT PSMA $402.540 / $805.040; PET-CT FDG $402.520 / $805.040. Cotizador: Pet-ct fdg, fdg cerebral, psma $402.520 / $805.040; its preparation text: "Las indicaciones específicas para la preparación del examen serán enviadas al correo registrado del paciente."

## FAQs (section "Preguntas frecuentes del PET-CT")
- Orden médica: obligatory, vigente ≤ 6 meses (validates the indication and the radiofármaco, and Fonasa/Isapre coverage).
- Resultado: informe "entre 48 y 72 horas hábiles".
- Preparación: "ayuno estricto de 4 a 6 horas (solo puedes beber agua pura)", no azúcares ni carbohidratos desde el día anterior, avoid intense exercise 24–48 h before; diabetes or regular medication → specific instructions when booking.
- Duración: 2 a 3 horas in the clinic; after the injection ~60 minutes of rest; the scan 15–30 minutes.
- Fonasa or Isapre: yes, with the orden médica.
- Precio: depends on the radiofármaco (FDG, PSMA…) and previsión.
- After the exam: drink plenty of water; avoid close contact with small children and pregnant women for 6 to 12 hours.
- Tell the team about pregnancy, lactancia, diabetes, difficulty lying still for 30 minutes, contrast allergy.
- Cancel or reschedule **at least 24 to 48 hours ahead** (the radiofármaco is produced for the appointment).

## Indicaciones PET-CT (/indicaciones-pet)
h1 "Indicaciones para exámenes PET-CT"; one dropdown per tracer: **FDG CUERPO ENTERO**, **18/FDG CEREBRAL**, **18F/PSMA**, **F18-NOTA-OCTREOTIDE**, **F18-PR04 CEREBRAL**, **F18-FBB FLORBETABEN CEREBRAL**, **F18-FLUORO-FAPI** (open the one the visitor's order names with `{faq: …}`). Common points, as the site writes them:
- Día anterior: take usual medication. For FDG (cuerpo entero, cerebral): avoid exercise, long walks and cold; from 20:00 h the day before no azúcares ni carbohidratos (only carnes, huevo, vegetales verdes; té o café sin azúcar).
- Día del examen: bring orden médica and cédula; **ayuno de 6 h** (FDG, PSMA, NOTA-OCTREOTIDE, FAPI; PR04 and FBB list no fasting); drink 2 litros de agua and urinate often; arrive 20 minutes early and allow at least 2 hours; comfortable warm clothes without metal, no jewellery; bring previous exams.
- FDG: a vía venosa for the radiotrazador, 1 hour of rest alone, then contraste yodado. Metformina (Glafornil, Glucophage…) suspended the day before and the day of; insulin per the instructions given when booking; ≥ 65 años, diabetes, hipertensión, enfermedad renal or autoinmune → a creatinina exam beforehand; embarazo: cannot have the exam; lactancia: extract milk beforehand (per the page).
- PR04 cerebral: suspend Levodopa 24 hours before.
Read these as the site's instructions; anything about the visitor's own medication → their doctor or the call center.

## Booking
- agenda-web servicio **71** (PET-CT), prestación **35 PET CT**: `https://agenda-web.clini.cl/?servicio=71&prestacion=35` (no region step). The site links it through the legacy `agenda-imagenes.clini.cl/FrmAgendaMain.aspx?PET_CT=CLTO`, which redirects there.
- Or the page's request form, or call 22 994 4003.

## Where the site disagrees with itself
- "Desde": $322.016 (PET page hero, /agendamiento-imagenes), $316.416 (home "Imágenes" tab; the research crawl recorded it as "copago fijo máximo"), vs $402.520 Fonasa per type. The $322.016 is with the convenio 20% discount; say "desde" with that condition.
- FDG $402.520 vs others $402.540 in the table; NOTA-OCTREOTIDE card $402.250.
- Fasting: FAQ "4 a 6 horas"; /indicaciones-pet "6 hrs". Quote /indicaciones-pet for the specific tracer and suggest confirming when booking.
