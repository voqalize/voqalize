# Las cuatro unidades: Infant, Elementary, Junior, Senior

Sources: https://saintgeorge.cl/unidad/infant/, https://saintgeorge.cl/unidad/elementary/, https://saintgeorge.cl/unidad/junior/, https://saintgeorge.cl/unidad/senior/ (texto y acordeones); portada sección "Nuestra comunidad" (`#comunidad`); menú Colegio. Datos estructurados en L3/levels.json. Crawl 2026-10-22.

El colegio va de Pre-Kínder a 12°. Cada unidad tiene su página (`/unidad/<slug>/`), con un título h1 (el nombre de la unidad), un subtítulo en negrita, texto, y acordeones (Bootstrap 5, `button.accordion-button`): primero "Dirección y equipo <Unidad>", luego uno por grado con los profesores jefe de cada curso. Los ids de los acordeones (`#collapse_1_1`, `#collapse_2_1`…) se repiten en cada unidad: para abrir uno, busca el botón por su texto en la página actual. Los botones se ven en MAYÚSCULAS (CSS).
Para elegir la unidad por edad o curso del hijo: PK/K → Infant; 1°–4° → Elementary; 5°–8° → Junior; 9°–12° → Senior. Si dan una edad sin curso, pregunta el curso: el sitio no da edades por nivel.
Las tarjetas de la portada (`#comunidad a.card[href*="/unidad/infant/"]`, etc.) también llevan a cada unidad.

## Infant — `/unidad/infant/`
- Subtítulo: "El primer paso en la vida escolar de nuestros estudiantes".
- Pre Kínder y Kínder: "cada nivel cuenta con **siete cursos** de aproximadamente **27 alumnos**, guiados por **dos educadoras**". Aprendizaje "a través del juego, la exploración y la experiencia directa"; "Desde el primer día, nuestros estudiantes se acercan al idioma inglés".
- Acordeones: "Dirección y equipo Infant" (`#collapse_1_1`), "PRE KINDER" (`#collapse_2_1`, cursos PKA–PKG), "KINDER" (`#collapse_3_1`, cursos KKA–KKG). Cada curso lista sus dos educadoras.
- Directora de Infant (Equipo Directivo): Francisca Tagle V.

## Elementary — `/unidad/elementary/`
- Subtítulo: "Construyendo los cimientos de su formación integral".
- "El ciclo de Elementary, que abarca desde 1° hasta 4° Básico". "Cada nivel está compuesto por **cinco cursos** de aproximadamente **36 estudiantes**."
- 1° y 2° Básico: cada curso con una **Headteacher y una Teacher**, que lideran Lenguaje, Matemáticas y **World Studies** (integra Ciencias Naturales y Sociales). 3° y 4° Básico: una **profesora jefe**, que también acompaña la preparación para la **Primera Comunión**.
- Enfoque: **Aprendizaje Basado en Conceptos** y habilidades del siglo XXI (comunicación, colaboración, pensamiento crítico, creatividad, resolución de problemas). Asignaturas complementarias: Inglés, Música, Educación Física, Arte y Tecnología.
- **Educación dual**: "Aproximadamente la mitad de las horas del plan de estudios se desarrollan en este idioma" (inglés).
- Acordeones: "Dirección y equipo Elementary" (`#collapse_1_1`), "1º BÁSICO" … "4º BÁSICO" (`#collapse_2_1` … `#collapse_5_1`), cursos A–E.
- Directora de Elementary: Yasna Jelincic S.

## Junior — `/unidad/junior/`
- Subtítulo: "Acompañamos en el desarrollo y crecimiento de nuestros estudiantes".
- Estudiantes de **5° a 8° básico**, "inicio de la adolescencia". Trabajo coordinado con Psicorientación, Convivencia Escolar y Pastoral. "Contamos con **más de 70 profesionales** que acompañan a los **20 cursos** que conforman este ciclo."
- Acordeones: "Dirección y equipo Junior" (`#collapse_1_1`), "5º BÁSICO" … "8º BÁSICO" (`#collapse_2_1` … `#collapse_5_1`), cursos A–E.
- Directora de Junior: Cecilia Fanta F.

## Senior — `/unidad/senior/`
- Subtítulo: "Consolidando aprendizajes camino a la adultez".
- Ciclo que "permite consolidar los aprendizajes"; "propuesta curricular diversificada". "Son **más de 60 profesionales** los que acompañan a los **20 cursos** que conforman este ciclo." Foco en "la toma de decisiones vocacionales" y la autonomía para "dar el paso a la educación superior".
- Acordeones: "Dirección y equipo Senior" (`#collapse_1_1`), "9°", "10°", "11°", "12°" (`#collapse_2_1` … `#collapse_5_1`), cursos A–E. La página no dice "9° a 12°" en el texto: lo dicen los acordeones.
- Directora de Senior: Marisol Corrotea O.
- Relacionado (menú Familia, en sistemas.saintgeorge.cl, con login): "Postulación opcionales 2027", "Postulación plan diferenciado 11° 2027", "Postulación plan diferenciado 12° 2027". El sitio no explica qué son ni quién postula: derivar al colegio.

## Nombres de profesores
Los acordeones listan profesores jefe y equipos con nombre. No los leas en voz alta por iniciativa propia; si un apoderado pregunta quién es el profesor jefe de un curso, abre el acordeón del grado y deja que lo vea en pantalla.

## Lo que el sitio no dice por unidad
Horarios de entrada/salida, jornada, uniforme por nivel, tamaño exacto de cada curso hoy, idioma de cada asignatura en Junior/Senior.
