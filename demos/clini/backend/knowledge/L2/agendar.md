# Cómo agendar: agenda-web, Reservo, LASIK, teléfono y WhatsApp

Sources: https://www.clini.cl/agendamiento (sections "Agenda tus exámenes médicos en CLINI", "¡No olvides tu carnet de identidad!", "Preguntas Frecuentes:"); https://www.clini.cl/agendamiento-imagenes ("Agenda tu examen de imágenes en minutos"); https://www.clini.cl/agendamiento-cardiologia ("Agenda tu examen de cardiología en minutos"); https://www.clini.cl/agendamiento-consultas-medicas ("Agenda tu Consulta médica en minutos"); https://www.clini.cl/cirugia-lasik (section "¡Agenda tu evaluación gratuita!"); https://agenda-web.clini.cl/?servicio=N (the booking app; L3/agenda_services.json); https://agendamiento.reservo.cl (consultas); the header ("Horarios call center", "22 994 4003"); https://www.clini.cl/astra/clinica-astra-evoluciona-centros-medicos-fonasa-nivel-1 (FAQ "¿Cómo puedo agendar?"); https://cotizador-web.clini.cl/.

Booking is split by service across three systems. Pick by what the visitor wants:

| Quiere… | Dónde | Who finishes it |
|---|---|---|
| Laboratorio / toma de muestras, imágenes (RM, TAC, eco, mamo, RX, PET-CT), cardiología | **agenda-web.clini.cl** `?servicio=N[&prestacion=P]` | the visitor presses **AGENDAR** |
| Consultas médicas, kinesiología, matrona, psicología, nutricionista | **Reservo** (agendamiento.reservo.cl), new tab | the visitor, on Reservo |
| Cirugía LASIK: evaluación gratuita | lead form on **/cirugia-lasik** (section "¡Agenda tu evaluación gratuita!") | the visitor presses "¡Agendar evaluación!"; a coordinator calls back |
| Anything, by a person | call center **22 994 4003**, WhatsApp **+56 9 8246 3202** | CLINI |

## Hub pages on www.clini.cl
- **/agendamiento** — "Agenda tus exámenes médicos en CLINI": a "Filtra por servicio:" list (Imágenes, Cirugía Lasik, Laboratorio, Consultas Médicas, Cardiología, Kinesiología) of cards with "Reservar hora": Evaluación Cirugía Lasik, Tomas de muestra, Resonancias Magneticas, Ecografías, Tomografía (TAC), Ecografías Ginecológicas, Mamografías, PET-CT, Radiografías, Ecocardiograma, Electrocardiograma, Holter de Presión (MAPA), Holter de Ritmo, Evaluación kinesiologica, Traumatología, Medicina Deportiva, Medicina General, Medicina Interna, Cirugía General, Neurocirugía, Consulta Matrona. Then "¡No olvides tu carnet de identidad!": "por normativa debes presentar tu cédula de identidad física vigente" at the toma de muestras.
- **/agendamiento-imagenes** — "Agenda tu examen de imágenes en minutos": Resonancias desde $54.990, Mamografías desde $11.750, Tomografías desde $13.380, Ecografías desde $7.660, Radiografías desde $5.520, PET-CT desde $322.016.
- **/agendamiento-cardiologia** — "Agenda tu examen de cardiología en minutos": Ecocardiograma Doppler desde $38.010, Electrocardiograma desde $3.860, Holter Ritmo desde $17.860, Holter Presión desde $12.490.
- **/agendamiento-consultas-medicas** — "Agenda tu Consulta médica en minutos": Traumatología desde $7.560, Medicina General desde $4.750, Medicina Interna "Desde: $.7560" (typo for $7.560), Kinesiología desde $3.620, Matrona desde $5.700, Psicología desde $6.550.
- Header menu **"Reservar hora"**: Cirugía Lasik, Laboratorio, Imágenes, Cardiología, Consultas Médicas/ Kine. Mobile bottom bar has a "Reservar" button.

## agenda-web.clini.cl (labs, imaging, cardiology)
Deep link `https://agenda-web.clini.cl/?servicio=<S>[&prestacion=<P>]`; with a prestación it is selected and the search runs by itself. Region defaults to 13 (RM). No branch or doctor parameter exists.

