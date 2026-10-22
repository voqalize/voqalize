# Resultados de exámenes (where to see exam results)

Sources: https://www.clini.cl/resultados (sections "Resultados de Exámenes CLINI", "¿Problemas para ver tus resultados?"; dropdowns "Imagenología Rayos X · Ecografías · TAC · RM" and "Laboratorio Clínico Hemograma · Bioquímica · Hormonas"); https://www.clini.cl/laboratorio and the /laboratorio/* branch pages (FAQs "¿Cómo puedo descargar mis resultados?", "¿Cómo retiro mi examen?", "¿Cuánto tiempo tardaré en obtener mis resultados?"); https://www.clini.cl/agendamiento (FAQ "¿Cuánto demoran los resultados?"); imaging and cardiology pages (buttons "Resultados de imágenes", "Resultados de cardiología"); header menu "Pacientes" → "Resultados de exámenes"; footer "Resultados de Exámenes".

**Javier never reads, interprets or comments on a result**, and never asks for one. He shows where the portal is and opens it; the visitor types their own RUT and code. For what a value means, the site's own words are: "es un médico especialista la persona mejor calificada para dar lectura a los resultados de tus exámenes" — so: their doctor. Urgent symptoms: call 131 (SAMU) or go to an urgencia.

## The page: /resultados
Heading "Resultados de Exámenes CLINI": "Encuentra tus resultados para laboratorio e imagenología directamente a través de nuestra plataforma, sin necesidad de registros ni contraseñas." Under "¿Qué tipo de resultado estás buscando?" there are two dropdown cards; open the right one, then its "Ver mis resultados" button:

| Card | Steps on the card | Portal |
|---|---|---|
| **Imagenología** (Rayos X · Ecografías · TAC · RM) | 1. "Haz click en Acceder con código de paciente." 2. "Ingresa tu RUT y el código de orden que aparece en tu comprobante de atención." 3. Review and download online. | https://app.dalca.cl/portal/clini?access_type=email |
| **Laboratorio Clínico** (Hemograma · Bioquímica · Hormonas) | 1. "Ingresa tu RUT." 2. "Encuentra tu exámen." 3. "Descarga tus resultados". | https://resultados.clini.cl/Resultados/Index |

Also on the page, "Información importante": if you can't collect your exams in person, authorise someone with a signed "poder simple" (button "Descargar documento", a PDF) and a copy of your valid cédula.
Section "¿Problemas para ver tus resultados?": "Nuestro equipo está disponible para ayudarte" → button "Formulario de contacto" (/solicitudes/contacto, new tab). The call center is 22 994 4003.

## Other links to the same portals
- Lab branch FAQ "¿Cómo retiro mi examen?": at https://resultados.clini.cl with "tu RUT sin puntos y con guion, además de tu número de orden, el cual será enviado a tu correo en el momento de la atención". /laboratorio FAQ "¿Cómo puedo descargar mis resultados?": "Resultados" section of the site with RUT and order number; you can also email them to yourself.
- Imaging pages ("Resultados de imágenes") and cardiology pages ("Resultados de cardiología") link https://app.dalca.cl/portal/clinilto; RM body-part pages link https://app.dalca.cl/portal/clini?access_type=alternative.
- A few blog posts and /examenes/perfil-hepatico… link an older patient portal, patientportal.prod.clini.procloudhub.com.
- Old path /resultados-clini redirects to /resultados.

## How long results take (as the site says)
- Laboratory: "en general … disponibles en 24 horas"; "En la Toma de Muestras de Metro Los Leones, puedes recibir resultados express en 4 horas para exámenes específicos" (/agendamiento). /laboratorio: "Mayoría de exámenes entregados en 24-48 horas". Los Leones and Santa Lucía pages: "Resultados en tan solo horas" for hemograma, creatinina, perfiles, glucosa, glicada, vitaminas D and B12, electrolitos, HIV, TP, TTPK, insulina.
- Per exam pages: hemograma and hemoglobina glicada "menos de 12 horas"; perfil lipídico, tiroideos, curvas "menos de 24 horas"; test de antígenos "en el plazo de 1 hora"; vitamina D "en pocos días" (sent to certified labs).
- Imaging, cardiology: no general time is stated on these pages; say so and point to the portal or the call center.

## How Javier helps
1. Ask lab or imaging (or cardiology, which uses the imaging portal on the cardiology pages).
2. Cue `{page: /resultados}` then `{show: Resultados de Exámenes CLINI}`; open the right dropdown card.
3. Offer to open the portal in a new tab (`open_link` kind `results_lab` or `results_imaging`); tell them they'll need their RUT (and, for imaging, the code on the comprobante). They type it themselves.

## Where the site disagrees with itself
- Imaging portal: /resultados uses app.dalca.cl/portal/clini?access_type=email; imaging and cardiology pages use /portal/clinilto; RM pages use ?access_type=alternative. All are the same provider; /resultados is the page to start from.
- Lab results time: 24 h, 24–48 h, 4 h express or "en solo horas", depending on the page.
- /resultados says "sin necesidad de registros ni contraseñas"; imaging still needs the RUT and the order code.
