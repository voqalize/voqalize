# Resonancia magnética (RM / MRI)

Sources: https://www.clini.cl/imagenes/resonancias-fonasa-1 (sections "Resonancia Magnética", "Encuentra la resonancia que necesitas", "Así de sencillo es el proceso", "Precios de la Resonancia Magnética", "¡Hola, Viña del Mar!", "¿Por qué elegir CLINI para tu Resonancia Magnética?", "Preguntas frecuentes"); https://www.clini.cl/imagenes/resonancias-magneticas/rodilla, /cerebro, /encefalo-cerebro, /columna-lumbar, /columna-total, /cuello, /silla-turca, /oidos, /cavidades-perinasales, /parrilla-costal; https://www.clini.cl/imagenes/resonancia-magnetica-fonasa-nivel-1-e-isapre-en-quillota (sections "Resonancia Magnética en Quillota", "Dónde realizar una Resonancia en Quillota", "¿Cuánto cuesta una resonancia magnética en Quillota?"); https://www.clini.cl/resored (section "RESORED", "Cotiza tu examen al instante."); https://www.clini.cl/imagenes (section "Resonancias magnéticas $54.990"); cotizador catalogue (L3/prices.json, servicio RM); agenda-web.clini.cl servicio 64.

## What the site says
- Main page: /imagenes/resonancias-fonasa-1, h1 "Resonancia Magnética", "Valor Fonasa nivel 1 en Región Metropolitana". Headline **"VALOR FONASA DESDE $54.990"**, small print "COPAGO PROMEDIO CON BONIFICACIÓN DE CONVENIOS VIGENTES" ("Otros centros: $190.000"); "+100.000 PACIENTES", "20MIN DURACIÓN".
- The $54.990 is **Fonasa (tramos B, C, D) + bonificación de convenio** (cajas de compensación and other convenios). Without a convenio the page says "desde $88.280 solo Fonasa" (section "Así de sencillo es el proceso": "Copago desde $54.990 Fonasa + bonificación de convenio | desde $88.280 solo Fonasa"). Always say "desde" and name the condition.
- Body-part pages (each "COPAGO FONASA + BONIFICACIÓN CONVENIOS $54.990*") list which convenios: "FONASA B,C y D + Caja Los Andes, Caja Los Héroes y Caja La Araucana", and more discounts with Sermecoop, Serviunión, Municipalidad de Puente Alto, Municipalidad de Ñuñoa, Bienestar Pudahuel, Aramark (see topic `fonasa-isapre-convenios`).
- "Equipos con inteligencia artificial integrada en el resonador de Metro Tobalaba y Alameda". Results: "Informe médico en 24-48h en tu email".
- The page also has a call-back form "Solicita una hora para tu Resonancia" (Nombre completo, No. Documento, Número teléfono, Correo, Previsión, "Adjunta tu orden" up to 10 MB): "Te contactaremos en menos de 24 horas hábiles desde el 600 023 1207." Javier never submits it; the visitor does.

## Price table (section "Precios de la Resonancia Magnética")
| Examen | Fonasa + Convenio Cajas | Copago Fonasa | Precio particular |
|---|---|---|---|
| RM de abdomen y pelvis | $54.990 | $161.490 | $322.990 |
| RM de silla turca | $54.990 | $112.210 | $224.330 |
| RM de cadera | $54.990 | $90.320 | $180.650 |
| RM de mama | $54.990 | $88.280 | $176.560 |
| RM de hombro | $54.990 | $88.280 | $176.560 |
| RM columna dorsal | $54.990 | $111.980 | $223.960 |
| RM columna lumbar | $54.990 | $107.670 | $215.350 |
| RM de rodilla | $54.990 | $88.280 | $176.560 |

Cotizador (live API; offline copy in L3/prices.json), Fonasa / particular: RM rodilla (unilateral) $88.280 / $176.560; ambas rodillas $176.560 / $353.120; columna lumbar $107.670 / $215.350; columna total $190.520 / $381.050; cerebro o encéfalo $107.670 / $215.350; hombro $88.280 / $176.560; cadera (unilateral) $91.920 / $183.850; abdomen y pelvis $161.490 / $322.990 (con contraste). 68 RM items in the catalogue. Prefer `quote_price` for any specific exam.

## Body-part pages (each: "¿Necesitas una resonancia de …?", "Todas las Resonancias Magnéticas con copago a $54.990 gracias a bonificaciones especiales por convenios asociados", "¿Por qué elegir CLINI para tu resonancia de …?", "Preguntas Frecuentes", "Agenda tu resonancia … hoy")
- /imagenes/resonancias-magneticas/rodilla — "Resonancia Magnética de Rodilla" (dolor, lesiones deportivas).
- /…/columna-lumbar — "Resonancia Magnética de Columna Lumbar" (dolor lumbar, ciática, hernia de disco).
- /…/columna-total — "Resonancia Magnética de Columna Total" (cervical, dorsal y lumbar).
- /…/cerebro — "Resonancia Magnética de Cerebro"; /…/encefalo-cerebro — "Resonancia Magnética de Encéfalo (Cerebro)".
- /…/cuello — "Resonancia Magnética de Cuello"; /…/silla-turca — "Resonancia Magnética de Silla Turca" (hipófisis).
- /…/oidos — "Resonancia Magnética de Oídos"; /…/cavidades-perinasales — "Resonancia Magnética de Cavidades Perinasales" (senos paranasales); /…/parrilla-costal — "Resonancia Magnética de Parrilla Costal".
- Their FAQs (dropdowns): "¿Necesito orden o derivación médica?" (yes, normally; "si aún no cuentas con derivación, en CLINI Salud ofrecemos consultas médicas desde $4.750"); "¿Cuáles son los medios de pago?" (efectivo or tarjetas); "¿Cuánto dura el examen y cuándo recibiré los resultados?" (20 a 30 minutos; informe 24 a 48 horas); "¿Debo prepararme antes del examen?" (evitar objetos metálicos, llegar con anticipación, avisar si tienes implantes o estás embarazada); "¿La resonancia magnética duele o es invasiva?" (No: indolora y no invasiva).
- The main page's "Encuentra la resonancia que necesitas" cards link six of these: rodilla, columna lumbar, cerebro, cuello, columna total, silla turca.

