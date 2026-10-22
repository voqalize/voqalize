# Radiografías (rayos X)

Sources: https://www.clini.cl/imagenes/radiografias-fonasa-nivel-1 (sections "Realiza tu Radiografía en CLINI - Fonasa Nivel 1", "¿Qué es una radiografía y para qué sirve?", "Solicita una hora para tu Tomografía (TAC):", "¿Vas a realizarte una Radiografía?", "Precios de Radiografías", "¡Hola, Viña del Mar!", "Clini: Tu salud en manos expertas", "¿Cuánto tiempo tarda en realizarse una Radiografía?"); https://www.clini.cl/centro-de-salud/vina-del-mar (section "Conoce nuestros precios", "Conoce Nuestros Servicios"); https://www.clini.cl/agendamiento-imagenes (card "Radiografías Desde: $5.520"); cotizador catalogue (L3/prices.json, servicio RX); agenda-web.clini.cl servicio 57.

## What the site says
- Page /imagenes/radiografias-fonasa-nivel-1, h1 "Realiza tu Radiografía en CLINI - Fonasa Nivel 1": radiografías "con cobertura Fonasa Nivel 1. Al mejor precio". Buttons "Reserva tu hora", 22 994 4003, "Resultados de imágenes"; call center L–V 08:00–22:00, Sáb 08:00–20:00, Dom 14:00–22:00.
- "¿Qué es una radiografía y para qué sirve?": uses rayos X for images of bones, joints and soft tissue; lists fracturas y lesiones óseas, problemas pulmonares, condiciones oncológicas, alteraciones articulares.
- "¿Vas a realizarte una Radiografía?": **"Recuerda llevar tu orden médica. Si tu radiografía es de abdomen simple, renal, vesical simple o sacro coxis, sigue un régimen blando 24 horas antes (té, sopas, pollo cocido, galletas de soda, jugos naturales), evita lácteos, gaseosas, masas y carne, y asiste en ayunas."** Then "Radiografías disponibles en Clini": columna (lumbar, cervical o total), tórax, Cavum (nasofaringe), extremidades (manos, pies, rodillas, caderas).
- "¿Cuánto tiempo tarda en realizarse una Radiografía?": "duración promedio de 10 a 20 minutos".
- "Clini: Tu salud en manos expertas": "Clínica Astra evoluciona y ahora es parte de Clini"; "5 puntos estratégicos en la Región Metropolitana para tu radiología".
- The page's form is headed "Solicita una hora para tu Tomografía (TAC):" (form `#wf-form-FORMULARIO-TAC`, with orden upload) although it is the radiografía page — a call-back request; the visitor submits it.

## Prices
- Table "Precios de Radiografías", Copago Fonasa / Particular: Radiografía Columna dorsal $6.430 / $12.870; **Radiografía de Tórax $5.520 / $11.050**; Radiografía de cráneo $5.730 / $11.470; Radiografía Columna Lumbar $6.430 / $12.870.
- "Desde $5.520" on /agendamiento-imagenes and the home "Imágenes" tab (= RX tórax simple).
- Cotizador (53 RX items, live via `quote_price`): RX tórax simple (frontal o lateral) $5.520 / $11.050; RX tórax (frontal y lateral) $9.960 / $19.930; RX rodilla (frontal y lateral) $5.700 / $11.400; RX ambas rodillas $11.400 / $22.800; RX pelvis, cadera o coxofemoral $4.230 / $8.080; RX columna lumbar o lumbosacra $9.520 / $19.050; RX columna total panorámica $14.240 / $28.500; cheapest item $3.860 (proyecciones especiales de cadera o pelvis).
- Preparation (cotizador): almost all "Sin preparación especial"; one item "Ayuno de 6 hrs". The page's régimen blando + ayuno rule applies to abdomen simple, renal, vesical simple and sacro coxis.

## Where
- agenda-web regions for radiografía: 13 RM (default) and 5 Valparaíso.
- Viña del Mar, Centro de Salud Quinta Vergara (Errázuriz 690, frente a Quinta Vergara; L, M, Mi y J 08:45–19:30, V 08:45–17:00): "Radiografías Digitales Desde $4.990"; its table: Radiografía Columna Dorsal $6.430 / $12.870, Tórax $5.520 / $11.050, Extremidad $4.820 / $10.600 (Fonasa + Convenio "No aplica").
- RM sedes on the page's carousel: Providencia Metro Tobalaba (Av. Luis Thayer Ojeda 073), Providencia Metro Salvador (Av. Salvador 283), Santiago Centro (Av. Libertador Bernardo O'Higgins 1529), Maipú (Av. Pajaritos 2624, local 32), La Florida (Av. Vicuña Mackenna Poniente 7255). Hours: `find_branch`.

## Booking
- agenda-web servicio **57** (Radiografía): `https://agenda-web.clini.cl/?servicio=57&prestacion=P` — **70 Radiografía General**, **72 Radiografía Proyecciones**. A single standard view (tórax, rodilla) → 70; extra/special projections on the order → 72; if unsure say so.
- Legacy `agenda-imagenes.clini.cl/…?RADIOGRAFIA=…` redirects to servicio 57. Phone 22 994 4003.

## Where the site disagrees with itself
- "Desde": $5.520 (/agendamiento-imagenes, home), $4.990 (Viña del Mar page and meta), and the cotizador's cheapest $3.860.
- The Viña del Mar card describes "Radiografías Digitales" with the resonancia text ("campo magnético potente y ondas de radio") — a copy slip on the site; don't repeat it.
- The form on the radiografía page is titled for "Tomografía (TAC)".
