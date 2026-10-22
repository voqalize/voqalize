# Scanner / TAC (tomografía computarizada)

Sources: https://www.clini.cl/imagenes/realiza-tu-examen-tac-scanner-fonasa-nivel-1 (sections "Tomografía Computarizada (TAC)", "Encuentra la Tomografía que necesitas", "¿Qué es la Tomografía Computarizada (TAC)?", "Precios de Tomografía Computarizada (TAC)", "¡Hola, Viña del Mar!", "Así de sencillo es el proceso", "Preguntas frecuentes"); https://www.clini.cl/imagenes (section "Precios de exámenes de imagenología"); https://www.clini.cl/centro-de-salud/vina-del-mar (section "Conoce nuestros precios"); cotizador catalogue (L3/prices.json, servicio TAC) and its cart rules; agenda-web.clini.cl servicio 70.

## What the site says
- Page /imagenes/realiza-tu-examen-tac-scanner-fonasa-nivel-1, h1 "Tomografía Computarizada (TAC)", "Valor Fonasa nivel 1". Hero **"VALOR FONASA DESDE $13.380"**, "COPAGO PROMEDIO CON BONIFICACIÓN DE CONVENIOS VIGENTES", "Otros centros: $50.000", "+60.000 PACIENTES", "20MIN DURACIÓN". Nav label: "Tomografía (TAC/TC)". Visitors say "scanner", "TAC", "escáner", "tomografía" — the same exam.
- "¿Qué es la Tomografía Computarizada (TAC)?": combines rayos X with computer technology for cross-section images; "Examen rápido de 15 a 20 minutos", "Sin dolor ni procedimientos invasivos", "Resultados entregados en 24-48 horas hábiles", "Médicos radiólogos especialistas".
- Call-back form "Solicita una hora para tu Tomografía" (name, documento, phone, email, previsión, orden médica upload); "Te contactaremos en menos de 24 horas hábiles desde el 600 023 1207". The visitor submits, never Javier.

## Cards (section "Encuentra la Tomografía que necesitas")
Tomografía de Rodilla — Valor fonasa $27.880; Tomografía columna lumbar — $38.820; Tomografía de cerebro — $34.850; Tomografía de cuello — $32.740; Tomografía de columna cervical — $44.310; Tomografía de silla turca — $36.680.

## Price table (section "Precios de Tomografía Computarizada (TAC)"), Copago Fonasa / Precio particular
| Examen | Fonasa | Particular |
|---|---|---|
| Angiotac de cuello y cerebro | $76.950 | $153.920 |
| Angiotac de tórax | $63.600 | $127.200 |
| Angiotac de abdomen | $58.800 | $117.770 |
| TAC de escápula | $51.720 | $103.440 |
| TAC de abdomen y pelvis | $50.820 | $101.650 |
| TAC columna cervical completa | $43.540 | $95.790 |
| TAC columna lumbar completa | $38.820 | $77.650 |
| TAC de pelvis | $31.930 | $63.870 |
| TAC cerebro | $34.850 | $69.710 |
| TAC de hombro | $27.880 | $55.760 |
| TAC abdomen | $31.140 | $62.280 |
| Pielotac | $13.380 | $26.770 |
| TAC de rodilla | $27.880 | $55.760 |
| TAC de tórax | $51.720 | $103.440 |

The cheapest, the "desde $13.380", is the **Pielotac** (pielografía TAC). The cotizador has 61 TAC items; e.g. TAC tórax $51.720 / $103.440, TAC cerebro $34.850 / $69.710, TAC columna lumbar $38.820 / $77.650, TAC abdomen y pelvis $50.820 / $101.650 (con contraste), most extremidades unilateral $27.880 / $55.760, bilateral $55.760 / $111.520. Use `quote_price` for a specific exam.

## Contraste and preparation
- Cotizador `preparacion` for most TAC: "No requiere preparación especial. Sin embargo, si la orden médica indica que el examen es con contraste, se debe realizar ayuno total de 6 horas antes del procedimiento." Others: "Requiere 6 horas de ayuno total" (angiotac, abdomen y pelvis and similar con contraste).
- The cotizador's cart rules: the contrast medium for a TAC costs extra (about $35.000–$50.000), paid privately (research note on `handler=ReglasCarrito`; say "puede tener un costo adicional por el contraste" and suggest confirming when booking).
- Page FAQs (section "Preguntas frecuentes", custom accordion): orden médica vigente ≤ 6 meses; informe 24–48 h; preparation depends on exam and contraste, "Al momento de reservar te informaremos la preparación"; "¿Necesito ayuno para una tomografía computarizada con contraste?" — some do; "¿Qué debo informar antes de realizarme un TAC con contraste?" — antecedentes, medicamentos, reacciones previas a medios de contraste; TAC vs resonancia: TAC uses rayos X, RM a campo magnético y ondas de radio, the right one depends on the doctor's order; change or cancel by contacting the team in advance.
- Javier quotes these; he does not decide whether someone needs contraste — the orden médica does.

## Where
- agenda-web regions for TAC: 13 RM (default) and 5 Valparaíso. The page's "¡Hola, Viña del Mar!" block lists Quinta Vergara (Errázuriz 690, Viña del Mar, L, M, Mi y J 08:45–19:30, V 08:45–17:00), Providencia Metro Tobalaba (Av. Luis Thayer Ojeda 073), Santiago Centro (Av. Libertador Bernardo O'Higgins 1529, Metro Moneda), La Florida (Av. Vicuña Mackenna Poniente 7255). Full list with hours: `find_branch`.
- Viña del Mar convenio prices (/centro-de-salud/vina-del-mar, "Conoce nuestros precios"): TAC Pielotac $13.380; TAC Tórax, Abdomen y Pelvis, Cerebro, Columna Lumbar Completa **$29.990 Fonasa + Convenio** (vs $51.720 / $50.820 / $34.850 / $38.820 Fonasa).

## Booking
- agenda-web servicio **70** (Scanner): `https://agenda-web.clini.cl/?servicio=70&prestacion=P`. Prestaciones: 94 Angio TAC; 90 TAC cerebro/cabeza/cuello; 91 TAC columna; 93 TAC extremidades; 92 TAC tórax/abdomen/pelvis; 95 Otros TAC. Pielotac → 92 (abdomen/pelvis) or 95 Otros TAC if unsure — say so.
- Legacy link `agenda-imagenes.clini.cl/…?SCANNER=…` redirects to servicio 70. Phone 22 994 4003.

## Where the site disagrees with itself
- Hero "desde $13.380" is labelled "copago promedio con bonificación de convenios", but $13.380 is also the plain Fonasa copago of the Pielotac in the tables.
- "TAC de rodilla $27880" is printed without the thousands dot.
- Duration: "15 a 20 minutos" ("¿Qué es la TAC?"), "20MIN" (hero), "20–30 minutos" ("Así de sencillo es el proceso").
- TAC columna cervical: card "$44.310", table "TAC columna cervical completa $43.540".