## FAQs on /imagenes/resonancias-fonasa-1 (section "Preguntas frecuentes"; a custom accordion, not a Webflow dropdown)
- Orden médica: yes, "vigente, con una antigüedad no mayor a 6 meses"; Fonasa needs it for coverage; Isapre for reembolso.
- Resultado: "entre 24 y 48 horas".
- Preparación: depends on the exam and whether it has medio de contraste; "Al momento de reservar te indicaremos las instrucciones específicas".
- Duración: "entre 20 y 45 minutos" in general.
- Valor incluye: the exam and the informe médico; contraste or extra insumos per the conditions when booking.
- Implantes / dispositivos metálicos: must inform (marcapasos, implantes, prótesis, clips quirúrgicos…); the clinical team decides.
- Cancelar o cambiar: contact the team in advance.

## Contraste and preparation (cotizador `preparacion`)
- Most RM: "No requiere preparación especial. Sin embargo, si la orden médica indica que el examen es con contraste, se debe realizar ayuno total de 2 horas antes del procedimiento."
- Some RM say "Requiere 2 horas de ayuno total" (14 items), a few 6 or 8 horas. Items marked con contraste in the catalogue include abdomen y pelvis, mamaria, pelvis blanda, pelvis por endometriosis, oídos, órbitas, plexo lumbar. Read the item's preparation from `quote_price`; never add your own.

## ResoRed (/resored)
"RESORED — $54.990* COPAGO ASOCIADO A BONIFICACIONES ESPECIALES", "resonancia de solo 20 minutos gracias a nuestro sistema con Inteligencia Artificial", "CENTRO TOBALABA"; "3 y 6 CUOTAS SIN INTERÉS", "5 SUCURSALES EN RM". Section "Cotiza tu examen al instante." lists ~20 RM at $54.990 with convenio (particular $150.000–$176.560). It has a call-back form. Details in topic `fonasa-isapre-convenios`.

## Where: sedes and regions
- agenda-web regions for RM: 13 Región Metropolitana (default) and 5 Valparaíso. Sedes with imaging (/ubicaciones): Metro Tobalaba (Luis Thayer Ojeda 073, Providencia), Astra Salvador, Astra Alameda, Astra La Florida, Astra Maipú, Astra San Miguel, and Quinta Vergara in Viña del Mar (RM, TAC, radiografías; see topic `imagenologia`).
- **Quillota** (/imagenes/resonancia-magnetica-fonasa-nivel-1-e-isapre-en-quillota, "Resonancia Magnética en Quillota"): "Rafael Ariztía 1465, La Palma, Quillota, Valparaíso. Oxígeno centro médico", Lunes a Viernes 8:00–20:00, tel 22 994 4003. "VALOR FONASA + CONVENIO DESDE $54.990*", "PARTICULAR: $120.000". Fine print: price under a convenio with "Plataforma Starbien" until 31-12-2026, for FONASA B, C, D with orden médica vigente, booked through Clini's channels. Not in /ubicaciones.

## Booking
- Online: agenda-web servicio **64** (Resonancia): `https://agenda-web.clini.cl/?servicio=64&prestacion=P` (with a prestación it searches automatically). Prestaciones: 804 RM Rodilla, Cadera, Hombro, Mano, Muñeca; 81 RM Columna Cervical o Dorsal o Lumbar; 800 RM Cerebro/Cabeza; 801 RM Cuello; 803 RM Pelvis; 802 RM Abdomen; 805 RM Pierna, Brazo, Antebrazo; 83 RM Abdomen y Pelvis; 82 RM Columna Total; 806 RM Ambas Rodillas, Caderas, Hombros, Manos, Muñecas; 807 RM Ambas Piernas, Brazos, Antebrazos; 808 RM Columna Total con Contraste; 86 Otras RM. Match the order (e.g. "resonancia de rodilla" → 804; silla turca, oídos, cavidades perinasales → 800 Cerebro/Cabeza or 86 Otras RM if unsure, and say so).
- Phone 22 994 4003; WhatsApp agendamiento asistido.
- Bring orden médica (≤ 6 meses) and cédula de identidad.

## Where the site disagrees with itself
- "Desde $54.990" (Fonasa + convenio) vs "desde $88.280 solo Fonasa" on the same page; the cotizador's cheapest RM Fonasa copago is $72.120. Say "desde $54.990 con convenio" and give the exam's own Fonasa price.
- RM de abdomen y pelvis: $161.490 Fonasa in the table, yet "$54.990" with convenio.
- Particular price: Quillota page says "PARTICULAR: $120.000" in the hero and "desde $150.000" in its price section; ResoRed lists $150.000 for many; the tables show $176.560+.
- Viña del Mar page meta says "Resonancias magnéticas desde $59.990" while its body says $54.990*.
- The h1 kicker reads "Resonancias Manéticas" (typo, as rendered).
