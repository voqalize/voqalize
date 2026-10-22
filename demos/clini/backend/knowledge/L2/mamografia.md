# Mamografía

Sources: https://www.clini.cl/imagenes/realiza-tu-mamografia-con-fonasa-en-clini (sections "Realiza tu Mamografía Fonasa 1 en CLINI desde $11.750", "¿Qué es una mamografía y para qué sirve?", "¿Cuándo se debe realizar este examen?", "¿Es dolorosa una mamografía?", "Precios de la Mamografía", "¿Por qué elegir Clini para realizar tu resonancia?"); https://www.clini.cl/campanas/octubre (sections "LA DECISIÓN QUE VAS A TOMAR HOY LO PUEDE CAMBIAR TODO", "AGENDA", "¿ES PARA TU MAMÁ?", "¿LLEGÓ EL DÍA DE TU EXAMEN?"); https://www.clini.cl/agendamiento-imagenes (card "Mamografías Desde: $11.750"); https://www.clini.cl/ (home slider, breast-cancer campaign); cotizador catalogue (L3/prices.json, servicio MAMO); agenda-web.clini.cl servicio 65.

## What the site says
- Page /imagenes/realiza-tu-mamografia-con-fonasa-en-clini (old alias /imagenes/mamografia redirects here). h1 **"Realiza tu Mamografía Fonasa 1 en CLINI desde $11.750"**; buttons "Reserva tu hora", phone 22 994 4003, "Resultados de imágenes".
- "¿Qué es una mamografía y para qué sirve?": an X-ray image of the breasts; specialists use it to look for early signs of breast cancer. "Mamografía bilateral" = both breasts, which is what doctors usually order. Low radiation dose ("¿Es peligroso realizarse este examen?").
- "¿Cuándo se debe realizar este examen?": the site recommends the first mamografía "entre los 35 y 40 años", if there is no family history or risk and no symptoms; with risk factors the specialist may order it earlier. Quote this as the site's statement; anything personal → their doctor.
- "¿Es dolorosa una mamografía?": pressure is applied, some find it uncomfortable or painful, it lasts minutes; the whole procedure "no tarda más de 15 minutos".
- Equipment: "el nuevo Siemens Mammomat Revelation 3D" (section "¿Por qué elegir Clini para realizar tu resonancia?" — the heading says resonancia on the mamografía page).
- Links to the indicaciones page ("Conocer indicaciones") and "SALUD MUJER en Clini" (topic `mujer`).

## Prices
- Page table "Precios de la Mamografía": Ecografía mamaria – complementaria $9.600 Fonasa / $19.210 particular; **Mamografía bilateral $11.750 / $23.500**.
- Cotizador: Mamografía bilateral $11.750 / $23.500; Mamografía bilateral (con prótesis) $11.750 / $23.500; Mamografía unilateral $6.900 / $13.800; Mamografía proyección complementaria $2.520 Fonasa. Ecografía mamaria $9.600 / $19.210.
- Preparation (cotizador, every mamografía item): "No requiere ayuno ni medicamentos previos. No aplicar desodorante, antitranspirante, cremas, talcos, aceites ni perfumes en las axilas ni en el pecho el día del examen."

## Octubre Rosa campaign (/campanas/octubre) — October 2026
Meta: "Mes de Sensibilización sobre el Cáncer de Mama". Section "LA DECISIÓN QUE VAS A TOMAR HOY LO PUEDE CAMBIAR TODO", "En Clini nos tomamos a pecho tu diagnóstico":
- FONASA B,C,D + CONVENIO: **Mamografía $10.000*** ("Precio referencial en convenio con bono").
- FONASA B,C,D: Ecografía Mamaria $9.600.
- FONASA B,C,D + CONVENIO: **Pack Mamografía + Ecografía mamaria $14.990***.
- FONASA A, PARTICULAR: Pack Mamografía + Ecografía mamaria $39.990.
- Steps (section "AGENDA"): 01 agenda online 24/7 or 22 994 4003, "Horas exclusivas para ti sábados y domingos de octubre"; 02 "NO OLVIDES TRAER TU ORDEN MÉDICA" ("¿No tienes orden? Pincha aquí"); 03 "Resultados en 48 horas en clini.cl/resultados".
- The page has a form `#wf-form-FORMULARIO-mamo-eco` (name, RUT, phone, email, previsión, orden upload) — the visitor submits it.
- It is a campaign landing: mention it during October; elsewhere quote the standard page.

## Where
agenda-web region for mamografía: **13 (Región Metropolitana) only**. Sedes with Imagenología in RM: Metro Tobalaba, Astra Salvador, Astra Alameda, Astra La Florida, Astra Maipú, Astra San Miguel (`find_branch`). Results: /resultados → Imagenología portal (topic `resultados`).

## Booking
- agenda-web servicio **65** (Mamografía): `https://agenda-web.clini.cl/?servicio=65&prestacion=P` — **401010 Mamografía Bilateral (4 exposiciones)**, **401110 Mamografía Unilateral (2 exposiciones)**. With prótesis: still bilateral (401010) per the cotizador name; suggest mentioning the implants when booking.
- Ecografía mamaria is booked separately: servicio 81, prestación 60 Mamaria (topic `ecografia`).
- Legacy `agenda-imagenes.clini.cl/…?MAMOGRAFIA=…` redirects to servicio 65. Phone 22 994 4003.
- Bring orden médica and cédula de identidad.

## Where the site disagrees with itself
- October campaign: mamografía "$10.000*" with convenio vs the standing $11.750 Fonasa price; pack $14.990 with convenio. Both are on the site; say which page.
- Particular: $23.500 (page, cotizador) vs the Fonasa A / particular pack $39.990 (includes the ecografía).
- The section heading "¿Por qué elegir Clini para realizar tu resonancia?" and its text "Si buscas realizarte una ecografía…" sit on the mamografía page (template copy).
