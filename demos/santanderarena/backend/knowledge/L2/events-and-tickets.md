# Events and tickets

Sources: /cartelera (H1 "Nuestra Cartelera"); every /nuestra-cartelera/... event page; the footer legal line; /preguntas-frecuentes ("Entradas y Acceso"); the home page ("Próximamente").

## Where events are listed
- **Cartelera (`/cartelera`)**, menu item "Cartelera". The page opens on the current month. Its section title is the month and year, e.g. "Octubre 2026" (`h2#title-filter`), with "Anterior" / "Siguiente" buttons either side. Above it is the filter bar: a search box ("¿Qué evento buscas?"), a type select ("Todos los eventos"), "Desde" / "Hasta" date inputs, "Fin de semana", "Este mes" and "Limpiar filtros". When nothing matches it shows "No se encontraron resultados" ("Intenta borrar o cambiar los filtros aplicados").
- The page holds all 275 event cards in its HTML (past events back to 2025 included). The month filter only hides the cards of other months. Each card shows the date ("5 Noviembre / 21:00 hrs", with no "de"), the name in capitals, "Ver más" (the event page), "Comprar tickets", and icons for "Compra Estacionamiento" and, on many cards, "Compra Experiencias VIP".
- The home page has two "Próximamente" blocks: a carousel beside the hero video (3 cards with "Ver más") and a row of 3 event cards lower down, followed by "Ver Cartelera". Experiencias VIP has its own "Proximamente" row (spelt without the accent).
- A Prontus listing "Conciertos" (`/santander-arena/site/tax/port/all/taxport_1_1__1.html`, reached from the event breadcrumb "Conciertos") shows the same cards, paginated 1–6. Pages 2–6 redirect.

## An event page
Path `/nuestra-cartelera/<categoría>/<slug>`. Almost all are `conciertos`. A few have no category (`/nuestra-cartelera/blessd`, `/nuestra-cartelera/jack-johnson`, `/nuestra-cartelera/epica-rhapsody`, `/nuestra-cartelera/los-tres-unplugged`…), and ten past September 2025 shows live at `/cartelera/conciertos/<slug>`. Repeat dates get numbered slugs (`anuel-aa`, `anuel-aa-0`, `anuel-aa-1`…), and some slugs start "copia-de-" (copied pages).
Top to bottom:
1. Breadcrumbs "Inicio › Nuestra Cartelera › Conciertos". Head block: name (h2, capitals) and date line, e.g. "5 de Noviembre / 21:00 hrs", with a "Comprar tickets" button.
2. A sidebar card repeating name and date with up to three buttons: **"Comprar tickets"** (`a.btn-tickets`), **"Comprar estacionamiento"** (`a.btn-parking`), **"Compra Experiencias VIP"** (`a.btn-upgrade`). On many pages parking and VIP point to the same Puntoticket product URL (e.g. Camilo: both `puntoticket.com/producto/push/BIZ376/1`).
3. The description (Spanish), usually the name in bold, a bold "<fecha> – Santander Arena" line, 1–3 paragraphs, "Vive esta experiencia en Santander Arena, el recinto #1 de Latinoamérica.", then "Produce: <productora>" and the producer's RUT. Most have a YouTube video.
4. "Completa tu noche en Santander Arena": cards RESERVA TU EXPERIENCIA VIP (→ /experiencias), RESERVA TU ESTACIONAMIENTO ("Ir a reservación" → puntoticket.com/estacionamientos), HAZTE CLIENTE SANTANDER (→ banco.santander.cl).
5. "Te puede interesar": three other events. These are often past ones (e.g. Chencho Corleone 22 Nov 2025).

## Tickets
- Footer, every page: "Les recordamos que la única venta oficial para todos los shows en Santander Arena es a través de Puntoticket en su web www.puntoticket.com y en sus puntos de venta físicos oficiales. Respecto de otros sitios que comercializan tickets de shows que se realizarán en Santander Arena, tanto el recinto como las productoras no pueden responder frente a problemas que se generen con ellos."
- FAQ 1: official tickets "únicamente a través de PuntoTicket o en la boletería del recinto en días de evento".
- FAQ: children usually pay from age 2, depending on the producer. Bring the ticket (printed or digital) plus cédula de identidad or passport. Lost e-ticket: download or print it again on Puntoticket ("Santander Arena no puede reemitir entradas"). Transfers depend on the event (some tickets are nominative).
- Door times are not on the site; they are announced on Instagram (FAQ 18, ¿Cómo llegar?).
- Every booking button opens puntoticket.com in a new tab. The agent can point at the button but cannot buy.

## Using the data
- `L3/events.json`: every event with `date` (ISO), `time`, `date_text`/`time_text` as written, `tickets_url`, `parking_url`, `vip_url`, `producer`, an English `summary` and the Spanish `description`. `upcoming` is relative to 2026-10-21. Dates come from the cartelera's `data-fecha`, so the year is the site's own.
- The events-index topic lists them all by date. On 2026-10-21 there were 66 upcoming (21 Oct 2026 → 3 Nov 2027; busiest November 2026 with 22, then December with 17) and 209 past.
- Home "Próximamente" shows dates without a year: "30 de Marzo" (La Oreja de Van Gogh) is 2027, "29 de Noviembre" (Edo Caroe) is 2026.
