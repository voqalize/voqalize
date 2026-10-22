# Centro Oncológico CLINI: exámenes para el diagnóstico del cáncer

Sources: https://www.clini.cl/centro-oncologico (sections "Ante la sospecha de cáncer:", "Cuéntanos qué tipo de cáncer te interesa conocer", "PET-CT" tabs, "¿No encuentras tu examen?", "Nuestra Ubicación", "Lo que dicen nuestros pacientes"); https://www.clini.cl/centro-oncologico-clini (sections "El primer paso es tu examen PET-CT", "¡Copago fijo máximo $316.416!", "Oncodiagnósticos: Todo en un solo lugar", "Ubicación y horarios de atención", "Preguntas Frecuentes:"); the seven cancer pages https://www.clini.cl/centro-oncologico/cancer-de-mama, /cancer-de-prostata, /cancer-de-pulmon, /cancer-colorrectal, /cancer-gastrico, /cancer-de-pancreas, /cancer-de-tiroides (sections "Exámenes Esenciales para tu Diagnóstico", "En Centro Oncológico CLINI te acompañamos en cada etapa con:", "Nuestra Ubicación"); cotizador catalogue (L3/prices.json, PET-CT).

CLINI is a **diagnostic** centre: the oncology pages offer the **exams** used to detect, stage and monitor cancer (PET-CT, TAC, resonancia, mamografía, ecografía, cardiology and laboratory), at Fonasa Nivel 1 prices. They do not offer cancer treatment or an oncologist consultation, and I never say whether someone has cancer or which exams they need: "Depende de la indicación de su médico". Header: "Servicios → Exámenes oncológicos" → /centro-oncologico; footer "PET-CT Oncológico" → /imagenes/examen-pet-ct-con-fonasa-nivel-1 (see topic `pet-ct`). /centro-oncologico-clini is an older landing of the same centre (in the sitemap, not in the menus).

## /centro-oncologico
- Hero "Ante la sospecha de cáncer:": "Realiza tu PET-CT, TAC o Pase Cardiológico con precios Clini y atención Fonasa e Isapre. Te ayudamos a gestionar tu atención sin demoras." Equipos de última generación · Resultados en 24-48 hrs · Especialistas certificados · Atención personalizada.
- "Cuéntanos qué tipo de cáncer te interesa conocer" — cards with "Ver exámenes recomendados" for Cáncer de Páncreas, Tiroides, Gástrico, Mama, Próstata, Pulmón, Colorrectal (each "✓ PET-CT, TAC y Resonancias disponibles").
- Exam tabs (TAC/Scanner, Mamografías, Resonancias, Ecografías, PET-CT), each with Información / Tecnología / Procedimiento / Precios:
  - **PET-CT** — "Estudio oncológico avanzado de cuerpo completo"; Duración 2-3 horas (incluye preparación); Resultados hasta 72 hrs; "Fonasa desde: $395.530"; Precios: **Precio Convenios $322.016**, **Precio FONASA $402.520**, **Precio Particular/Isapres $805.040**.
  - **TAC/Scanner** — "Protocolo oncológico detallado de cuerpo entero"; 10-20 minutos; hasta 72 hrs; Fonasa desde $34.250 (another block: convenios desde $29.990, Fonasa desde $34.850, particular desde $69.710).
  - **Mamografías**, **Resonancias Magnéticas** ("ideal para evaluar tejidos blandos sin radiación"), **Ecografías** (Fonasa desde $7.560).
  - "¿Listo para agendar? Te contactamos en menos de 1 hora" — "Agenda ahora" / "Solicitar Cotización".
- "¿No encuentras tu examen?": a network of associated centres; "Consultar Examen"; "Paquetes Personalizados: ¿Tu médico te indicó varios exámenes? Solicita una cotización de paquete personalizado".
- Click-to-call form `#wf-form-Formulario_Onco_c2c` (name, phone): the visitor sends it.
- "Nuestra Ubicación": **Luis Thayer Ojeda 073, Providencia** (Metro Tobalaba); teléfono +56 2 2994 4003; call center L–V 08:00–22:00, Sáb 08:00–20:00, Dom 14:00–22:00; Centro de Salud L–V 08:00–21:00, Sáb 08:00–20:30, Dom 09:00–20:30.

## /centro-oncologico-clini
- "El primer paso es tu examen PET-CT" — "Tus exámenes oncológicos para FONASA con los precios más convenientes".
- **"¡Copago fijo máximo $316.416!"** — "Afiliados Cajas de compensación… beneficio exclusivo para afiliados de Caja Los Andes. (se excluye FBB, PR04 y FAN)".
- "Oncodiagnósticos: Todo en un solo lugar": PET-CT Fonasa desde $402.510; Resonancia Magnética Fonasa desde $54.990; Tomografía (TAC/Scanner); plus cardiology and laboratory, "Reservar hora" on each.
- "Ubicación y horarios de atención": Luis Thayer Ojeda 073, Providencia, a block from Metro Tobalaba and near Costanera Center; L–V 08:00–20:00, Sáb 08:00–20:00, Dom 09:00–15:00 (Resonancias y TAC).
- A news block: "CLINI dona 12 Kits OncoDiagnósticos a Fundación CARE…".
- FAQs ("Preguntas Frecuentes:"):
  - **¿Soy Fonasa, puedo comprar mi Bono directo en CLINI?** Sí, for PET-CT: come with your orden médica, cédula de identidad vigente and fingerprint (huella) validation.
  - **¿Qué exámenes se requieren para el cáncer?** Depends on your doctor's indication; the centre has PET-CT, resonancias, ecografías, mamografías, TAC, cardiología, ecocardiogramas and 900+ lab exams.
  - **¿Puedo acudir acompañado el día de mi atención?** Sí, se recomienda un acompañante mayor de edad.
  - **¿Qué es un examen oncológico?** A test to detect, diagnose or monitor cancer.
  - **¿Cómo se realiza el diagnóstico del cáncer?** Several tests: imaging (PET-CT, tomografías, resonancias) and blood tests for markers.
  - **¿Cuánto cuestan los exámenes de detección de cáncer en CLINI?** Varies; Fonasa Nivel 1 discounts up to 60%; quote online (cotizador).
  - **¿Cuál es el mejor centro oncológico de Chile?** The site says CLINI is "uno de los centros de diagnóstico oncológico más recomendados en Santiago".

