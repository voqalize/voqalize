# Preparación de exámenes (how to prepare: fasting, urine, contrast)

Sources: https://www.clini.cl/indicaciones (sections "Busca tus indicaciones según el servicio que necesites", "Indicaciones:"); https://www.clini.cl/indicaciones-pet (section "Indicaciones para exámenes PET-CT"); the /examenes/* pages (field "Ayuno:"); https://www.clini.cl/laboratorio (section "¡Compara y ahorra!", FAQ "¿Cómo puedo saber cuáles son las indicaciones de mis exámenes?"); https://www.clini.cl/agendamiento (FAQ "¿Cuánto tiempo antes debo llegar a mi cita?"); the cotizador's `preparacion` field (cotizador-web.clini.cl, L3/prices.json); agenda-web's per-centre "Indicaciones" after "Continuar".

Only say what the site says. The best source for one exam is the live price lookup (`quote_price`), whose result carries that exam's preparation, then agenda-web's indications for the chosen centre. When unsure, the site itself says to call 22 994 4003 ("Las indicaciones de este examen pueden variar. Para mayor información, llamar al 22 994 4003" — 174 lab items say exactly this).

## Where the site keeps it
- **/indicaciones** — "Busca tus indicaciones según el servicio que necesites": a filterable list (filters Todas, Resonancia Magnética, Tomografía Computarizada, Mamografía, Ecografía, Cardiología) under the heading "Indicaciones:". Each card shows the exam, its Código Fonasa and service; its text opens as a dropdown; "Ver más" loads more. It covers imaging and cardiology, not lab.
- **/indicaciones-pet** — "Indicaciones para exámenes PET-CT": one dropdown per tracer (FDG CUERPO ENTERO, 18/FDG CEREBRAL, 18F/PSMA, F18-NOTA-OCTREOTIDE, F18-PR04 CEREBRAL, F18-FBB FLORBETABEN CEREBRAL, F18-FLUORO-FAPI), each with "DÍA ANTERIOR" and "DÍA DEL EXÁMEN" steps (detail in topic `pet-ct`). The cotizador says PET-CT instructions are emailed to the patient.
- **/examenes/<exam>** — every lab explainer shows "Ayuno:" (topic `examenes-laboratorio`).
- agenda-web, after "Continuar": a service alert ("Entendido") and the centre's indications (`#appointmentIndications`).

## Laboratorio (cotizador wording)
- **"Sin indicaciones"** — 419 lab items, e.g. hemograma VHS, creatinina, vitamina D, hemoglobina glicada, perfil tiroideo.
- **Ayuno 8 hrs.** — glucosa, perfil bioquímico, insulina, fierro sérico. **Ayuno 6 hrs.** — perfil hepático, fosfatasas alcalinas, fósforo. **Ayuno 9 hrs.** — perfil lipídico, triglicéridos. **Ayuno 12 hrs.** — péptido C.
- **Curvas de glucosa / insulina** — "ayuno de mínimo 8 horas y máximo 10 horas antes de su examen".
- **Orina aislada / orina completa / urocultivo** — "Requiere 4 horas sin orinar". Orina de primer chorro (cultivos, PCR ETS en orina) — "Requiere 1 hora sin orinar". **Orina de 24 horas** — "Recolectar orina durante 24 hrs."
- **Cortisol AM** — rest at least 30 minutes; the sample is taken at 09:00 h (agenda-web: book it at 9 h; Cortisol PM is not done).
- **Vaginal / endocervical cultures** — normal hygiene; no period in the previous 48 h; 48 h sexual abstinence; no vaginal ovules, douches, talc, creams or colognes in the 48 h before. Gynaecological samples are booked at Los Leones.
- /laboratorio's sample order ("¡Compara y ahorra!") gives general indications: "Presentarse con ayuno de 8-12 horas • Traer orden médica y carnet de identidad".

## Imaging (cotizador and /indicaciones)
- **Resonancia (RM)** — most body parts: "No requiere preparación especial. Sin embargo, si la orden médica indica que el examen es con contraste, se debe realizar ayuno total de 2 horas". Some need 2 h fasting anyway (cuello, glúteos, fosa posterior); abdomen, abdomen y pelvis, renal: 6 h; colangioresonancia: 8 h. Próstata multiparamétrica: Tobalaba 2 h fasting, other sedes 6 h plus soft diet the day before, and a PSA no older than 30 days.
- /indicaciones general RM rules: bring carnet, orden médica (valid up to 12 months), arrive 30 minutes early, bring previous exams; from 12 years old; remove metal objects; women of childbearing age who might be pregnant rule it out with a test first; tattoos in the area may feel warm. With contrast: patients who are diabetic, renal, over 65 and others listed must bring a creatinina no older than 3 months (7 days with renal insufficiency).
- **TAC / scanner** — "No requiere preparación especial … con contraste … ayuno total de 6 horas"; angio-TAC: 6 h fasting. /indicaciones: contrast costs "$35.000 (se paga adicional)". PieloTAC: drink water 1–3 h before and hold urine about 1 h. TAC abdomen y pelvis: 6 h without solids; at CLINI Tobalaba also hold urine 1–3 h.
- **Ecografía** — most: "Sin preparación especial." Abdominal: "AYUNO COMPLETO … 6 horas" (diabetics at least 4 h; children 0–4 years 3 h). Hepatobiliar: 6–8 h. Pelviana / ginecológica transabdominal: drink plenty of water and hold urine 1 h 30 min. Mamaria: no deodorant or creams; from 40 years old bring a mammogram no older than 8 months. Axilas: no deodorant. Transvaginal: empty bladder. Obstétrica / 4D-5D: no preparation; doppler 11–14 and 20–24 weeks: bring the pregnancy control card.
- **Mamografía** — "No requiere ayuno ni medicamentos previos"; no deodorant, antiperspirant, creams, talc, oils or perfume on armpits or chest that day.
- **Radiografía** — "Sin preparación especial", except RX abdomen simple: 6 h fasting.

## Cardiología (cotizador)
- **Electrocardiograma** — no creams or oils on the chest.
- **Ecocardiograma** — no fasting; no creams on the chest; clothes easy to remove; usual medicines; bring previous cardiac exams after heart surgery.
- **Holter de ritmo** — bring 1 AA Duracell battery; loose clothes; don't touch the cables; from 14 years old.
- **Holter de presión (MAPA)** — bring 2 AA Duracell batteries; loose clothes; normal activities; keep the device dry.

## Consultas y kinesiología
Consultas: "Sin preparación especial". Kinesiología: comfortable clothes and sneakers; the price is per session.

## Always
Bring cédula de identidad and the medical order; arrive 15 minutes early (/agendamiento FAQ; RM says 30 minutes). Don't give medical advice beyond these texts: questions about medicines or illness go to the treating doctor or the call center.

## Where the site disagrees with itself
- Hemograma: /examenes/examen-de-sangre shows "Ayuno: 8 Horas" but its text says "el hemograma no requiere de ayuno"; the cotizador says "Sin indicaciones".
- Curvas: the explainer pages say 8 h fasting; the cotizador says 8–10 h.
- General lab fasting "8-12 horas" (/laboratorio example) vs exam-specific fasting in the cotizador. Quote the exam's own line.
- Arrival: 15 minutes (/agendamiento, /laboratorio) vs 30 minutes for RM (/indicaciones).
