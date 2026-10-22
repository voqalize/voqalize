# Admisión: vías de ingreso y requisitos

Sources: admision.uahurtado.cl /vias-de-admision/, /admision-via-paes/, /admision-directa/,
/requisitos-de-admision/, /ranking-1000/, /admision-pace/, /programa-de-atraccion-de-talento-pedagogico/,
/continuidad-de-estudios/, simula.uahurtado.cl.

Static description only. Calendars (postulación, matrícula, resultados), score minimums,
ponderaciones and the Ranking 1000 application window change every year: read them live on the
page, and say which year the page itself names. Several of these pages still describe
**Admisión 2026** while the career pages already say 2027.

## Vías de Admisión (`/vias-de-admision/`)
The hub page lists six cards: **Admisión Directa**, **Admisión vía PAES**, **Requisitos de
Admisión**, **Ranking 1000**, **Admisión PACE** and **Simulador de Puntaje**. The header menu
"Vías de Admisión" has the same entries plus Programa de Atracción de Talento Pedagógico.

## Admisión vía PAES (admisión centralizada, `/admision-via-paes/`)
- The regular route: you apply through the national system (DEMRE / Acceso Mineduc) with your PAES
  scores, and the UAH weighs them with each career's **ponderaciones** (NEM, Ranking, Competencia
  Lectora, Competencia Matemática 1, Historia o Ciencias, M2) against a minimum weighted score and a
  minimum average of Lectora + Matemática.
- Each career's weights and minimums are on its page, tab **Requisitos y Aranceles**
  (`#requisitos_carrera-tab`). "10% ó 10%" for Historia / Ciencias means the higher of the two counts.
- The page explains matrícula online in stages: **Etapa 1 Formalización de la Matrícula**,
  **Etapa 2 Pruebas de Competencias Habilitantes (CCHH)**, **Etapa 3 Encuesta de caracterización**,
  **Etapa 4 Tarjeta Nacional Estudiantil (TNE)**, plus sections **PRIMER PERIODO DE MATRÍCULA
  ("POSTULANTE CONVOCADO")**, **SEGUNDO PERIODO ("POSTULANTE EN LISTA DE ESPERA")**,
  **REPOSTULACIÓN**, **RETRACTO** (Ley 19.955: matrícula refunded minus 1% of the annual fee if you
  enrol elsewhere), **MATRÍCULA POSTULANTES DE BECA EXCELENCIA ACADÉMICA (BEA)** and
  **MATRÍCULAS EN EL CASO DE HABER POSTULADO A LA GRATUIDAD**. Its dates are the previous year's.
- **Requisitos Admisión Carreras (`/requisitos-de-admision/`)**: a downloadable table of entry
  scores, plus the rule that a student in the top 10% of their school who misses the minimum average
  may still apply if they reach the minimum weighted score. Where a career weighs both Ciencias and
  Historia, the student chooses; if both were taken, the higher counts.
- **Simulador de Puntaje** (`simula.uahurtado.cl`, linked as "Simula tu puntaje" in the header): asks
  for name, RUT, e-mail and phone before it shows a result, so it is a lead form with reCAPTCHA. Offer
  it; never fill it. Javier can instead compute a weighted score aloud from the live ponderaciones.

## Habilitación pedagógica (any pedagogía)
By Ley 20.903, first-year pedagogy students must meet at least one requirement: a PAES average
(Lectora + M1) at or above a national percentile, a school-grade average in the top part of their
school, or having passed a recognised preparation programme (such as Talento Pedagógico UAH). The
exact thresholds are on `/admision-directa/` ("Habilitación pedagógica") and on each pedagogy career
page: read them live.

## Admisión Directa (`/admision-directa/`)
"Una vía de ingreso alternativa", with limited places, for careers marked as available
(`admision_directa` in carreras.json; Psicología is one that is not). How it works ("¿Cómo postular
por Admisión Directa?"): 1) check you meet one modality's requirements; 2) pre-apply with the form at
the end of the page (it adds a **Vía de Admisión** select); 3) you are contacted by e-mail; 4) you
upload documents, then have an online interview with the career's coordinación académica, who decides.
Every modality requires being interviewed and accepted by the career. Modalities (h4 headings on the
page, each an accordion):
- **NEM 30% o superior**: recent school leavers in the top 30% of their generation by grades.
- **Estudiantes destacados/as**: recent school leavers with a minimum ranking score and either high
  grades in a subject of the area or proven student leadership / social action.