| servicio | Nombre | prestaciones (code: name) | regiones |
|---|---|---|---|
| 62 | Laboratorio | 30 Toma De Muestra (only one, preselected) | 6 O'Higgins, 9 Araucanía, 13 RM, 16 Ñuble; in RM a sector (Todos/Centro/Oriente/Sur/Poniente) |
| 64 | Resonancia | 804 Rodilla/Cadera/Hombro/Mano/Muñeca; 81 Columna cervical, dorsal o lumbar; 800 Cerebro/Cabeza; 801 Cuello; 803 Pelvis; 802 Abdomen; 805 Pierna/Brazo/Antebrazo; 83 Abdomen y pelvis; 82 Columna total; 806 Ambas rodillas, caderas, hombros, manos, muñecas; 807 Ambas piernas, brazos, antebrazos; 808 Columna total con contraste; 86 Otras RM | 5 Valparaíso, 13 RM |
| 70 | Scanner (TAC) | 94 Angio TAC; 90 TAC cerebro/cabeza/cuello; 91 TAC columna; 93 TAC extremidades; 92 TAC tórax/abdomen/pelvis; 95 Otros TAC | 5, 13 |
| 57 | Radiografía | 70 Radiografía General; 72 Radiografía Proyecciones | 5, 13 |
| 65 | Mamografía | 401010 Bilateral (4 exp.); 401110 Unilateral (2 exp.) | 13 |
| 81 | Ecografía | 60 Mamaria; 67 Abdominal; 62 Pélvica; 63 Doppler; 64 Musculoesquelética; 66 Tiroides/Renal; 65 Otras | 13 |
| 82 | Ecoginecología | 43 4D y 5D; 44 Doppler 11–14 semanas; 45 Doppler 20–24 semanas; 99 Doppler ginecológico; 42 Ginecológica; 100 Obstétrica | 13 |
| 71 | PET-CT | 35 PET CT | no region step |
| 76 | Holter de Ritmo | 46 | 13 |
| 77 | Holter de Presión | 47 | 13 |
| 78 | Electrocardiograma | 49 | 13 |
| 79 | Ecocardiograma | 50 | 13 |

