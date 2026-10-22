# Cardiología: electrocardiograma, Holter de ritmo, Holter de presión (MAPA) y ecocardiograma

Sources: https://www.clini.cl/examenes-de-cardiologia-fonasa-nivel-1 (sections "Exámenes de Cardiología en CLINI", "Conoce nuestros exámenes:", "Precios de los exámenes de Cardiología en CLINI", "Bono Clini para pacientes Isapre"); https://www.clini.cl/cardiologia/realiza-tu-electrocardiograma-de-reposo-en-clini; https://www.clini.cl/cardiologia/realiza-tu-holter-de-ritmo-en-clini; https://www.clini.cl/cardiologia/realiza-tu-holter-de-presion-mapa-en-clini (section "Recuerda traer tus pilas AA"); https://www.clini.cl/cardiologia/ecocardiograma-fonasa-1 (sections "Ecocardiograma Doppler", "¿Qué es un ecocardiograma doppler?", "Cobertura de salud"); https://www.clini.cl/agendamiento-cardiologia (section "Agenda tu examen de cardiología en minutos", "Preguntas Frecuentes"); home https://www.clini.cl/ (tab "Exámenes Cardiológicos" in "Conoce los servicios que en CLINI tenemos para ti"); cotizador catalogue (L3/prices.json); agenda-web services 76–79.

CLINI does four cardiology exams ("Exámenes de Cardiología en CLINI"), with Fonasa Nivel 1 prices for tramos B, C and D and a "Bono Clini" for Isapre patients. The site lists no cardiology *consultation* — only the exams. Results: the page offers a "Resultados de cardiología" button (see topic `resultados`). Call center 22 994 4003 (L–V 08:00–22:00, Sáb 08:00–20:00, Dom 14:00–22:00).

## The four exams (section "Conoce nuestros exámenes:")

| Exam | What the site says | Copago Fonasa | Particular | agenda-web |
|---|---|---|---|---|
| **Electrocardiograma de reposo (ECG)** | Records the heart's electrical activity at rest with electrodes on the skin; detects arritmias, bloqueos, signos de infarto. **10 a 15 minutos**; you may be asked to avoid caffeine and stimulants; slight skin discomfort, not painful. | $3.810 | $7.620 | servicio **78**, prestación 49 |
| **Holter de ritmo** | Ambulatory ECG for **24 a 48 horas**; detects arritmias, taquicardia, bradicardia; "esencial para pacientes con síntomas de palpitaciones o desmayos inexplicables". Keep an activity and symptom diary. | $17.880 | $35.760 | servicio **76**, prestación 46 |
| **Holter de presión (MAPA)** | Monitor Ambulatorio de Presión Arterial, measures blood pressure continuously for **24 horas**, day and night; key to diagnose hypertension and its control. Keep a diary. | $12.490 | $24.980 | servicio **77**, prestación 47 |
| **Ecocardiograma doppler color** (bidimensional, transtorácico) | Non-invasive ultrasound of the heart's structure and function: size and shape, wall movement, valves. **20–30 minutos · Sin ayuno previo · Resultado en 24–48 hrs**. "*Para mayores de 15 años*". | $38.010 | $76.030 | servicio **79**, prestación 50 |

Prices are the table "Precios de los exámenes de Cardiología en CLINI" on /examenes-de-cardiologia-fonasa-nivel-1, which match the cotizador. Say prices as "desde" when quoting a card (the cards say "Desde:").

Ecocardiograma page (/cardiologia/ecocardiograma-fonasa-1, hero "Ecocardiograma Doppler", "Valor FONASA 1 en Región Metropolitana"): "VALOR FONASA DESDE **$30.000** — COPAGO PROMEDIO + BONIFICACIÓN DE CONVENIOS VIGENTES · MAYORES DE 15 AÑOS"; "Otros centros: $83.630". Section "Cobertura de salud": "Atendemos FONASA e ISAPRE" — Fonasa: bono electrónico desde Fonasa.cl, copago según tramo, "Atención inmediata con orden médica"; Isapre: todas las Isapres, reembolso según plan, "Requiere orden médica del especialista", cobro directo a tu Isapre; consultar cobertura al 22 994 4003.