- **Admisión Complementaria para Técnicos Nivel Superior (Ingeniería)**: TNS graduates, with
  recommendation and motivation letters and a minimum TNS grade average.
- **Motivos Vocacionales** and **Cambio interno de carrera**: UAH students changing career.
- **Carreras paralelas**: UAH students starting a second career in parallel.
- **Pruebas internacionales**: Bachillerato Internacional (IB) or Bachillerato General Francés.
- **Enseñanza media en el extranjero**: a foreign certificate equivalent to the Chilean licencia.
- **Otra Universidad con título o grado** (any open career except pedagogías) and **Otra Universidad
  sin título o grado (cambio de universidad)**; **Misma universidad sin título o grado** (readmission).
- **Pueblos originarios**: CONADI certificate plus a minimum ranking score.
- **Deportistas destacadas/os**: see `/deportista-destacado/`.
- **Para Profesionales (continuidad de estudios)**, **Prueba de años anteriores** (PAES/PDT up to
  five years old, meeting the career's minimum) and **Conducencias UAH** (after Bachillerato en
  Humanidades or the Plan común de Ingeniería).
- Section **PROGRAMAS ESPECIALES** describes Pedagogía para Profesionales (vespertino, 4 semesters),
  Contador Público Auditor continuidad (vespertino, 7 trimestres), Bachillerato en Filosofía and the
  three Interpretación Superior careers (Canto, Dirección Coral, Música Antigua; these have
  **Audiciones**).
- The page also has one accordion per career ("Estudia <carrera>", target `#collapse-<slug>`), grouped
  under faculty h3s.

## Admisión PACE (`/admision-pace/`)
Programa de Acceso a la Educación Superior, from the Ministerio de Educación: guaranteed places for
students from vulnerable sectors who meet PACE criteria, without regard to their PAES score. The UAH
works with 19 liceos in the Región Metropolitana (preparation in 3° and 4° medio, then support during
the first four semesters).

## Ranking 1000 (`/ranking-1000/`)
A national quota for school leavers with the very top Ranking de Notas (from municipal, subsidised,
delegated or SLEP schools) whose PAES score is not enough for the centralised system. You apply at
ranking1000.cl, in a window in early January. Sections: "¿Cuándo postular?", "¿Cómo postular?",
"¿Tienes preguntas?". Read the window and score bands live.

## Programa de Atracción de Talento Pedagógico (`/programa-de-atraccion-de-talento-pedagogico/`)
For 4° medio students with a vocation to teach. Recognised by MINEDUC under Ley 20.903. Activities:
3 academias sabatinas presenciales, 3 cursos virtuales, 1 salida pedagógica, 1 asistencia a clase real
de Pedagogía, 2 consejerías vocacionales. Passing it (full attendance in person, 80% of each virtual
course) opens **Admisión Especial** to the 11 pedagogy careers (having taken the PAES) and the
**Beca Talento Pedagógico**. Motivation letter to elijoserdocente@uahurtado.cl.

## Continuidad de Estudios (`/continuidad-de-estudios/`)
Careers for people with previous studies or a first degree, grouped by modality: **Modalidad
presencial** (Ingeniería Civil Industrial para TNS, Ingeniería Civil en Informática para TNS,
Pedagogía para Profesionales), **Modalidad semipresencial** (Contador Público Auditor, vespertino) and
**Modalidad 100% online** (Ingeniería en Gestión de Personas, Comercial, Financiera, de Empresas,
Comercial y Marketing, Logística, de la Innovación y emprendimiento, y Analítica de Datos;
Ingeniería Comercial; Administración Pública; Ingeniería Civil Industrial). "Validación de estudios":
previous training can shorten the career. `/continuidad/` and `/campusb/` redirect here.