Not linked from the site (don't offer): 55 Kinesiología, 68 and 80 (old eco services), 72 Control cirugía LASIK, 73 Pabellón LASIK, 74 Eval. cirugía LASIK, 75, 83 Test de esfuerzo, 86. The LASIK evaluation is booked through the lead form, not agenda-web.

### The steps, in the visitor's words
1. **"Selecciona tu prestación"**: the service name is shown; choose the **región** (if asked) and the **prestación** (a searchable list); press **"Buscar disponibilidad"**.
2. **Elige el día**: a calendar with the available days (two months; arrows to change month). Days without slots say "sin agenda".
3. **Mañana o tarde**: AM / PM buttons.
4. **Elige el centro y la hora**: each centre is a group ("TM | BUIN", "CENTRO DE SALUD | METRO TOBALABA"); only the first is open — tap another centre to see its times; "Ver más horas" shows the rest. The summary reads e.g. "JUEVES, 22 DE OCTUBRE DE 2026 A LAS 07:00 (AM) · TM | BUIN".
5. **"Continuar"** ("Validando horario…"). A notice with the service's indications may appear (e.g. for laboratorio: gynaecological samples only at Los Leones, Cortisol AM at 9 h, orders by nutritionist/nurse not covered by Fonasa) → **"Entendido"**.
6. **Datos del paciente**: the appointment summary (centro, dirección, servicio, beneficio, fecha, hora, indicaciones del centro). Then RUT (or passport), nombre, apellido paterno, apellido materno, fecha de nacimiento, sexo, teléfono (+56, 9 digits), correo. If the RUT already belongs to a patient, the name/birth/sex fields fill in masked and locked; a new patient fills everything ("Paciente nuevo: completa todos los campos.").
7. **Consentimiento**: the visitor ticks the privacy consent (terms of data use).
8. **AGENDAR**: **the visitor presses it**, never Javier. A success screen shows the summary and returns to clini.cl after 30 s. Until AGENDAR is pressed, nothing is reserved.

After booking, CLINI confirms by calling from **600 023 1207** or by WhatsApp **+56 9 8553 9754** (agenda-web confirmation text). **Cancel**: menu "Cancelar cita" → https://agenda.clini.cl/FrmAgendaAnular.aspx. FAQ "¿Qué pasa si no puedo asistir a mi hora médica?": avisar "con al menos 24 horas de anticipación", by the link in the confirmation or by WhatsApp. FAQ "¿Cuánto tiempo antes debo llegar a mi cita?": "al menos 15 minutos antes".

## Reservo (consultas médicas and therapies)
Every consulta "Reservar hora" opens agendamiento.reservo.cl (Reservo, a third-party booking app) in 5 steps: Centro Médico → Prestación → Profesional → día y hora → datos. Links (all under https://agendamiento.reservo.cl/makereserva/): Traumatología agenda_multisucursal/r0KRDfl0c0kMvl2A1Q19A3z1i659XG; Medicina General agenda_multisucursal/20nmRjj0K0Hn2m4y1W79hki1L059UA; Medicina Interna agenda_multisucursal/p0dv0iG0y0pH4l7V1B89mJh1e3U9o2; Psicología agenda/K0o51vu0B0RxkW171W29ppW1u1Y9ul; Kinesiología agenda/J0ruvTj0R0x9wD8O1M19aws1w5n9Fi; Matrona agenda/M03rCYr000BlJe3j1859XPv1K3R9pY; Medicina deportiva agenda/b0jpo8W0O05te80A1i49VF0187T9ri; Neurocirugía agenda_multisucursal/O0idmkN090KIlj9y1t89ydL1Y1B9rN; Cirugía General agenda_multisucursal/j00GJm30g0X9PG8T1b19lhF1E4a92q; Nutricionista agenda/F02dJ9Z0Q0LF8h0q1V393yR1h7791a; Urología agenda/j0E6Udi0y0LNwL4915697N11h5r9hW. Javier opens the right one and guides by voice; he does not drive Reservo. Telemedicina: clini.medipasspro.com.

## LASIK: free evaluation (lead form)
/cirugia-lasik, section "¡Agenda tu evaluación gratuita!" (every "¡Agendar evaluación!" button scrolls there). Fields: Nombre y apellido, RUT (typed by the visitor, format 12345678-9), Correo, Teléfono (+56 9 XXXX XXXX), Previsión, Ubicación (Santiago - LTO, Santiago - Lyon, Santiago - Metro Santa Lucía, Antofagasta, Temuco). The visitor presses "¡Agendar evaluación!". Success: "Muy pronto uno de nuestros coordinadores te llamará para elegir el mejor día y hora para ti" — the form does not book a slot. Ages 18–60.

## By phone, WhatsApp, chat
- Call center **22 994 4003**: Lunes–Viernes 08:00–22:00, Sábados 08:00–20:00, Domingo 14:00–22:00.
- WhatsApp agendamiento **+56 9 8246 3202** (the Astra page also gives +569 9489 0594).
- "Clini Chat" (Clinito, bottom-right).
- FAQ "¿Qué necesito para agendar una hora?": cédula de identidad and a phone or email.

## Price first
Cotizador: https://cotizador-web.clini.cl/ (menu "Cotizador"): search exams for a price; the full quote asks name, RUT, phone, previsión and caja; "Cotizador IA" reads a photo of the medical order. See topic `precios`.

## Where the site disagrees with itself
- FAQ "¿Qué pasa si no puedo asistir a mi cita?" says to reschedule from "tu perfil de usuario en nuestra plataforma"; agenda-web has no user profile — cancellation is via the confirmation link, WhatsApp or "Cancelar cita".
- Medicina Interna price "$.7560" (typo); Electrocardiograma $3.860 here vs $3.810 on the cardiology table; Holter ritmo $17.860 vs $17.880.
- PET-CT "desde" $322.016 here, $316.416 on the home tab, $299.000 on /ahorra-fonasa-1.