## Preparation (cotizador and the exam pages)
- **Electrocardiograma**: no cremas ni aceites en el tórax.
- **Holter de ritmo**: llevar **1 pila AA** Duracell; no cremas/lociones/aceites en el tórax; ropa holgada; no retirar ni manipular los cables. Desde los **14 años**.
- **Holter de presión**: llevar **2 pilas AA** Duracell; ropa holgada; actividades habituales permitidas; no mojar el equipo ni el manguito; no manipular cables ni manguito. Desde los **15 años**. Celulares y microondas no interfieren.
- **Ecocardiograma**: si fue operado del corazón, traer exámenes cardiológicos anteriores; sin cremas en el tórax; ropa cómoda (se descubre el torso); **no requiere ayuno**; puede tomar sus medicamentos habituales según indicación de su médico.
- Section "Recuerda traer tus pilas AA" (on the ECG, Holter de ritmo and Holter de presión pages): "dos pilas AA nuevas, de preferencia marca Duracell o Energizer… si se descargan durante el examen, será necesario repetirlo." (See the disagreement below about one vs two batteries.)
- /agendamiento-cardiologia "¡No olvides tu carnet de identidad!": bring your physical, valid cédula de identidad.

## Booking
- agenda-web deep links (Región Metropolitana only, region 13): Holter de ritmo `https://agenda-web.clini.cl/?servicio=76&prestacion=46`, Holter de presión `?servicio=77&prestacion=47`, Electrocardiograma `?servicio=78&prestacion=49`, Ecocardiograma `?servicio=79&prestacion=50`. Each has a single prestación, so the page selects it and searches by itself. The visitor fills the form and presses **AGENDAR** themselves.
- /agendamiento-cardiologia ("Agenda tu examen de cardiología en minutos") has the four cards with "Reservar hora" and "Conocer más". The header menu "Reservar hora → Cardiología" goes there.
- Sedes with cardiology ("Laboratorio Cardiología" tag on /ubicaciones): Metro Tobalaba, Astra Alameda, Astra La Florida, Astra Maipú, Astra Salvador (see topic `sedes`).
- FAQs on /agendamiento-cardiologia ("Preguntas Frecuentes"): ¿Cómo puedo agendar una hora? (online: service, day and time, your data, automatic confirmation); ¿Qué necesito para agendar una hora? (cédula de identidad and a phone or email); ¿Cuánto tiempo antes debo llegar a mi cita? (**al menos 15 minutos antes**); ¿Qué pasa si no puedo asistir a mi cita? (reprogramar o cancelar; agenda-web's menu also has "Cancelar cita").
- A test de esfuerzo (servicio 83) exists in the booking system but no page of the site offers it.

## Where the site disagrees with itself
- **Electrocardiograma**: $3.860 on the home tab "Exámenes Cardiológicos" and on /agendamiento-cardiologia ("Desde: $3.860"); $3.810 in the price table of /examenes-de-cardiologia-fonasa-nivel-1, on /cardiologia/realiza-tu-electrocardiograma-de-reposo-en-clini ("$3.810 *Copago fonasa") and in the cotizador.
- **Holter de ritmo**: $17.860 on the home tab and /agendamiento-cardiologia; $17.880 in the price table and the cotizador; $17.810 in the hero of /cardiologia/realiza-tu-holter-de-ritmo-en-clini. Quote the cotizador ($17.880) and say it is confirmed when booking.
- **Ecocardiograma**: "desde $30.000" (copago promedio + bonificación de convenios) on its own page vs $38.010 everywhere else (the same page also says "Desde $38.010 de copago").
- On /cardiologia/ecocardiograma-fonasa-1 "Nuestros servicios" the descriptions of Holter de presión and Holter de ritmo are swapped (presión says "Monitoreo continuo del ritmo cardíaco", ritmo says "Monitoreo ambulatorio de presión arterial"); the exam pages themselves are right.
- Batteries: the pages say two AA batteries for any Holter; the cotizador says 1 for Holter de ritmo and 2 for Holter de presión.
- Ages: ecocardiograma "mayores de 15 años"; Holter de ritmo "desde los 14 años" (cotizador).