## The seven cancer pages (/centro-oncologico/<tipo>)
Each: hero with a short definition ("Volver a Centro Oncológico Clini"), "Llama ahora: +56 2 29944003", tabs "¿Qué es y por qué se puede producir?" / "Exámenes Necesarios" / "Síntomas", then **"Exámenes Esenciales para tu Diagnóstico"** — exam cards (dropdowns with Información, Indicaciones, Procedimiento, Precios) the visitor ticks to build a quote; then a call-back form `#wf-form-formulario_callonco` (exámenes seleccionados, total cotizado, Nombre completo, teléfono, correo, Previsión) that the visitor sends; "En Centro Oncológico CLINI te acompañamos en cada etapa con:" (PET-CT, RM 3 Tesla, TAC multicorte; "Sin lista de espera · Agenda hoy, examínate mañana").
Exams listed per page:
- **Cáncer de Mama**: PET-CT FDG cuerpo entero, Mamografía Bilateral, Ecografía Mamaria, Mamografía proyección complementaria, ECG, Ecocardiograma, Creatinina, Chequeo Metabólico y Hormonal.
- **Cáncer de Próstata**: Antígeno prostático (PSA), Perfil Preventivo Masculino Completo, Ecografía Pélvica Masculina, Resonancia Magnética de Próstata (desde $54.990), Creatinina, ECG, PET-CT FDG, TAC Abdomen y pelvis.
- **Cáncer de Pulmón**: PET-CT FDG, Radiografía de tórax, TC de tórax, ECG, Ecocardiograma, Creatinina, Batería de Laboratorio – Perfil Completo.
- **Cáncer Colorrectal**: PET-CT FDG, Hemorragia Oculta en Deposiciones, TC de tórax, abdomen y pelvis, Panel Metabólico Completo, Ecocardiograma, ECG, Creatinina, RM de pelvis.
- **Cáncer Gástrico**: Endoscopía, Chequeo Nutricional y Metabólico Completo, Creatinina, TC de tórax, abdomen y pelvis, Antígeno Carcinoembrionario (CEA), PET-CT FDG, Ecocardiograma, ECG.
- **Cáncer de Páncreas**: Batería de Función Hepática y Marcadores Tumorales, PET-CT FDG, Ecocardiograma, ECG, TAC Abdomen y pelvis.
- **Cáncer de Tiroides**: Perfil Tiroideo (TSH, T3, T4 libre) y Calcitonina, Ecografía Doppler Tiroidea, TAC de Cuello y Tórax, RM de Cuello, PET-CT FDG, ECG, Ecocardiograma, Creatinina.

## Booking
- PET-CT: agenda-web servicio **71** (prestación 35 "PET CT", no region step), reached on the site through the legacy link `agenda-imagenes.clini.cl/…?PET_CT=CLTO` which redirects there; the PET-CT page also has a request form with medical-order upload (`#wf-form-from_pet`). Preparation for PET-CT is sent by CLINI to the patient (cotizador: "Las indicaciones específicas para la preparación del examen serán enviadas…"); the /indicaciones-pet page has the details (topic `preparaciones`).
- TAC, resonancia, mamografía, ecografía: agenda-web (topics `scanner`, `imagenologia-resonancia`, `mamografia`, `ecografia`).
- Cotizador PET-CT items (FDG, FDG cerebral, PSMA, PR04, 18F-nota-octreotide FAN): Fonasa $402.520 / particular $805.040.

## Where the site disagrees with itself
- **PET-CT Fonasa**: "desde $395.530" (/centro-oncologico tab header) vs "Precio FONASA $402.520" (same tab, Precios; cotizador) vs "Fonasa desde $402.510" (/centro-oncologico-clini) vs FDG "$402.520"/others "$402.540" in the PET-CT page table (SITE_REPORT). Convenio prices: "$322.016" (/centro-oncologico) vs "Copago fijo máximo $316.416" for Caja Los Andes (/centro-oncologico-clini, excluding FBB, PR04 and FAN; the home imaging tab says "PET-CT Desde: $316.416").
- **Results**: "Resultados en 24-48 hrs" (hero) vs "Hasta 72 hrs" (each exam tab).
- **Hours** at Luis Thayer Ojeda 073: L–V 08:00–20:00 / Dom 09:00–15:00 (Resonancias y TAC) on /centro-oncologico-clini vs L–V 08:00–21:00 / Dom 09:00–20:30 on /centro-oncologico and /ubicaciones.
- TAC "Fonasa desde": $34.250 vs $34.850 on the same page.
