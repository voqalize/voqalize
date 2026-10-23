# Mapa del sitio: cada página, sus títulos y acordeones

Sources: L3/pages.json, L3/sections.json y L3/site.json (generados por build.py desde un crawl con navegador headless de https://saintgeorge.cl).

Los títulos están escritos como los muestra la página (innerText: los botones de acordeón salen en mayúsculas por CSS). `(pseudo)` marca un párrafo en negrita usado como título. `▸` es un botón de acordeón (se abre con un clic; su id `#collapse_X_Y` se repite en cada página, así que se busca por su texto). Cada navegación es una carga de página completa. Las páginas vacías (plantilla por defecto de WordPress) están al final: no llevar al visitante ahí.

## Menú principal (#menu-menu-1)
- Colegio (/colegio/) (abre submenú, no navega)
  - Historia (/colegio/historia/)
  - Congregación de Santa Cruz Chile (/congregacion/congregacion-santa-cruz-chile/)
  - Proyecto Educativo (/colegio/proyecto-educativo/)
  - Documentos Institucionales (/documentos-institucionales/)
    - Plan Estratégico 2026-2030 (PLAE) (/colegio/plan-estrategico-2026-2030-plae/)
    - Plan Curricular (/colegio/plan-curricular/)
    - Plan Integral de Seguridad Escolar (PISE) (/colegio/plan-integral-de-seguridad-escolar/)
    - Reglamento Interno de Convivencia Escolar (RICE) (/colegio/reglamento-interno-de-convivencia-escolar-rice/)
    - Comité de Escolaridad (/colegio/comite-de-escolaridad/)
    - Reglamento de Evaluación, Calificación y Promoción (/colegio/reglamento-de-evaluacion-calificacion-y-promocion/)
    - Protocolos y Estrategias de Prevención (/colegio/protocolos-y-estrategias-de-prevencion/)
    - Programa de Afectividad, Sexualidad y Género (/colegio/programa-de-afectividad-sexualidad-y-genero/)
  - Equipo Directivo (/equipo-directivo/)
  - Infant (/unidad/infant/)
  - Elementary (/unidad/elementary/)
  - Junior (/unidad/junior/)
  - Senior (/unidad/senior/)
- Familia (/familia/) (abre submenú, no navega)
  - Postulación opcionales 2027 (https://sistemas.saintgeorge.cl/opcional/postular)
  - Postulación plan diferenciado 11° 2027 (https://sistemas.saintgeorge.cl/diferenciado/postular-11)
  - Postulación plan diferenciado 12° 2027 (https://sistemas.saintgeorge.cl/diferenciado/postular-12)
  - Informativo (/familia/informativo/)
  - Lista de Materiales (/familia/materiales/)
  - Calendario (/familia/calendario/)
  - Schoolnet (https://schoolnet.colegium.com/webapp/es_CL/login)
  - Casino (/familia/casino/)
  - Ropero (/familia/ropero/)
  - Boletín The Dragon (/familia/boletin-the-dragon/)
  - Musical The Lion King (/familia/musical-the-lion-king/)
- Formación integral (/formacion-integral/) (abre submenú, no navega)
  - Aprender a Ser y trascender (/aprender-a-ser-y-trascender/)
    - Introducción (/formacion-integral/introduccion_aprender_a_ser_y_trascender/)
    - Dirección de Pastoral (/formacion-integral/direccion_de_pastoral/)
    - Psicorientación (/formacion-integral/psicorientacion/)
  - Aprender a Conocer (/aprender-a-conocer/)
    - Introducción (/formacion-integral/introduccion_aprender_a_conocer/)
    - Dirección de Estudios (/formacion-integral/direccion_de_estudios/)
  - Aprender a Convivir (/aprender-a-convivir/)
    - Introducción (/formacion-integral/introduccion_aprender_a_convivir/)
    - Área Deportiva (/formacion-integral/area-deportiva/)
    - Área de Convivencia Escolar (/formacion-integral/area-de-convivencia-escolar/)
- Admisión (/admision/) (abre submenú, no navega)
  - Admisión (/admision/admision/)
  - Admisión Programa Moreau (/admision/admision-programa-moreau/)
- Comunidad (/comunidad/) (abre submenú, no navega)
  - Centro de Estudiantes (CDE) (https://sites.google.com/georgian.cl/cde-2025/inicio)
  - Centro de Apoderados (CDA) (https://www.cdasaintgeorge.cl/)
  - Old Georgians (OGA) (https://www.oldgeorgians.cl/)
- Pago Colegiatura (https://sistemas.saintgeorge.cl/colegiatura/pagar-mensualidad)
- Footer: contacto@saintgeorge.cl (mailto:contacto@saintgeorge.cl); Centro de Estudiantes (CDE) (https://sites.google.com/georgian.cl/cde-2025/inicio); Centro de Apoderados (CDA) (https://cdasaintgeorge.cl/); Old Georgians (OGA) (https://www.oldgeorgians.cl/); LIRMI (https://login.lirmi.com/login); Trabaja con nosotros (https://saintgeorge.profejobs.cl/trabaja-con-nosotros); instagram.svg (https://www.instagram.com/gosaintgeorge/); linkedin.svg (https://www.linkedin.com/company/saint-george-s-college/)

## / (home)
Title: Saint George's College | Somos un colegio católico de la Congragción de Santa Cruz
  - Nuestra comunidad
  - La misión que nos convoca
  - Nuestros valores que guían la acción educativa
    - Respeto
    - Inclusión
    - Austeridad
    - Justicia
    - Responsabilidad
    - Honestidad
    - Caridad
  - The dragon
- ancla #comunidad (Nuestra comunidad)
- ancla #mision (La misión que nos convoca)
- ancla #valores (Nuestros valores que guían la acción educativa)
- PDFs (4): Dragon Septiembre; Dragon Junio; DRAGON Julio; Dragon Agosto

## /admision/admision (admission)
Title: Admisión
- Admisión
    - Cambridge English Qualifications

## /admision/admision-programa-moreau (admission)
Title: Admisión Programa Moreau
- Admisión Programa Moreau
- Enlaces externos: admisiones@saintgeorge.cl → mailto:admisiones@saintgeorge.cl

## /colegio (page)
Title: Colegio
  - Imagen divisoria
  - El Saint George’s College reconoce, valora y acompaña a la familia como el ente primario de formación y con un rol insustituible en esta.
  - La misión que nos convoca
- Enlaces externos: DESCARGAR DOCUMENTO → https://bbyte.cl/clientes/wp-sg/colegio/; LEE EL REGLAMENTO → https://bbyte.cl/clientes/wp-sg/colegio/; INSCRÍBETE A PASTORAL → https://bbyte.cl/clientes/wp-sg/colegio/#

## /colegio/comite-de-escolaridad (school)
Title: Comité de Escolaridad
- Comité de Escolaridad
- PDFs (1): REVISA EL REGLAMENTO DEL COMITÉ DE ESCOLARIDAD

## /colegio/historia (school)
Title: Historia
- Historia
- iframes: iframe.video-colegio (www.youtube.com)

## /colegio/plan-curricular (school)
Title: Plan Curricular
- Plan Curricular
- PDFs (1): REVISA EL PLAN CURRICULAR

## /colegio/plan-estrategico-2026-2030-plae (school)
Title: Plan Estratégico 2026-2030 (PLAE)
- Plan Estratégico 2026-2030 (PLAE)
- PDFs (1): REVISA EL PLAE

## /colegio/plan-integral-de-seguridad-escolar (school)
Title: Plan Integral de Seguridad Escolar (PISE)
- Plan Integral de Seguridad Escolar (PISE)
- PDFs (1): REVISA EL PISE

## /colegio/programa-de-afectividad-sexualidad-y-genero (school)
Title: Programa de Afectividad, Sexualidad y Género
- Programa de afectividad, sexualidad y género
- PDFs (1): REVISA EL PROGRAMA

## /colegio/protocolos-y-estrategias-de-prevencion (school)
Title: Protocolos y Estrategias de Prevención
- Protocolos y Estrategias de Prevención
- PDFs (1): REVISA LOS ANEXOS

## /colegio/proyecto-educativo (school)
Title: Proyecto Educativo
- Proyecto Educativo
  - El Saint George’s College reconoce, valora y acompaña a la familia como el ente primario de formación y con un rol insustituible en esta.
  - La Misión que nos convoca
- PDFs (1): DESCARGAR DOCUMENTO

## /colegio/reglamento-de-evaluacion-calificacion-y-promocion (school)
Title: Reglamento de Evaluación, Calificación y Promoción
- Reglamento de Evaluación, Calificación y Promoción
- PDFs (1): REVISA EL REGLAMENTO

## /colegio/reglamento-interno-de-convivencia-escolar-rice (school)
Title: Reglamento Interno de Convivencia Escolar (RICE)
- Reglamento Interno de Convivencia Escolar (RICE)
- PDFs (1): REVISA EL RICE

## /congregacion/congregacion-santa-cruz-chile (school)
Title: Congregación de Santa Cruz Chile
- Congregación de Santa Cruz
- Enlaces externos: CONOCE EL DISTRITO → https://congregaciondesantacruz.cl/new/
- iframes: iframe (www.youtube.com)

## /equipo-directivo (team)
Title: Equipo Directivo
- Equipo Directivo
    - Paula Noemi C.
    - Carolina López E.
    - P. Pablo Miranda M.
    - María Eliana Carrasco S.
    - P. Rodrigo Valenzuela R. C.S.C.
    - Javier Mascaró J.
    - Francisca Tagle V.
    - Yasna Jelincic S.
    - Cecilia Fanta F.
    - Marisol Corrotea O.

## /familia (page)
Title: Familia archivo
- Familia

## /familia/boletin-the-dragon (family)
Title: Boletín The Dragon
- Boletín The Dragon
- PDFs (7): EDICIÓN MARZO; EDICIÓN ABRIL; EDICIÓN MAYO; EDICIÓN JUNIO; EDICIÓN JULIO; EDICIÓN AGOSTO; EDICIÓN SEPTIEMBRE

## /familia/calendario (calendar)
Title: Calendario
- Calendario
- iframes: iframe.calendar-desktop (calendar.google.com); iframe.calendar-mobile (calendar.google.com)

## /familia/casino (family)
Title: Casino
- Casino
- PDFs (3): CARTA DE BIENVENIDA; MENÚ JUNIOR; MENÚ SENIOR

## /familia/informativo (family)
Title: Informativo
- Informativo 2026
- PDFs (1): REVISA EL INFORMATIVO 2026

## /familia/materiales (family)
Title: Materiales
- Lista de Materiales
- PDFs (13): PK – KK° LISTA DE ÚTILES Y PLAN LECTOR 2026; 1° LISTA DE ÚTILES Y PLAN LECTOR 2026; 2° LISTA DE ÚTILES Y PLAN LECTOR 2026; 3° LISTA DE ÚTILES Y PLAN LECTOR 2026; 4° LISTA DE ÚTILES Y PLAN LECTOR 2026; 5° LISTA DE ÚTILES Y PLAN LECTOR 2026; 6° LISTA DE ÚTILES Y PLAN LECTOR 2026; 7° LISTA DE ÚTILES Y PLAN LECTOR 2026; 8° LISTA DE ÚTILES Y PLAN LECTOR 2026; 9° LISTA DE ÚTILES Y PLAN LECTOR 2026; 10° LISTA DE ÚTILES Y PLAN LECTOR 2026; 11° LISTA DE ÚTILES Y PLAN LECTOR 2026; 12° LISTA DE ÚTILES Y PLAN LECTOR 2026

## /familia/musical-the-lion-king (family)
Title: Musical The Lion King
- The Lion King Funciones 20 y 21 noviembre
  - 90 años de historia. Una comunidad. Un mismo escenario.
    - EQUIPO Y ELENCO Un musical hecho por nuestra comunidad
    - SÚMATE AL EQUIPO Talleres para apoderados y grupo de apoyos
    - CONTACTO ¿Tienes dudas?
- PDFs (6): ¡Haz click aquí y conoce al equipo y elenco que hacen posible The Lion King!; MÁS INFORMACIÓN DEL TALLER DE MAQUILLAJE TEATRAL.; MÁS INFORMACIÓN DEL TALLER DE CONFECCIÓN DE VESTUARIO.; MÁS INFORMACIÓN DEL TALLER DE CREACIÓN DE CORPÓREOS.; MÁS INFORMACIÓN DE OPERACIONES.; BASES CONCURSO DE VENTA DE ENTRADAS
- Enlaces externos: musical-the-lion-king → https://ticketplus.cl/events/musical-the-lion-king

## /familia/ropero (family)
Title: Ropero
- Ropero
    - ¿Qué es el Ropero?
    - ¿Cómo funciona?
    - Reciclaje, Reparación, Reutilización y Donación:
    - Conéctate con el Ropero
- Enlaces externos: @roperosgc → https://www.instagram.com/roperosgc/

## /formacion-integral/area-de-convivencia-escolar (formation)
Title: Área de Convivencia Escolar
- Área de Convivencia Escolar

## /formacion-integral/area-deportiva (formation)
Title: Área Deportiva
- Área Deportiva
  ▸ CONOCE AL EQUIPO
- PDFs (2): ÁREA DE DEPORTE 2026; HORARIOS DEPORTE 2026

## /formacion-integral/direccion_de_estudios (formation)
Title: Dirección de Estudios
- Dirección de Estudios
    - TAREAS DE LA DIRECCIÓN DE ESTUDIOS
    - OBJETIVOS DE LA DIRECCIÓN DE ESTUDIOS
    - RESPONSABILIDADES DE LA DIRECCIÓN DE ESTUDIOS
    - CAMBRIDGE ENGLISH QUALIFICATIONS
    - CONOCE AL EQUIPO:
  ▸ EQUIPO DIRECCIÓN DE ESTUDIOS
  ▸ JEFES DE ÁREA/COORDINADORES
  ▸ CENTRO DE INFORMACIÓN Y EXTENSIÓN (CIE)
  ▸ ÁREA PSICOPEDAGOGÍA

## /formacion-integral/direccion_de_pastoral (formation)
Title: Dirección de Pastoral
- Dirección de Pastoral
    - PROYECTOS PASTORALES
    - OBJETIVOS
  ▸ CONOCE AL EQUIPO DE DIRECCIÓN PASTORAL

## /formacion-integral/introduccion_aprender_a_conocer (formation)
Title: Introducción
- Aprender a Conocer

## /formacion-integral/introduccion_aprender_a_convivir (formation)
Title: Introducción
- Aprender a Convivir

## /formacion-integral/introduccion_aprender_a_ser_y_trascender (formation)
Title: Introducción
- Aprender a ser y trascender

## /formacion-integral/psicorientacion (formation)
Title: Psicorientación
- Psicorientación

## /unidad/elementary (unit)
Title: Elementary
- Elementary
      - Construyendo los cimientos de su formación integral (pseudo)
  ▸ Dirección y equipo Elementary
  ▸ 1º BÁSICO
  ▸ 2º BÁSICO
  ▸ 3º BÁSICO
  ▸ 4º BÁSICO

## /unidad/infant (unit)
Title: Infant
- Infant
      - El primer paso en la vida escolar de nuestros estudiantes (pseudo)
  ▸ Dirección y equipo Infant
  ▸ PRE KINDER
  ▸ KINDER

## /unidad/junior (unit)
Title: Junior
- Junior
      - Acompañamos en el desarrollo y crecimiento de nuestros estudiantes (pseudo)
  ▸ Dirección y equipo Junior
  ▸ 5º BÁSICO
  ▸ 6º BÁSICO
  ▸ 7º BÁSICO
  ▸ 8º BÁSICO

## /unidad/senior (unit)
Title: Senior
- Senior
      - Consolidando aprendizajes camino a la adultez (pseudo)
  ▸ Dirección y equipo Senior
  ▸ 9°
  ▸ 10°
  ▸ 11°
  ▸ 12°

## Páginas vacías o de plantilla (no usar)
/admision, /aprender-a-conocer, /aprender-a-convivir, /aprender-a-ser-y-trascender, /comunidad, /documentos-institucionales, /equipo-directivo/carolina-lopez, /equipo-directivo/cecilia-fanta, /equipo-directivo/francisca-tagle-v, /equipo-directivo/javier-mascaro, /equipo-directivo/maria-eliana-carrasco, /equipo-directivo/marisol-corrotea, /equipo-directivo/p-pablo-miranda, /equipo-directivo/paula-noemi-callejas, /equipo-directivo/rodrigo-valenzuela, /equipo-directivo/yasna-jelincic, /familia/ropero/img_4371, /familia/ropero/img_4395, /familia/ropero/img_4399, /familia/ropero/img_4571, /formacion-integral, /materia/lenguaje, /materia/matematicas, /nivel/nivel-1, /nivel/nivel-2, /nivel/nivel-3, /the-dragon/dragon-1, /the-dragon/dragon-2, /the-dragon/dragon-3, /the-dragon/dragon-septiembre, /tipo_de_categoria_colegio/historia, /tipo_de_categoria_colegio/proyecto-educativo, /tipo_de_formacion/formacion-para-equipos-directivos-y-docentes, /tipo_de_formacion/formacion-para-tutores
