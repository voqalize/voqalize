# Imagenología: overview, prices and where each exam is done

Sources: https://www.clini.cl/imagenes (sections "Servicio de Imagenología en CLINI", "Imágenes y procedimientos", "Conoce nuestros exámenes:", "¿Eres paciente FONASA de los tramos B, C o D?", "Resonancias magnéticas $54.990", "Precios de exámenes de imagenología", "Convenio FONASA 1:", "Bono Clini para pacientes Isapre", "¿Por qué elegir Clini para realizar tus exámenes?", "Dr. Eduardo Maddaleno", "¡Conoce más sobre los exámenes de imagenología en CLINI!"); https://www.clini.cl/agendamiento-imagenes (sections "Agenda tu examen de imágenes en minutos", "¡No olvides tu carnet de identidad!", "Preguntas Frecuentes"); https://www.clini.cl/centro-de-salud/vina-del-mar (sections "Centro de Salud Quinta Vergara | CLINI Salud", "¿Qué es ser Fonasa Nivel 1?", "Conoce Nuestros Servicios", "Conoce nuestros precios", "¿Cómo llegar a CLINI Quinta Vergara?", "Preguntas frecuentes"); https://www.clini.cl/ubicaciones; agenda-web.clini.cl.

## The imaging pages (for moving people around)
- **/imagenes** — overview (nav "Imagenología"; /imagenes-fonasa-nivel-1 and /servicios/imagenes redirect here). "En nuestros Centros de Diagnóstico ofrecemos un servicio de Imágenes y Procedimientos con tecnología de excelencia, a los precios más bajos del mercado… somos Fonasa Nivel 1."
- **/agendamiento-imagenes** — the booking hub (header menu "Reservar hora" → "Imágenes"). Cards with "Desde" and "Reservar hora": Resonancias $54.990 (Popular), Mamografías $11.750 (Popular), Tomografías $13.380, Ecografías $7.660 (dropdown: Ecografías / Ecografías Ginecológicas), Radiografías $5.520, PET-CT $322.016. Each "Reservar hora" opens agenda-web for that service.
- Exam pages: Resonancia → /imagenes/resonancias-fonasa-1 (`imagenologia-resonancia`); TAC → /imagenes/realiza-tu-examen-tac-scanner-fonasa-nivel-1 (`scanner`); Ecografías → /imagenes/ecografia-fonasa-nivel-1 (`ecografia`); Mamografía → /imagenes/realiza-tu-mamografia-con-fonasa-en-clini (`mamografia`); Radiografías → /imagenes/radiografias-fonasa-nivel-1 (`radiografia`); PET-CT → /imagenes/examen-pet-ct-con-fonasa-nivel-1 (`pet-ct`). Section "Conoce nuestros exámenes:" on /imagenes has a card for each.

## /imagenes price table (section "Precios de exámenes de imagenología"), Copago Fonasa / Precio particular
| Examen | Fonasa | Particular |
|---|---|---|
| Resonancia magnética columna dorsal | $111.980 | $223.960 |
| Resonancia magnética columna lumbar | $107.670 | $215.350 |
| Resonancia magnética de rodilla | $88.280 | $176.560 |
| Ecografía mamaria – complementaria | $9.600 | $19.210 |
| Mamografía bilateral | $11.750 | $23.500 |
| Pielotac | $13.380 | $26.770 |
| TAC de rodilla | $27.880 | $55.760 |
| TAC de tórax | $51.720 | $103.440 |
| Ecografía abdominal | $13.780 | $30.320 |
| Ecografía Tiroides | $9.600 | $21.130 |
A banner "Resonancias magnéticas $54.990 — Copago fonasa" ("¡Últimos días!") sits above it. For anything not in the table use `quote_price` (the cotizador; prices are the Fonasa Nivel 1 copago for tramos B, C, D and the particular price).

## Fonasa, Isapre and the "desde" prices
- "Convenio FONASA 1:" — "los precios más bajos del mercado para pacientes Fonasa B, C y D… ahorran hasta un 60%" vs a Fonasa 3 centre.
- "Bono Clini para pacientes Isapre" — "programa exclusivo con copago $0. Solo debes inscribirte gratis en cualquiera de nuestros Centros de Salud o Toma de muestras." (topic `fonasa-isapre-convenios`).
- The low "desde" figures on the exam pages (RM $54.990, TAC $13.380, eco $6.990, PET $322.016) are "copago promedio con bonificación de convenios vigentes" — they need a convenio. Say so.
- Results: "Informe médico en 24-48h en tu email" (RM, TAC, eco); PET-CT 48–72 h hábiles. Portal: /resultados → Imagenología (topic `resultados`).
- Dr. Eduardo Maddaleno, Director Médico de CLINI Salud: equipment "proporcionada por Siemens Healthineers".

