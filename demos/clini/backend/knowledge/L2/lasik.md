# Cirugía LASIK (CLINI Visión) y la evaluación gratuita

Sources: https://www.clini.cl/cirugia-lasik (sections "Cirugía Lasik", "¡Agenda tu evaluación gratuita!", "🤔 ¿Qué es la cirugía LASIK y por qué elegir CLINI?", "Beneficios de la Cirugía Refractiva LASIK en CLINI", "Historias reales de pacientes felices", "🔎 Preguntas frecuentes sobre la Cirugía LASIK", "Tu salud en buenas manos", "⏰ ¡Mejora tu visión ahora!", "🚀 CLINIVIDENTES: Recomienda y gana", "📍 Estamos cerca de ti"); https://www.clini.cl/cirugia-lasik/santiago ("Cirugia Lasik en Santiago", "Cirugía oftalmológica precios en Providencia", "Preguntas frecuentes de cirugía ocular"); https://www.clini.cl/cirugia-lasik/temuco; https://www.clini.cl/cirugia-lasik/diagno-antofagasta; https://www.clini.cl/cirugia-lasik/clinividentes; https://www.clini.cl/cirugia-lasik/campana-de-derivadores; https://www.clini.cl/cirugia-lasik/pacientes-derivados-clini-vision; https://www.clini.cl/ (hero slider; tab "Cirugía Lasik"); https://www.clini.cl/ubicaciones; SITE_REPORT §4.1 (form selectors).

CLINI Visión does refractive surgery (LASIK) in **Santiago, Antofagasta y Temuco**: "Corrige miopía, astigmatismo e hipermetropía en solo 30 min sin dolor y con la mejor tecnología". The way in is a **free pre-surgical evaluation** ("evaluación gratuita", "Evaluación sin costo asociado"), requested with a lead form; a coordinator then calls the visitor to choose the day and time. LASIK is **not** in the cotizador and is not booked on agenda-web. Header: "Reservar hora → Cirugía Lasik" and footer "Cirugía Lasik" go to /cirugia-lasik/fonasa, which redirects to /cirugia-lasik; "Servicios → Oftalmología / Cirugía Lasik" → /cirugia-lasik.

## Price (hero "Cirugía Lasik" on /cirugia-lasik)
- **BONO PAD FONASA "$381.250/ojo*"** — "*Precio con BONO PAD FONASA + Bonificación de convenios con Cajas y Municipalidades." Say it as **"desde $381.250 por ojo"** and that the exact copago is calculated at the free evaluation ("Al momento de venir por tu evaluación, te asistiremos para calcular tu copago más bajo").
- **Pacientes ISAPRES: "HASTA COPAGO $0*"** — "Pacientes isapres dependen de su cobertura."
- Bono PAD (Pago Asociado a Diagnóstico, /cirugia-lasik/santiago "Bono PAD LASIK y convenios en Providencia"): lets Fonasa users get LASIK "con un precio fijo y conocido". CLINI "es un prestador afiliado a Fonasa con autorización para emitir bonos electrónicos y Bono PAD en todos nuestros centros".
- Payment ("⏰ ¡Mejora tu visión ahora!"): **"De 3-6 a 12 cuotas sin interés"**; "Bonificación exclusiva de **$200.000** si te operas ambos ojos y eres de **Puente Alto, Ñuñoa** o tienes **convenio con tu caja de compensación**". Campaign pages add "Plan 50/50: da un pie del 50% y paga el resto en 12 cuotas sin interés" and "Usa tus tarjetas de crédito en CLINI".
- Prices conflict across pages — see the last section; never pick one silently.

## What the site says about the surgery
- Ambulatory, ~30 minutes, laser seconds per eye, anesthetic drops, painless; recovery: "retoma tus actividades en 24 a 48 horas", "Resultados visibles en las primeras 24hrs." Corneal topography equipment, certified ophthalmologists. "Más de 1.000 pacientes han recuperado su visión con nosotros." (a blog post title says "Más de 2.300 pacientes").
- Before surgery (/cirugia-lasik/pacientes-derivados-clini-vision): no contact lenses in the days before; no makeup, eye creams or perfume that day; tell the specialist about drug allergies; come with a companion; no driving for 24 hours afterwards.
- Evaluation day: "Escáner ocular 3D" (a map of the eye to see if you are apt), advice and payment options, then you schedule the operation.

