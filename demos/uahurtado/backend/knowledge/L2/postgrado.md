# Postgrado UAH

Sources: postgrados.uahurtado.cl /, /especialidad/{magister,diplomado,doctorado,cursos}/,
/doctorados/, /magister-online/, /areas_estudio/<área>/, /facultades/<facultad>/, /financiamiento/,
and the programme pages /programa/<slug>/.

## What there is
82 programmes (L3/programas.json; the full list by type is the postgrado-catalogo topic):
7 **doctorados**, 30 **magíster** (27 on the Magíster listing plus 3 **Magíster Online**), 34
**diplomados** and 7 **postítulos** (both on the Diplomados listing), and 4 **cursos y talleres**
(docencia universitaria, supervisión de tesis, ética de la investigación, innovación; offered free to
postgraduate students). Modalities as the programmes state them: presencial, semipresencial sincrónica
(híbrida), online sincrónico, online. The Doctorado en Educación is joint with the Universidad Diego
Portales.

## How the site is organised
- Header menu: Doctorados, Magíster, Magíster Online, Diplomados, Cursos (`/especialidad/<x>/`).
- **Programas por Área** (14 áreas, `/areas_estudio/<slug>/`): Administración, Arte y Cultura,
  Ciencias Sociales, Comunicaciones, Derecho, Economía y Negocios, Educación, Educación Virtual,
  Filosofía y Humanidades, Gestión, Gobierno y Políticas Públicas, Literatura, Psicología, Tributaria.
- **Programas académicos por facultad** (`/facultades/<slug>/`): Ciencias Sociales, Derecho, Economía
  y Negocios, Educación, Filosofía y Humanidades, Psicología.
- Listings group programmes under faculty h2s (collapsible, `#collapse<id>`); each card shows
  Acreditación, Modalidad and Duración. There are no client-side filters: the URL is the filter.

## A programme page (`/programa/<slug>/`)
Hero `#cabeza-carrera` with the name and the lead form. Accordion `#programaAccordion`:
**Descripción General** (Objetivos del Programa, Destinatarios), **Plan de Estudios** (Metodología,
Horario), **Malla Curricular** (a PDF), **Requisitos y Valores** (documents required, then fees and
early-enrolment discounts: read live), **Perfil del Graduado**, **Docentes**. Sidebar: Postulaciones
(application window), Inicio (start date), Director/a, Contacto e Información (coordinator's e-mail
and WhatsApp), Admisión. All dates and prices: read live.

## Financing (`/financiamiento/`)
Becas de la AGCI, Crédito CORFO, ANID; links to Formas de Pago and Descuentos (alumni benefits,
agreements). Contact: postgrados@uahurtado.cl, WhatsApp +56 9 3455 2723, +56 2 2692 0200.
