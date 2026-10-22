# Sedes: dónde está CLINI, qué atiende cada una y sus horarios

Sources: https://www.clini.cl/ubicaciones (section "Horarios y Ubicaciones CLINI": the filter and each branch's "Ver horarios" dropdown; L3/branches.json); https://www.clini.cl/astra/clinica-astra-evoluciona-centros-medicos-fonasa-nivel-1 (sections "NO ES UN CAMBIO, ¡ES UNA EVOLUCIÓN!", "¿Qué significa esto para ti?", "¡Nuevos servicios disponibles!", "Horarios y Ubicaciones", "Preguntas Frecuentes"); https://www.clini.cl/centro-de-salud/vina-del-mar (sections "Centro de Salud Quinta Vergara | CLINI Salud", "Conoce nuestros precios", "¿Cómo llegar a CLINI Quinta Vergara?", "Preguntas frecuentes"); https://www.clini.cl/laboratorio (section "Realiza tus muestras ahora también los Domingos"); https://www.clini.cl/cirugia-lasik (section "📍 Estamos cerca de ti"); https://www.clini.cl/resored (section "Presencia en toda la Capital.").

/ubicaciones lists **20 sedes** in one Finsweet CMS list. Each card: name (heading), "Dirección:", service tags, a **"Ver horarios"** dropdown (click it to show the hours) and "Reserva tu hora". The filter at the top: **Región** select, **Comuna** select, a text search and service checkboxes (Evaluación Cirugía Lasik, Consultas Médicas, Imagenología, Toma de Muestras, Laboratorio Cardiología, Kinesiología). Show a branch by its name (e.g. `{show: Centro Médico Astra Salvador}`); the adapter opens its "Ver horarios". There are no maps or coordinates on /ubicaciones; addresses only. "Laboratorio Cardiología" is how the site tags cardiology exams.

## Región Metropolitana (14)
| Sede | Dirección | Servicios | Horario |
|---|---|---|---|
| Centro de Diagnóstico CLINI - Metro Tobalaba | Luis Thayer Ojeda 073, Piso 2, Providencia. A pasos del Costanera Center. | Evaluación Cirugía Lasik, Imagenología, Laboratorio Cardiología | L–V 08:00–21:00; Sáb 08:00–20:30; **Dom 09:00–20:30** |
| Centro de Salud Astra Alameda | Av. Libertador Bernardo O'Higgins 1529, 2 piso Clínica Astra (Santiago Centro). A pasos del Metro La Moneda. | Toma de Muestras, Imagenología, Laboratorio Cardiología, Consultas Médicas | Centro de Salud L–V 07:30–18:00; Toma de muestras L–V 7:00–15:00, Sáb 07:30–14:00, **Dom 08:30–13:00** |
| Centro de Salud Astra La Florida | Av. Vicuña Mackenna Poniente 7255, Piso 2, La Florida | Toma de Muestras, Imagenología, Kinesiología, Consultas Médicas, Laboratorio Cardiología | L–V 07:30–20:00; **Dom 08:30–14:00** |
| Centro de Salud Astra Maipú | Av. Pajaritos 2624, Local 32, Maipú | Kinesiología, Imagenología, Toma de Muestras, Consultas Médicas, Laboratorio Cardiología | Centro L–V 08:00–19:30; Toma de muestras L–V 7:00–15:00, Sáb 07:30–14:00, **Dom 08:30–13:00** |
| Centro de Salud Astra San Miguel | Gran Avenida 5681 | Imagenología, Kinesiología, Consultas Médicas, Toma de Muestras | Centro L–V 07:30–20:00; Toma de muestras L–V 7:00–15:00, Sáb 07:30–14:00; Dom sin atención |
| Centro Médico Astra Salvador | Av. Salvador 283, Providencia. A pasos del Metro Salvador. | Toma de Muestras, Imagenología, Kinesiología, Laboratorio Cardiología, Consultas Médicas | Centro L–V 07:30–20:00; Toma de muestras L–V 7:00–15:00, Sáb 07:30–14:00; Dom sin atención |
| Toma de Muestras Buin | Santa María 399, Buin | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; **Dom 08:30–13:00** (larga duración: L–V 7:00–13:30, Sáb 07:30–12:00, Dom 08:30–10:45) |
| Toma de Muestras Mall Florida | Mall Cenco Florida, planta -1, acceso Jumbo (La Florida) | Toma de Muestras | L–V 7:30–15:00; Sáb 08:00–14:00; **Dom 09:00–13:00** |
| Toma de Muestras Metro Los Leones | Coyancura n° 2244, esq. Lyon/Lota, Edificio Paris (Providencia) | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; Dom sin atención |
| Toma de Muestras San Bernardo | O´Higgins n° 337 | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; **Dom 08:30–13:00** |
| Toma de Muestras Santa Lucía | Miraflores 156, Santiago Centro | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; Dom sin atención |
| Toma de Muestras Tobalaba | Av. Luis Thayer Ojeda 082, Providencia | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; **Dom 08:30–13:00** |
| Visión Metro Los Leones | Av. Ricardo Lyon 190, Providencia | Evaluación Cirugía Lasik | L–V 9:00–18:30; Sáb 09:00–12:30; Dom sin atención |
| Visión Metro Santa Lucía | Miraflores 156, Santiago Centro | Evaluación Cirugía Lasik | L–V 9:00–18:30; Sáb 09:00–12:30; Dom sin atención |

Tobalaba has both a diagnostic centre (073) and a toma de muestras (082).

"Exámenes de larga duración" (long tests, e.g. curves) have shorter windows at every toma de muestras; check the branch's "Ver horarios".