## FAQs (/cirugia-lasik, "🔎 Preguntas frecuentes sobre la Cirugía LASIK")
- **¿Es dolorosa?** No. Rápido y ambulatorio, anestesia local en gotas.
- **¿Cuánto dura la cirugía?** Cerca de 30 minutos; el láser solo toma segundos por ojo.
- **¿Desde qué edad puedo operarme?** Desde los 18 años, con graduación estable y una evaluación ocular previa (incluye topografía corneal).
- **¿Qué pasa si no soy candidato?** Lo sabrás en la evaluación gratuita. Si no puedes operarte, no pagas nada.
- **¿Qué personas son candidatas para la cirugía LASIK?** Buena salud ocular, sin enfermedades como queratocono, con miopía, astigmatismo o hipermetropía.
/cirugia-lasik/santiago has more ("Preguntas frecuentes de cirugía ocular"): ¿Cuándo podré notar los resultados?, ¿Cuánto tiempo debo descansar…?, ¿Los resultados… son permanentes?, ¿Qué pasa si tengo miopía y astigmatismo al mismo tiempo?, ¿Puedo pagar la cirugía con Bono PAD Fonasa?
Whether a particular person is a candidate is decided only at the evaluation — I don't judge it.

## The free evaluation form (/cirugia-lasik, section "¡Agenda tu evaluación gratuita!", `#form`)
"Válido para personas entre 18 y 60 años. Al enviar este formulario, declara haber leído y aceptado los Términos, Condiciones y la Política de Privacidad." Every "¡Agendar evaluación!" button on the page jumps here. Form `#nuevo_lasik_junio`:
- **Nombre y apellido** `#name` (placeholder "Nombre y Apellido: María Perez")
- **RUT** `#rutInput` — **the visitor types it**; format without dots, with hyphen (12345678-9); invalid → "RUT inválido. Debe estar sin puntos y con guión (ej: 12345678-9)". I point at it, never say or fill it.
- **Correo** `#correo`
- **Teléfono** `#telefonoInput` — prefilled "+56 9 "; formatted `+56 9 XXXX XXXX` (I set the digits, e.g. 912345678, and read it back)
- **Previsión** `#Prevision-4` — Fonasa, Banmédica, Consalud, CruzBlanca, Colmena, Nueva Más Vida, Vida Tres, iSalud, Fundación, Cruz del Norte, Esencial, Particular
- **Ubicación** `#Ubicaci-n-2` — shown as "Santiago - Metro Tobalaba", "Santiago - Metro los Leones", "Santiago - Metro Santa Lucía", "Antofagasta - Sucre 244", "Temuco - Av. Alemania 999" (option values "Santiago - LTO", "Santiago - Lyon", "Santiago - Metro Santa Lucía", "Antofagasta", "Temuco")
- Submit **"¡Agendar evaluación!"** — **the visitor presses it**, never me. Success text: "¡Gracias por agendar tu evaluación gratuita! Muy pronto uno de nuestros coordinadores te llamará para elegir el mejor día y hora para ti." It books no slot: it is a call-back.
The city landings carry their own forms with separate Nombre / Apellido fields and a consent line "Autorizo a CLINIVisión SpA para el tratamiento y uso de mi información… Ley 19.628".

## Where (tab widget "📍 Estamos cerca de ti": Región Metropolitana / Región Antofagasta / Región de la Araucanía)
- **Centro de Salud Metro Tobalaba** — Luis Thayer Ojeda 073, Providencia (evaluations; /ubicaciones tags "Evaluación Cirugía Lasik").
- **Visión Los Leones** — Av. Ricardo Lyon 190, Providencia. L–V 9:00–18:30, Sáb 09:00–12:30.
- **Visión Metro Santa Lucía** — Miraflores 156, Santiago Centro. L–V 9:00–18:30, Sáb 09:00–12:30.
- **Visión Antofagasta** — Sucre 244, 2do piso de Diagno Salud. L–V 9:00–19:00, Sáb 09:00–13:00.
- **Visión Temuco** — Avenida Alemania 999, Edificio Paseo de las Artes. L–V 9:00–18:30, Sáb 09:00–12:30.
Sundays closed at all Visión sedes.

