# Calendario y eventos

Sources: https://saintgeorge.cl/familia/calendario/ (h1 "Calendario", dos iframes de Google Calendar); https://saintgeorge.cl/familia/informativo/; https://saintgeorge.cl/familia/musical-the-lion-king/; https://saintgeorge.cl/familia/ (tarjetas). Crawl 2026-10-22.

## Dónde están los eventos `[en vivo]`
- **`/familia/calendario/`** (menú Familia ▸ Calendario). La página es solo el título "Calendario" y un **Google Calendar incrustado** del calendario `actividades@saintgeorge.cl` (zona horaria America/Santiago):
  - `iframe.calendar-desktop`: vista **mes** (`mode=MONTH`), en pantallas anchas.
  - `iframe.calendar-mobile`: vista **agenda** (`mode=AGENDA`), en pantallas angostas (< 992 px).
- El contenido del iframe es de otro origen (calendar.google.com): la página no puede leerlo y **este conocimiento no contiene eventos**. Dato cambiante: si preguntan "qué hay esta semana", los eventos se leen en vivo (el calendario público también existe como ICS: `https://calendar.google.com/calendar/ical/actividades%40saintgeorge.cl/public/basic.ics`) o se muestra el calendario en pantalla y se deja que el visitante lo mire. No inventes fechas.
- Para mostrarlo: navegar a `/familia/calendario/` y hacer scroll al iframe visible (`.calendar-desktop` o `.calendar-mobile` según el ancho).

## Fechas que el sitio escribe en texto
- **Musical The Lion King**: viernes 20 y sábado 21 de noviembre, Gimnasio del colegio (ver `musical-90-anos`). Es el único evento destacado con página propia.
- **Informativo 2026** (`/familia/informativo/`, carta de la Rectora; foto del inicio de año 2026, ya pasado): inicio de clases martes 3 de marzo de 2026 para 2° Básico a 12°; Pre-Kínder a 1° Básico se incorporan miércoles 4 y jueves 5 de marzo según su grupo. Menciona que con el Informativo se publicaba el "Calendario Escolar 2026".
- **Fechas de admisión**: no se guardan aquí; el estado de admisión se lee en vivo en `/admision/admision/` (show_fees(about="admission")).
- Ropero: atención los miércoles de 8:00 a 13:30 hrs.

## Lo que el sitio no tiene
Vacaciones, feriados, fechas de pruebas, reuniones de apoderados o actos escritos como texto: todo eso, si existe, está en el Google Calendar o en PDFs (Informativo 2026).