## Other regions (6)
| Región | Sede | Dirección | Servicios | Horario |
|---|---|---|---|---|
| Valparaíso | Centro de Salud Quinta Vergara (Viña del Mar) | Errázuriz 690, Viña del Mar (frente a Quinta Vergara) | Imagenología | Lu, Ma, Mi, Ju 08:45–19:30; Vi 08:45–17:00 |
| Antofagasta | Visión Antofagasta | Sucre 244, 2do piso de Diagno Salud | Evaluación Cirugía Lasik | L–V 9:00–19:00; Sáb 09:00–13:00 |
| Araucanía | Toma de Muestras Temuco | Av. Alemania 999, Temuco | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; Dom 08:00–12:00 (the site prints "080:00") |
| Araucanía | Visión Temuco | Avenida Alemania 999, Edificio Paseo de las Artes | Evaluación Cirugía Lasik | L–V 9:00–18:30; Sáb 09:00–12:30 |
| Ñuble | Toma de Muestras Chillán | Constitución 796, piso 5, Chillán | Toma de Muestras | L–V 7:30–16:00; Sáb 08:00–13:00; Dom sin atención |
| O'Higgins | Toma de Muestras Rancagua | Sargento José Bernardo - C. Cuevas 483, Rancagua | Toma de Muestras | L–V 7:00–15:00; Sáb 07:30–14:00; Dom sin atención |

## Quick answers
- **Open on Sunday**: Metro Tobalaba (imaging, 09:00–20:30), Astra La Florida, and the tomas de muestras at Astra Alameda, Astra Maipú, Buin, Mall Florida, San Bernardo, Tobalaba and Temuco. /laboratorio, section "Realiza tus muestras ahora también los Domingos": "domingos de 09:00 a 13:00 hrs" at Metro Moneda, Metro Tobalaba, Maipú, San Bernardo, Mall Cenco La Florida.
- **LASIK evaluation**: Metro Tobalaba, Visión Metro Los Leones, Visión Metro Santa Lucía, Visión Antofagasta, Visión Temuco. On /cirugia-lasik the section "📍 Estamos cerca de ti" has tabs Región Metropolitana / Región Antofagasta / Región de la Araucanía. The LASIK form's Ubicación options are "Santiago - LTO" (Metro Tobalaba), "Santiago - Lyon" (Los Leones), "Santiago - Metro Santa Lucía", "Antofagasta", "Temuco".
- **Consultas médicas**: Astra Alameda, La Florida, Maipú, San Miguel, Salvador (booked in Reservo, see topic `agendar`).
- **Kinesiología**: Astra La Florida, Maipú, San Miguel, Salvador.
- **Imaging outside Santiago**: Viña del Mar only (and Quillota, see below). Resonancia on agenda-web exists for regions 5 (Valparaíso) and 13 (RM).
- Nearest metro, from /resored "Presencia en toda la Capital.": Tobalaba (Luis Thayer Ojeda 073), Salvador (Av. Salvador 283), Moneda (O'Higgins 1529), Santiago Bueras (Maipú), Bellavista La Florida (Vicuña Mackenna Pte 7255).

## Clínica Astra is now CLINI
/astra/clinica-astra-evoluciona-centros-medicos-fonasa-nivel-1: "NO ES UN CAMBIO, ¡ES UNA EVOLUCIÓN! ¡AHORA SOMOS PARTE DE CLINI SALUD!" — "Ahora somos 100% Fonasa Nivel 1"; same centres; "Mismos doctores y especialistas de siempre"; new services (Cirugía Lasik with free pre-operative evaluation, imaging incl. PET-CT, oncoginecología, traumatología, neurología, cardiología, test de esfuerzo, kinesiología y medicina deportiva). FAQs: "¿Qué pasó con Clínica Astra?", "¿Continuarán los servicios de Astra?" (yes, now booked through CLINI), "¿Todos los centros ahora son CLINI?" ("Se adicionan 5 nuevas tomas de muestras y 4 centros de cirugía lasik"), "¿Cómo puedo agendar?" (www.clini.cl, 22 994 4003, WhatsApp +569 8246 3202 o +569 9489 0594).

## Viña del Mar (Quinta Vergara)
/centro-de-salud/vina-del-mar: "¡YA LLEGAMOS VIÑA DEL MAR!". Resonancia Magnética $54.990* (convenio Caja Los Héroes, Caja 18, Caja La Araucana and Plataforma Starbien, Fonasa B-C-D with orden médica, until 31-12-2026); Tomografías desde $13.380; Radiografías Digitales desde $4.990; Toma de muestras "¡Pronto!". Price table "Conoce nuestros precios" (e.g. Resonancia de rodilla $54.990 convenio / $88.280 copago Fonasa / $176.560 particular). "Convenio de Caja Los Andes no se encuentra disponible en sucursales de CLINI Viña del Mar (Quinta Vergara) y CLINI Quillota (Centro Oxígeno)." FAQ: an orden médica is required for RM, TAC and radiografías there.
Quillota: /resored shows "¡NUEVA SUCURSAL! Quillota, Av. Ariztía 1415, Lun a Vie 08:30–19:30"; /imagenes/resonancia-magnetica-fonasa-nivel-1-e-isapre-en-quillota is its RM page. Quillota is not on /ubicaciones.

## Where the site disagrees with itself
- How many sedes: 20 on /ubicaciones; "más de 18" (/ahorra-fonasa-1); "más de 16" (convenio pages); "15 puntos de atención" (Astra page).
- Metro Salvador hours: /ubicaciones says centro L–V 07:30–20:00, Dom sin atención; /resored says L–V 08:00–21:00, S 08:00–20:30. Metro Tobalaba toma de muestras: /ubicaciones "Luis Thayer Ojeda 082"; /laboratorio "Luis Thayer Ojeda 085".
- Viña del Mar: meta description says "Resonancias magnéticas desde $59.990"; the page body says $54.990*.