## Which exam where (from /ubicaciones and agenda-web)
| Exam | agenda-web servicio | Regions on agenda-web | Notes |
|---|---|---|---|
| Resonancia | 64 | 13 RM, 5 Valparaíso | AI resonador at Metro Tobalaba and Alameda; Quillota page (Oxígeno centro médico) |
| TAC / Scanner | 70 | 13, 5 | |
| Radiografía | 57 | 13, 5 | |
| Mamografía | 65 | 13 only | |
| Ecografía general | 81 | 13 only | |
| Ecoginecología | 82 | 13 only | |
| PET-CT | 71 (prestación 35) | no region step | only Metro Tobalaba, Luis Thayer Ojeda 073 |
Sedes tagged "Imagenología" on /ubicaciones: Centro de Diagnóstico CLINI – Metro Tobalaba (Luis Thayer Ojeda 073, piso 2, Providencia), Centro de Salud Astra Alameda (Av. Libertador B. O'Higgins 1529, 2º piso), Astra La Florida (Av. Vicuña Mackenna Poniente 7255, piso 2), Astra Maipú (Av. Pajaritos 2624, local 32), Astra San Miguel (Gran Avenida 5681), Centro Médico Astra Salvador (Av. Salvador 283, Providencia), Centro de Salud Quinta Vergara (Errázuriz 690, Viña del Mar). Hours vary per sede: use `find_branch` and show the sede's "Ver horarios".

## Centro de Salud Quinta Vergara, Viña del Mar (/centro-de-salud/vina-del-mar)
- "¡YA LLEGAMOS VIÑA DEL MAR!" — h1 "Centro de Salud Quinta Vergara | CLINI Salud". Errázuriz 690, frente a Quinta Vergara (cerca de Estación Viña del Mar). Horario: Lunes, Martes y Jueves 08:45–19:30, Miércoles 08:45–19:30, Viernes 08:45–17:00.
- Services ("Conoce Nuestros Servicios"): Resonancia Magnética $54.990*, Tomografías Computarizadas desde $13.380, Radiografías Digitales desde $4.990; "¡Pronto! Toma de muestras".
- "Conoce nuestros precios" (Fonasa + Convenio / Copago Fonasa / Particular): RM rodilla $54.990 / $88.280 / $176.560; RM columna cervical $54.990 / $107.670 / $215.350; RM columna total $54.990 / $190.520 / $381.050; RM abdomen y pelvis $54.990 / $161.490 / $322.990; TAC Pielotac $13.380 / $13.380 / $26.770; TAC tórax, abdomen y pelvis, cerebro, columna lumbar completa $29.990 with convenio; radiografías columna dorsal $6.430, tórax $5.520, extremidad $4.820 (convenio "No aplica").
- The $54.990 there: convenio with Caja Los Héroes, Caja 18, Caja La Araucana and Plataforma Starbien until 31-12-2026, FONASA B, C, D with orden médica. **"Convenio de Caja Los Andes no se encuentra disponible en sucursales de CLINI Viña del Mar (Quinta Vergara) y CLINI Quillota (Centro Oxígeno)."**
- FAQs: orden médica obligatory for RM, TAC and radiografías; reserving with your RUT checks your Fonasa tramo and applies the Nivel 1 price automatically.

## Booking (any imaging exam)
1. Online: agenda-web `https://agenda-web.clini.cl/?servicio=S&prestacion=P` (codes in each exam topic); with a prestación it searches by itself. The visitor presses AGENDAR.
2. Phone 22 994 4003 (L–V 08:00–22:00, Sáb 08:00–20:00, Dom 14:00–22:00); WhatsApp agendamiento asistido.
3. The exam page's request form (call-back from 600 023 1207 within 24 business hours).
/agendamiento-imagenes FAQs: arrive at least 15 minutes early; you need your cédula de identidad and a phone or email; "¡No olvides tu carnet de identidad!" — "debes presentar tu cédula de identidad física vigente".

## Where the site disagrees with itself
- Ecografías "desde" $7.660 (/agendamiento-imagenes, home) vs $6.990 (ecografía page).
- PET-CT "desde" $322.016 (/agendamiento-imagenes) vs $316.416 (home tab).
- Particular prices on /imagenes (eco abdominal $30.320, eco tiroides $21.130) differ from the cotizador ($27.570, $19.210). Prefer the cotizador and say prices may change.
- Viña del Mar: meta description "Resonancias magnéticas desde $59.990, TAC desde $13.380 y radiografías desde $4.990" vs the body's RM $54.990*.
- /imagenes "Ecografía mamaria – complementaria $19.210" particular vs the ecografía page "Ecografía mamaria $21.130".