## City landings (listed)
- /cirugia-lasik/santiago ("Cirugia Lasik en Santiago", title "Cirugía Lasik | Providencia"; /cirugia-lasik/providencia redirects here): "$200.000 Bonificación especial al copago de la cx*", 4 steps (evaluación pre-quirúrgica → cirugía ambulatoria → resultados inmediatos → controles), "💰 Precio desde $481.250 por ojo con Bono PAD Fonasa", "$200.000 al operarte ambos ojos → $422.210 por ojo según convenios".
- /cirugia-lasik/temuco ("LASIK Temuco: cirugía láser ocular y cirugía refractiva"): same structure, Av. Alemania 999, "desde $481.250 por ojo".
- /cirugia-lasik/diagno-antofagasta ("Deja tus lentes con cirugía LASIK.", "Evaluación gratuita en Antofagasta"; /cirugia-lasik/antofagasta redirects here): "$381.250 Con Bono PAD FONASA y beneficios aplicables*", Sucre 244.

## CLINIVIDENTES (referrals)
/cirugia-lasik section "🚀 CLINIVIDENTES: Recomienda y gana": "Si ya te operaste en CLINI, puedes ser un Clinividente. Por cada amigo o familiar que se opere gracias a tu recomendación, ganas $100.000." Button "¡Quiero referir y ganar!" → /cirugia-lasik/clinividentes (**unlisted landing**, not in the sitemap): a form with your data (nombre, email, teléfono) and the referral's (nombre, email, teléfono, RUT, sucursal). Referrals must wear glasses and have miopía, astigmatismo or hipermetropía; "¡ganas hasta $100.000!".

## Unlisted landings (campaign pages — don't send visitors there unprompted)
/cirugia-lasik-ocular (SEO landing, its own form), /cirugia-lasik/clinividentes, /cirugia-lasik/campana-de-derivadores, /cirugia-lasik/campana-de-derivados-vision, /cirugia-lasik/derivadores-clini, /cirugia-lasik/pacientes-derivados-clini-vision (referred-patient pages with older prices and a "Plan 50/50"). Prefer /cirugia-lasik.

## Where the site disagrees with itself
- **Price per eye with Bono PAD**: **$381.250** in the /cirugia-lasik hero ("BONO PAD FONASA $381.250/ojo*", price with convenio bonuses), in its title and meta description ("desde $381.250") and on /cirugia-lasik/diagno-antofagasta; **$481.250** in the same page's section "🤔 ¿Qué es la cirugía LASIK y por qué elegir CLINI?" ("copago promedio por Bono PAD de $481.250 por ojo"), in the home tab "Cirugía Lasik" ("Fonasa: $481.250") and on /cirugia-lasik/santiago and /temuco ("desde $481.250"). Older landings: $522.210/ojo (campana-de-derivadores), $501.160/ojo (pacientes-derivados), both totals $1.002.320 for two eyes; /cirugia-lasik/santiago: $422.210 per eye after the $200.000 bonus. Say "desde $381.250 por ojo con Bono PAD y convenios; el copago promedio que muestra el sitio es $481.250; se confirma en la evaluación gratuita".
- **The $200.000 bonus**: home slider "Bono de hasta $200.000"; /cirugia-lasik: only if you operate both eyes **and** are from Puente Alto or Ñuñoa or have a caja de compensación convenio; city landings: "Bonificación especial al copago de la cx*".
- **Ages**: /cirugia-lasik form 18–60; campana-de-derivadores "18 a 65 años"; FAQ "desde los 18 años".
- **Cuotas**: "3-6 a 12 cuotas sin interés" (/cirugia-lasik) vs "6 a 12 cuotas sin interés" (campaign pages).
- **Referral reward**: "$100.000" (/cirugia-lasik, clinividentes body) vs the clinividentes title "Gana $100 por referir".
- **Patients operated**: "Más de 1.000" (/cirugia-lasik) vs "Más de 2.300" (blog post title).
