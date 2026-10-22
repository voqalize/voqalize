# Ecografías (generales, ginecológicas y obstétricas)

Sources: https://www.clini.cl/imagenes/ecografia-fonasa-nivel-1 (sections "Ecografías", "Todas las ecografías que necesites están en CLINI", "Precios de exámenes de Ecografía", "¿Por qué elegir CLINI para tu ecografía?", "Preguntas frecuentes", "Así de sencillo es el proceso"); https://www.clini.cl/agendamiento-imagenes (card "Ecografías", menu "Reservar hora": Ecografías / Ecografías Ginecológicas); https://www.clini.cl/ (hero slide "SOMOS FONASA NIVEL 1 EN TODAS LAS ECOGRAFÍAS"); https://www.clini.cl/imagenes (section "Precios de exámenes de imagenología"); cotizador catalogue (L3/prices.json, servicios ECO and ECOGINE); agenda-web.clini.cl servicios 81 and 82.

## What the site says
- Page /imagenes/ecografia-fonasa-nivel-1, h1 "Ecografías", "Precio Fonasa nivel 1 en Santiago": ultrasound exams; prices vary by type and previsión. Hero **"VALOR FONASA DESDE $6.990"** ("COPAGO PROMEDIO CON BONIFICACIÓN DE CONVENIOS VIGENTES"; "Otros centros: $16.860"), "20 min DURACIÓN", "24/7 AGENDA".
- Home hero slide: "SOMOS FONASA NIVEL 1 EN TODAS LAS ECOGRAFÍAS — ¡Agenda una hora!" → agenda-web servicio 81.
- Every "Reserva tu hora" / "Reservar ecografía" button on the page is a dropdown with two choices: **Ecografías** (general, servicio 81) and **Ecografías Ginecológicas** (servicio 82). Open it and point at the right one.

## Cards (section "Todas las ecografías que necesites están en CLINI")
- **Ecografías Generales** — órganos internos, tiroides, mamas, musculoesquelético. "FONASA desde $6.990".
- **Ecografías Ginecológicas** — control ginecológico preventivo y seguimiento del embarazo; transvaginales y doppler. "FONASA desde $7.700".
- **Ecografía doppler** — flujo sanguíneo en arterias y venas (várices, trombosis). "FONASA desde $31.520".
- **Ecografía del corazón** — "Realizado por cardiólogos especialistas", "FONASA desde $30.000". That is the ecocardiograma (topic `cardiologia`).

## Price table (section "Precios de exámenes de Ecografía"), Copago Fonasa / Particular
Ecografía prostática $7.660 / $16.860; abdomen y pelvis masculina $21.440 / $47.780; pierna $9.600 / $21.130; pared abdominal $9.600 / $21.130; pelvis femenina $7.330 / $16.130; axilar $9.600 / $21.130; renal $9.550 / $21.020; testicular $9.480 / $20.860; inguinal $9.600 / $21.130; mano $9.600 / $21.130; mamaria $9.600 / $21.130; transvaginal $7.700 / $16.940; partes blandas $9.600 / $21.130; abdominal $13.780 / $30.320; tiroides $9.600 / $21.130.

Cotizador (live via `quote_price`), Fonasa / particular: Ecografía abdominal $13.780 / $27.570; mamaria $9.600 / $19.210; tiroides (incluye doppler) $9.600 / $19.210; doppler abdominal $32.480 / $64.960; rodilla (partes blandas) $9.600 / $19.210. Ginecológicas: Ecografía obstétrica $7.330 / $14.410; pelviana femenina transabdominal $7.330 / $14.670; transvaginal $7.700 / $15.400; doppler ginecológico transvaginal $32.480 / $64.960; doppler obstétrica vasos placentarios 11–14 semanas and 20–24 semanas $31.520 / $63.040; **Ecografía 3D, 4D, 5D: particular $49.000** (no Fonasa price).

## Preparation (cotizador `preparacion`, quote the item's own)
- Most general ecografías: "Sin preparación especial."
- Abdominal-type: "Mantener ayuno de al menos 6 horas antes del examen. Puede beber pequeñas cantidades de agua sin gas hasta 3 horas antes. Evite chicle, cigarrillos y bebidas gaseosas…"; some list a full ayuno of 6 h (diabéticos mínimo 4 h; eco pediátrica 0–4 años 3 h).
- Pélvica/vesical: "Debe ingerir abundante agua y retener orina de al menos 1 hora 30 minutos" (with a note for patients with sonda).
- Mamaria/axilar: "Sin preparación especial. Evite aplicar desodorante, antitranspirante, cremas, talcos o perfumes en axilas y mamas el día del examen."
- Transvaginal: no preparation; "es necesario haber iniciado relaciones sexuales"; evacuar la vejiga antes. Obstétrica: "Llevar carnet de control de embarazo."
- Page FAQ "¿Cómo me preparo para la ecografía?": "Algunas requieren ayuno, otras vejiga llena y otras no necesitan preparación especial. Al momento de reservar te indicaremos las instrucciones exactas."

## FAQs (section "Preguntas frecuentes")
- "¿Necesito derivación médica para hacerme una ecografía?" — sí, orden médica vigente no mayor a 6 meses (Fonasa needs it to sell the bono; Isapre reembolso).
- "¿Cuánto tiempo tarda en llegar el informe?" — 24 a 48 horas, by email.
- "¿CLINI atiende pacientes con alergia al látex?" — no ("no dispone de un ambiente clínico completamente libre de este material").
- "¿Qué incluye el precio?" — the exam, equipment and informe; no hidden charges.
- "¿Puedo usar Fonasa?" — sí, tramos B, C y D.
- "¿Puedo cancelar o cambiar mi cita?" — contact the team in advance.

## Where
agenda-web region for ecografías: 13 (Región Metropolitana) only. Sedes with Imagenología: Metro Tobalaba, Astra Salvador, Astra Alameda, Astra La Florida, Astra Maipú, Astra San Miguel (`find_branch`). Viña del Mar (Quinta Vergara) lists RM, TAC and radiografías, not ecografías. The ecoginecología booking has an extra centre-mode switch on agenda-web.

## Booking
- General: agenda-web servicio **81** (Ecografía): `https://agenda-web.clini.cl/?servicio=81&prestacion=P` — 60 Mamaria, 67 Abdominal, 62 Pélvica, 63 Doppler, 64 Musculoesquelética, 66 Tiroides/Renal, 65 Otras.
- Ginecológica/obstétrica: servicio **82** (Ecoginecología): 43 4D y 5D, 44 Doppler 11–14 semanas, 45 Doppler 20–24 semanas, 99 Doppler ginecológico, 42 Ginecológica, 100 Obstétrica. (Old codes 68 and 80 exist on agenda-web but the site doesn't link them.)
- Ecografía mamaria is also part of the breast pack in the October campaign (topic `mamografia`).

## Where the site disagrees with itself
- "Desde": $6.990 (this page, with convenio), $7.660 (/agendamiento-imagenes and the home tab "Ecografías Desde: $7.660"), $7.330 (cheapest Fonasa item in the cotizador, pelvis femenina / obstétrica). Say "desde unos siete mil pesos con Fonasa" only with the page you are on, or quote the exact exam.
- Particular prices differ between the page table and the cotizador (abdominal $30.320 vs $27.570; mamaria $21.130 vs $19.210 — /imagenes says $19.210; transvaginal $16.940 vs $15.400). Prefer the cotizador and say prices can change.
- Ecografía abdomen y pelvis masculina: $21.440 on the page, $21.110 in the cotizador.
