# pyright: basic
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Build Colegio Everest's L3 knowledge: the pages of colegioeverest.cl, as data,
read from a real browser, and the catalogue of places on them Javier points at.

The build runs offline on a dev machine; its output is committed and the brain
only ever reads the JSON (the site refuses some countries, India among them, so
the brain could not read it anyway). Network is touched only by ``crawl``;
every page's extraction is cached outside the repository, so ``--offline``
rebuilds from the cache.

colegioeverest.cl is WordPress with GeneratePress (+ GP Premium), Gutenberg and
GenerateBlocks: server-rendered HTML, a full page load per navigation, a header
that scrolls away with the page (not fixed: no scroll offset beyond a small
gap). GenerateBlocks gives every block a stable hash class
(``.gb-container-<8hex>``, ``.gb-grid-column-<8hex>``, ``.gb-button-<8hex>``):
unique within a page, but **reused across pages** (``.gb-grid-column-1f487431``
is the PEI card on /normativas/ and a yearbook card on /anuarios/), so the
catalogue keys every place by page path. Pages that are only paragraphs
(Historia, the cycles' children, the attributes' children) have no hook, so
their places are positional (``.entry-content > :nth-child(n)``, marked
``positional``) and are re-checked on every build. The server is slow and
sometimes stalls for minutes: every load waits for ``domcontentloaded`` only,
with a long timeout and three attempts.

Run from ``voqalize/demos`` on a connection the site answers (Chromium installed
once with ``playwright install chromium``; always headless)::

    uv run --no-project --with playwright --with pypdf python \
        colegioeverest/backend/knowledge/build.py crawl --pdfs
    uv run --no-project --with playwright python \
        colegioeverest/backend/knowledge/build.py crawl --refresh
    uv run --no-project --with pypdf python \
        colegioeverest/backend/knowledge/build.py crawl --offline --pdfs

``crawl`` renders every page of the catalogue below (plus three recent news
posts, to check the post template) and reads the public REST API for the page
list and the news posts. A page already in the cache is not rendered again
unless ``--refresh``. No form is ever filled or submitted, no button pressed.
It writes, next to this file:

- ``L3/anchors.json`` — the catalogue: ``{_meta, header, footer, post, pages:
  {path: {kind, title, header, footer, anchors: [{key, selector, label,
  hidden?, positional?, optional?, href?}]}}}``. Each selector matched exactly
  one laid-out element on the live page, or it is dropped and printed.
  ``hidden`` places are the adapter's own (a form field, a button, the CTA
  links it opens), never offered to the model; ``optional`` ones (the contact
  form's answer line) exist but show only once used, so they are checked for
  existence, not layout. ``header`` and ``footer`` are on every page whose
  ``header``/``footer`` flag is true; ``post`` is the news post template.
- ``L3/pages.json`` — one record per page, the keys the shared loader reads:
  ``{path, url, title, kind, description, modified, sections: [{key, heading,
  text}], headings, documents: [{label, url, near}], links: [{label, url,
  near}], iframes, forms, text}``. A section is a catalogue place with the
  words the element shows (capped). Pages the visitor must not be sent to
  (orphans, the empty Deporte page, test pages) are in it with ``empty:
  true``. The news posts (the most recent :data:`POSTS_KEPT`, from the REST
  API) are pages too, ``kind: "post"``, with ``date``.
- ``L3/site.json`` — the menu (top bar and main menu with dropdowns), the
  footer, the calls to action that leave the site (Alexia application, MS
  Bookings visit, upago, Handing, Lirmi, Buk), the pages not to guide to, the
  REST counts.
- ``L3/documents.json`` — every PDF the pages link, with the pages and labels,
  plus the PDFs the school serves without linking them (Valores 2027, the
  enrolment guide, the 2027 timetable); a one-line note on the ones that
  matter. With ``--pdfs`` each gets ``n_pages`` and ``bytes``; the extracted
  text stays in the local cache.
- ``L3/levels.json`` — the levels a child can enter in 2027, with the
  admission page's age rule and window, the place that shows it, the 2027
  vacancies and the fee band (see :data:`LEVELS`).

It also regenerates ``L2/site-map.md`` and ``L2/noticias.md``. The other L2
topics and L1 are hand-written and not touched.

The cache is ``$XDG_CACHE_HOME/voqalize-colegioeverest`` (``~/.cache`` by
default). If the site answers 403/405 or "Not allowed" three times running,
the crawl stops and writes nothing.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
L3 = HERE / "L3"
SITE = "https://www.colegioeverest.cl"
HOST = "www.colegioeverest.cl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141 Safari/537.36"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "voqalize-colegioeverest"
#: The header is not fixed (it scrolls away); the adapter keeps a small gap.
HEADER_PX = 0
GAP_PX = 20
TEXT_CAP = 1400
#: News posts kept in pages.json, most recent first.
POSTS_KEPT = 40
#: News posts rendered to check the post template's places.
POST_SAMPLES = 3

ADM = "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"


def gb(i: str, kind: str = "container") -> str:
    return f".gb-{kind}-{i}"


def col(i: str) -> str:
    return gb(i, "grid-column")


def btn(i: str) -> str:
    return gb(i, "button")


def nth(n: int) -> str:
    return f".entry-content > :nth-child({n})"


def href(part: str) -> str:
    return f'#main a[href*="{part}"]'


# ─── The catalogue ──────────────────────────────────────────────────────────
# (key, selector, label, flags). Labels are what the model reads; keys are what
# it writes in a cue. Flags: "h" hidden (the adapter's own: must be laid out),
# "o" optional (hidden, may not be laid out until used), "p" positional.

Row = tuple[str, str, str, str]

HEADER: list[Row] = [
    (
        "menu_superior",
        "#secondary-navigation",
        "Barra superior: Home, Información Práctica, Noticias, Conectados, Exalumnos, Lirmi, Alexia, Buk, Pago Online, Contacto",
        "",
    ),
    (
        "menu_principal",
        "#site-navigation",
        "Menú principal: Nuestro Colegio, Nuestro Modelo Educativo, Comunidad Everest, Admisión",
        "",
    ),
    ("menu_nuestro_colegio", "#menu-item-107", "Menú «Nuestro Colegio» (desplegable)", ""),
    (
        "menu_modelo_educativo",
        "#menu-item-284",
        "Menú «Nuestro Modelo Educativo» (desplegable)",
        "",
    ),
    ("menu_comunidad", "#menu-item-400", "Menú «Comunidad Everest» (desplegable)", ""),
    ("menu_admision", "#menu-item-406", "Menú «Admisión»", ""),
    ("menu_informacion_practica", "#menu-item-490", "Barra superior: «Información Práctica»", ""),
    ("menu_noticias", "#menu-item-485", "Barra superior: «Noticias»", ""),
    ("menu_contacto", "#menu-item-1254", "Barra superior: «Contacto»", ""),
    (
        "menu_alexia",
        "#menu-item-5448",
        "Barra superior: «Alexia» (plataforma de apoderados, externa)",
        "",
    ),
    ("menu_pago_online", "#menu-item-3907", "Barra superior: «Pago Online» (upago, externo)", ""),
    ("logo", ".site-logo", "Logo Colegio Everest", ""),
]

FOOTER: list[Row] = [
    ("pie", ".site-footer", "Pie de página", ""),
    (
        "pie_contacto",
        gb("4efcd0b2"),
        "Pie: dirección Camino Real 4518, Lo Barnechea; teléfono (+56) 2 2757 8800; correo; Facebook e Instagram",
        "",
    ),
    ("pie_mapa", gb("9c3eafa7"), "Pie: mapa de Google del colegio", ""),
    (
        "pie_links",
        gb("7240a6ad"),
        "Pie: links relacionados (Oak, Cambridge, Regnum Christi, Red RC) y «Trabaja con nosotros»",
        "",
    ),
]

INNER: list[Row] = [
    ("titulo", "h1.titulo-pagina", "Título de la página", ""),
    ("contenido", ".entry-content", "Contenido de la página", ""),
]

POST: list[Row] = [
    ("titulo", "h1.titulo-pagina", "Título de la noticia", ""),
    ("imagen", ".featured-image", "Imagen de la noticia", ""),
    ("contenido", ".entry-content", "La noticia", ""),
]

HOME: list[Row] = [
    ("hero", ".slider-header__content", "Portada: «Bienvenidos al Everest» (video de fondo)", ""),
    ("hero_admision", ".slider-header__link1", "Botón «Admisión» de la portada", ""),
    ("atributos", gb("bfdf2a01"), "«Nuestros atributos»: los cinco íconos", ""),
    ("atributo_catolico", col("bef6edef"), "Atributo «Colegio Católico»", ""),
    ("atributo_formacion", col("9d7fd36f"), "Atributo «Formación Integral de Excelencia»", ""),
    (
        "atributo_acompanamiento",
        col("6bb98930"),
        "Atributo «Acompañamiento Centrado en la Persona»",
        "",
    ),
    ("atributo_apostoles", col("dbe684e6"), "Atributo «Apóstoles al Servicio de los demás»", ""),
    ("atributo_comunidad", col("d5412194"), "Atributo «Comunidad Educativa»", ""),
    (
        "treinta_anos",
        gb("9b1f91a9"),
        "«Ya llevamos 30 años de vida», con video y botón «Conocer más»",
        "",
    ),
    ("treinta_anos_video", col("2347db21"), "Video «30 Años Colegio Everest» (YouTube)", ""),
    ("noticias", gb("25f8ede8"), "«Noticias»: carrusel de las últimas noticias", ""),
    ("noticias_carrusel", ".slider-noticias", "Carrusel de noticias (tres a la vista)", ""),
    (
        "noticias_anterior",
        ".slider-noticias .slick-prev",
        "Flecha «anterior» del carrusel de noticias",
        "h",
    ),
    (
        "noticias_siguiente",
        ".slider-noticias .slick-next",
        "Flecha «siguiente» del carrusel de noticias",
        "h",
    ),
    ("noticias_todas", href("/noticias/"), "Link «Leer todas las noticias»", ""),
    (
        "destacados",
        gb("d35e15b6"),
        "«Destacados»: Handing, Admisión Bambolino 2027, app de canchas, tour 360°, energía solar",
        "",
    ),
    (
        "destacado_handing",
        col("d76c4564"),
        "Destacado: «Toda la información práctica… en Documentos útiles de Handing»",
        "",
    ),
    ("destacado_admision", col("905e86bc"), "Destacado: «Admisión Bambolino 2027»", ""),
    (
        "destacado_canchas",
        col("71f4913f"),
        "Destacado: arriendo de canchas con la app «Colegio Everest»",
        "",
    ),
    ("destacado_tour", col("4ede0fb6"), "Destacado: «Tour virtual 360°»", ""),
    (
        "destacado_solar",
        col("75b8e931"),
        "Destacado: video «Colegio Everest se ilumina con energía solar»",
        "",
    ),
]

ADMISION: list[Row] = [
    (
        "intro",
        gb("1c045dbd"),
        "Introducción: somos parte de la Red de Colegios Regnum Christi, con video",
        "",
    ),
    (
        "intro_video",
        gb("a7d1f177"),
        "Video «Colegio Everest, parte de la Red internacional de colegios RC»",
        "",
    ),
    ("fechas", gb("27bcc394"), "«Fechas de Postulación»", ""),
    ("fechas_niveles", gb("a372b43a"), "Las cinco tarjetas de fechas por nivel", ""),
    (
        "fecha_prekinder",
        gb("db32d6d8"),
        "Fechas: Prekínder 2027 (4 años cumplidos al 31 de marzo 2027)",
        "",
    ),
    (
        "fecha_playgroup",
        gb("49e6a090"),
        "Fechas: Playgroup 2027 (1 al 15 de abril de 2026; 3 años)",
        "",
    ),
    (
        "fecha_kinder_iv_medio",
        gb("0339c204"),
        "Fechas: Kínder a IV medio 2027 (julio a septiembre 2026)",
        "",
    ),
    (
        "fecha_bambolino",
        gb("d9eaa29f"),
        "Fechas: Mini Bambolino y Bambolino 2027 (1° al 20 de octubre 2026)",
        "",
    ),
    (
        "fecha_mini_bambolino_2s",
        gb("62f080f8"),
        "Fechas: Mini Bambolino II semestre 2026 (1 al 15 de mayo de 2026)",
        "",
    ),
    ("pasos", gb("a875bd50"), "«Pasos de Postulación»", ""),
    ("pasos_grilla", gb("716a5e69"), "Los ocho pasos de postulación", ""),
    ("paso_1_conoce", gb("5cd7e937"), "Paso 1: Conoce nuestro proyecto educativo", ""),
    (
        "paso_2_prepara",
        gb("00b03be9"),
        "Paso 2: Prepara los documentos digitales (carta a la directora, certificado de nacimiento)",
        "",
    ),
    (
        "paso_3_postula",
        gb("2dfc21a5"),
        "Paso 3: Postula online (botón «Postulación ONLINE», Alexia)",
        "",
    ),
    (
        "paso_4_visita",
        gb("a8e15b22"),
        "Paso 4: Visita nuestro colegio (botón «Agenda AQUÍ», Microsoft Bookings)",
        "",
    ),
    ("paso_5_entrevista", gb("0ba9a577"), "Paso 5: Entrevista de familia", ""),
    ("paso_6_admission_day", gb("1357fad0"), "Paso 6: Admission Day (valor proceso $45.000)", ""),
    ("paso_7_resultados", gb("40f29001"), "Paso 7: Entrega de resultados", ""),
    ("paso_8_incorporacion", gb("b571284d"), "Paso 8: Incorporación (7 días para matricular)", ""),
    (
        "boton_pei",
        href("proyecto-educativo-colegio-everest.pdf"),
        "Botón «Proyecto Educativo» del paso 1 (PDF)",
        "",
    ),
    (
        "cta_postular",
        href("FormularioMatriculacion"),
        "Botón «Postulación ONLINE» (abre Alexia en pestaña nueva)",
        "h",
    ),
    (
        "cta_agendar_visita",
        href("bookings.cloud.microsoft"),
        "Botón «Agenda AQUÍ» (abre Microsoft Bookings en pestaña nueva)",
        "h",
    ),
    (
        "botones_documentos",
        gb("5d80ff91"),
        "Botones «Vacantes 2027», «Resultados de admisión 2026», «Valores 2026»",
        "",
    ),
    ("vacantes", btn("30d0568a"), "Botón «Vacantes 2027» (PDF)", ""),
    ("valores", btn("2580295e"), "Botón «Valores 2026» (PDF)", ""),
    ("ciclos", gb("dcf0a5f3"), "«Conoce Nuestros Ciclos»", ""),
    ("ciclo_i", gb("21d572ad"), "I Ciclo \u2013 Preschool (Bambolino a Kinder)", ""),
    ("ciclo_ii", gb("c62f1960"), "II Ciclo (1° a 6° básico)", ""),
    ("ciclo_iii", gb("28b33524"), "III Ciclo (7° a IV medio)", ""),
    (
        "encargada_admision",
        gb("6c360a28"),
        "Encargada de Admisión: María Ignacia Fuentes, correo y teléfono",
        "",
    ),
    ("telefono_admision", href("tel:+56227578804"), "Teléfono de admisión +56 2 2757 8804", "h"),
]

CONTACTO: list[Row] = [
    (
        "formulario",
        "#wpcf7-f1250-p1251-o1",
        "Formulario de contacto (Nombre, correo, asunto, mensaje)",
        "",
    ),
    (
        "field_nombre",
        '#wpcf7-f1250-p1251-o1 input[name="your-name"]',
        "Campo Nombre (requerido)",
        "h",
    ),
    (
        "field_email",
        '#wpcf7-f1250-p1251-o1 input[name="your-email"]',
        "Campo Correo (requerido)",
        "h",
    ),
    ("field_asunto", '#wpcf7-f1250-p1251-o1 input[name="your-subject"]', "Campo Asunto", "h"),
    ("field_mensaje", '#wpcf7-f1250-p1251-o1 textarea[name="your-message"]', "Campo Mensaje", "h"),
    ("captcha", "#wpcf7-f1250-p1251-o1 .wpcf7-turnstile", "Verificación Cloudflare Turnstile", "h"),
    ("submit", "#wpcf7-f1250-p1251-o1 .wpcf7-submit", "Botón «Enviar»", "h"),
    (
        "respuesta",
        "#wpcf7-f1250-p1251-o1 .wpcf7-response-output",
        "Línea de respuesta del formulario (aparece al enviar)",
        "o",
    ),
]

AMBIENTES: list[Row] = [
    (
        "intro",
        gb("ee7b0614"),
        "«Comprometidos con la cultura del cuidado y la prevención» y el equipo",
        "",
    ),
    (
        "indice",
        gb("2cd099cd"),
        "Índice: Protocolos, Formulario de denuncias, Certificación Ceprome, Documentos",
        "",
    ),
    ("protocolos", "#as-protocolos", "Protocolos de Actuación: los cinco principios", ""),
    ("activacion", gb("20080fa6"), "Activación del protocolo AS (quién lo activa)", ""),
    ("etapas", gb("9d65fe96"), "Etapas de nuestros Protocolos", ""),
    ("etapa_deteccion", col("d0ad2074"), "Etapa «Detección»", ""),
    ("etapa_acciones", col("ca8a68bf"), "Etapa «Acciones inmediatas»", ""),
    ("etapa_apoyo", col("f105aae0"), "Etapa «Apoyo y seguimiento»", ""),
    ("etapa_cierre", col("82e95c4f"), "Etapa «Cierre»", ""),
    ("denuncias", "#as-formulario", "Formulario de Denuncias (solo mostrar, nunca llenar)", ""),
    ("ceprome", "#as-ceprome", "Certificación Ceprome (noviembre 2025) y sus 8 estándares", ""),
    ("documentos", "#as-documentos", "Documentos y links de interés", ""),
    ("pdf_codigo", btn("a5d6eed3"), "Código de Promoción de Ambientes Sanos y Seguros (PDF)", ""),
    ("pdf_informe_ceprome", btn("1deaee36"), "Informe de certificación Ceprome (PDF)", ""),
    ("pdf_diploma_ceprome", btn("4ad16c3b"), "Diploma de certificación Ceprome (PDF)", ""),
    ("link_as_regnum", btn("d346e80a"), "Sitio web Ambientes Seguros del Regnum Christi Chile", ""),
    ("link_ceprome", btn("f0101964"), "Sitio web Ceprome Latinoamérica", ""),
]

INFRAESTRUCTURA: list[Row] = [
    (
        "texto",
        nth(1),
        "Las instalaciones: 8 multicanchas, pista atlética, canchas, bibliotecas, laboratorios, capillas, auditorios",
        "p",
    ),
    ("galeria", ".slider-for", "Galería de fotos del colegio (20 fotos)", ""),
    ("galeria_miniaturas", ".slider-nav", "Miniaturas de la galería", ""),
    ("galeria_anterior", ".slider-for .slick-prev", "Flecha «anterior» de la galería", "h"),
    ("galeria_siguiente", ".slider-for .slick-next", "Flecha «siguiente» de la galería", "h"),
]

INFO_PRACTICA: list[Row] = [
    (
        "intro",
        gb("d6482b48"),
        "«Estimadas familias: bienvenidas a la sección de Información Práctica»",
        "",
    ),
    ("tarjetas", gb("1e1dda51"), "Las 14 tarjetas de información práctica", ""),
    ("fechas_importantes", col("75b8b7b9"), "Tarjeta «Fechas importantes 2026» (imagen)", ""),
    ("lost_found", col("5b4c08c3"), "Tarjeta «Lost & Found»", ""),
    (
        "calendario_academico",
        col("7fd91661"),
        "Tarjeta «Calendario académico mensual» (dice que los calendarios están en Handing)",
        "",
    ),
    ("comite_convivencia", col("c69390e0"), "Tarjeta «Activación Comité de Convivencia» (PDF)", ""),
    ("casino", col("c373b60f"), "Tarjeta «Casino» (imagen)", ""),
    ("textos_utiles", col("23b2f3ca"), "Tarjeta «Textos y útiles escolares»", ""),
    ("compra_uniformes", col("73016e16"), "Tarjeta «Compra uniformes escolares»", ""),
    ("uniforme", col("d3739ab7"), "Tarjeta «Uniforme»", ""),
    ("arriendo_canchas", col("fed4a071"), "Tarjeta «Arriendo de canchas»", ""),
    ("enfermeria", col("97fcbbfd"), "Tarjeta «Enfermería»", ""),
    ("portal_pago", col("5fe7ddca"), "Tarjeta «Portal de pago fácil» (upago, externo)", ""),
    ("atencion_familias", col("04667202"), "Tarjeta «Atención de familias»", ""),
    ("instructivo_alexia", col("57f4c7ff"), "Tarjeta «Instructivo Alexia» (PDF)", ""),
    ("bus_car", col("83c039ca"), "Tarjeta «Bus-Car»", ""),
]

NORMATIVAS: list[Row] = [
    ("reglamentos", gb("6caf6aea"), "«Reglamentos y Estatutos»", ""),
    (
        "reglamentos_grilla",
        gb("0787cebc"),
        "Reglamentos: PEI, Promoción y Evaluación 2027, disciplina formativa, Formación Ciudadana, Ideario, RICE 2027, Fondo de Becas, biblioteca",
        "",
    ),
    ("protocolos", gb("10add672"), "«Protocolos»", ""),
    ("protocolos_grilla", gb("e32135b5"), "Los 14 protocolos", ""),
    ("comites", gb("9d50a6b0"), "«Comités»", ""),
    ("comites_grilla", gb("e94240d5"), "Comité de Convivencia Escolar", ""),
    ("pdf_pei", col("1f487431"), "Proyecto Educativo Institucional (PDF)", ""),
    (
        "pdf_promocion_evaluacion",
        col("3a84f04d"),
        "Reglamento de Promoción y Evaluación Escolar 2027 (PDF)",
        "",
    ),
    (
        "pdf_disciplina_formativa",
        col("4fe4c2bf"),
        "Principios y pautas de disciplina formativa RC (PDF)",
        "",
    ),
    ("pdf_formacion_ciudadana", col("ddef68b3"), "Plan de Formación Ciudadana (PDF)", ""),
    ("pdf_ideario", col("9c16919f"), "Ideario Colegios RC (PDF)", ""),
    (
        "pdf_rice",
        col("6d01c50a"),
        "Reglamento Interno de Convivencia Escolar (RICE) 2027 (PDF)",
        "",
    ),
    ("pdf_fondo_becas", col("d9e4e21a"), "Reglamento del Fondo Solidario de Becas (PDF)", ""),
    ("pdf_biblioteca", col("4c364dbf"), "Reglamento biblioteca (PDF)", ""),
    (
        "pdf_codigo_ambientes",
        col("f9474967"),
        "Código de promoción de ambiente sano y seguro (PDF)",
        "",
    ),
    ("pdf_pise", col("ae78a577"), "Plan Integral de Seguridad Escolar (PISE) (PDF)", ""),
    (
        "pdf_medidas_extraordinarias",
        col("38f3426a"),
        "Plan medidas extraordinarias Ley 21290 (PDF)",
        "",
    ),
    ("pdf_manual_gimnasio", col("fafb6784"), "Manual de procedimientos gimnasio (PDF)", ""),
    (
        "pdf_trabajo_colaborativo",
        col("4ce88d77"),
        "Protocolo trabajo colaborativo III ciclo (PDF)",
        "",
    ),
    ("pdf_alcohol_drogas", col("d8edf2fb"), "Prevención del consumo de alcohol y drogas (PDF)", ""),
    (
        "pdf_entrada_salida",
        col("78af8c70"),
        "Protocolo entrada y salida del recinto escolar (PDF)",
        "",
    ),
    (
        "pdf_nee",
        col("0fac22ff"),
        "Programa de apoyo a alumnos con necesidades educativas especiales (PDF)",
        "",
    ),
    ("pdf_decalogo_deportista", col("3ec32805"), "Decálogo deportista Everest (PDF)", ""),
    (
        "pdf_acoso_laboral",
        col("842999ce"),
        "Protocolo de prevención del acoso sexual, laboral y violencia en el trabajo (PDF)",
        "",
    ),
    (
        "pdf_apoyo_deportistas",
        col("1b4b88de"),
        "Plan de apoyo académico para deportistas seleccionados (PDF)",
        "",
    ),
    ("pdf_protocolo_acompanamiento", col("65277e30"), "Protocolo de acompañamiento (PDF)", ""),
    ("pdf_viajes", col("c78695d8"), "Protocolo por viaje (PDF)", ""),
    (
        "pdf_intercambio",
        col("40b86d7e"),
        "Protocolo y reglamento para intercambios escolares (PDF)",
        "",
    ),
    ("pdf_comite_que_es", col("e782a30b"), "¿Qué es el Comité de Convivencia Escolar? (PDF)", ""),
    ("pdf_comite_acta", col("986f50ba"), "Acta constitución Comité de Convivencia (PDF)", ""),
]

#: path → (kind, rows). Inner pages get INNER in front; every page has the
#: header and the footer.
PAGES: dict[str, tuple[str, list[Row]]] = {
    "/": ("home", HOME),
    ADM: ("admission", ADMISION),
    f"{ADM}resultados-admision/": (
        "admission_results",
        [
            ("resultados_2022", gb("f98e2f9e"), "Resultados de admisión 2022 (PDF, antiguos)", ""),
            (
                "nota_2023",
                gb("9e6d1ea0"),
                "Nota: los resultados 2023 se entregaron por mail y en la oficina de Admisión",
                "",
            ),
        ],
    ),
    "/contacto/": ("contact", CONTACTO),
    "/trabaja-con-nosotros/": (
        "jobs",
        [
            (
                "formulario",
                "#wpcf7-f1217-p1218-o1",
                "Formulario «Trabaja con nosotros» (CV; solo mostrar)",
                "",
            ),
        ],
    ),
    "/nuestro-colegio/nuestra-mision/": (
        "school",
        [
            (
                "pdf_ideario",
                btn("63202ab0"),
                "Botón «Descarga el Ideario de los colegios RC» (PDF)",
                "",
            ),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/": (
        "school",
        [
            ("catolico", gb("aa9be48b"), "Colegio Católico", ""),
            ("formacion", gb("eed9528a"), "Formación Integral de Excelencia", ""),
            ("acompanamiento", gb("8a1c6ee6"), "Acompañamiento Centrado en la Persona", ""),
            ("apostoles", gb("dc1eda32"), "Apóstoles al Servicio de los demás", ""),
            ("comunidad", gb("994f613b"), "Comunidad Educativa", ""),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/colegio-catolico/": (
        "attribute",
        [
            (
                "intro",
                nth(1),
                "«Nuestro colegio ofrece actividades que… promueven la vida espiritual»",
                "p",
            ),
            (
                "lista",
                nth(2),
                "Oración, comunión diaria, confesión, Misas, la Virgen María, sacramentos, religión",
                "p",
            ),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/formacion-integral-de-excelencia/": (
        "attribute",
        [
            ("intro", nth(1), "Cita del Ideario: inteligencia, voluntad y afectividad", "p"),
            ("integer_homo", nth(2), "«Integer Homo e Integra Mulier»", "p"),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/acompanamiento-centrado-en-la-persona/": (
        "attribute",
        [
            ("intro", nth(1), "El acompañamiento al estilo de Jesucristo", "p"),
            (
                "medios",
                nth(4),
                "Medios: encargadas de familia, profesor jefe, disciplina formativa, sacerdotes y consagradas, psicología",
                "p",
            ),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/apostoles-al-servicio-de-los-demas/": (
        "attribute",
        [
            ("intro", nth(1), "«Nuestro colegio promueve la vida apostólica mediante:»", "p"),
            (
                "lista",
                nth(2),
                "Pastoral, Participación Social, orientación, programa COES, amistad",
                "p",
            ),
        ],
    ),
    "/nuestro-colegio/nuestros-atributos/comunidad-educativa/": (
        "attribute",
        [
            ("intro", nth(1), "«En la comunidad educativa todos contribuyen a la formación»", "p"),
            (
                "lista",
                nth(3),
                "Las familias, los alumnos, los profesores, la directora y el equipo directivo",
                "p",
            ),
        ],
    ),
    "/nuestro-colegio/historia/": (
        "school",
        [
            ("fundacion_1995", nth(1), "1995: se funda con 75 alumnos en el Colegio Cumbres", "p"),
            ("camino_real_1997", nth(2), "1997: primera piedra en Camino Real, La Dehesa", "p"),
            ("edificio_1998", nth(3), "1998: el edificio que hoy ocupa Preescolar", "p"),
            (
                "primera_generacion_2008",
                nth(4),
                "2008: primera promoción; 17 generaciones desde entonces",
                "p",
            ),
            (
                "direccion_unica_2016",
                nth(5),
                "2016: preescolar, masculino y femenino bajo una sola Dirección",
                "p",
            ),
            ("gimnasio_2022", nth(6), "2022: se inaugura el gimnasio", "p"),
            (
                "hoy",
                nth(7),
                "Hoy: casi 2000 alumnos, de Mini Bambolino a IV Medio; 30 años en 2025",
                "p",
            ),
        ],
    ),
    "/nuestro-colegio/equipo-directivo/": (
        "school",
        [
            (
                "equipo",
                gb("b017e162"),
                "Equipo directivo: directora, subdirectora, UTP, coordinadoras, administración",
                "",
            ),
        ],
    ),
    "/nuestro-colegio/infraestructura/": ("school", INFRAESTRUCTURA),
    "/nuestro-colegio/normativas/": ("documents", NORMATIVAS),
    "/nuestro-colegio/colegios-rc/": (
        "school",
        [
            ("intro", gb("6f9495c5"), "La Red de Colegios Regnum Christi", ""),
            ("particulares", gb("2323dbd3"), "Colegios particulares de la red (seis)", ""),
            (
                "fundacion",
                gb("bf4aff4a"),
                "Colegios Fundación Mano Amiga y el particular subvencionado",
                "",
            ),
        ],
    ),
    "/tour-virtual/": (
        "tour",
        [
            ("tour", gb("bfa84f54"), "Tour virtual 360° del colegio", ""),
        ],
    ),
    "/nuestro-colegio/ambientes-seguros/": ("safeguarding", AMBIENTES),
    "/nuestro-colegio/protocolos-de-ambientes-seguros/": (
        "safeguarding",
        [
            ("esquema", gb("935b06da"), "Esquema de los protocolos: casos 1, 2 y 3", ""),
        ],
    ),
    "/nuestro-modelo-educativo/proyecto-educativo/": (
        "education",
        [
            (
                "adhesion",
                gb("90463eec"),
                "«Adhesión al proyecto educativo del colegio» (requisito para postular)",
                "",
            ),
        ],
    ),
    "/nuestro-modelo-educativo/nuestro-modelo-formativo/": (
        "education",
        [
            ("metodologias", gb("987cf4c3"), "«Metodologías Activas»", ""),
            (
                "ambientes_aprendizaje",
                gb("7f5bcdde"),
                "Ambientes de Aprendizaje y las demás metodologías",
                "",
            ),
        ],
    ),
    "/nuestro-modelo-educativo/evertics/": (
        "education",
        [
            ("vision", gb("93ef716a"), "«Nuestra visión tecnológica» (estándares ISTE)", ""),
            ("inspira", gb("8ad1ca07"), "Inspira, Imagina, Impacta", ""),
        ],
    ),
    "/nuestro-modelo-educativo/ingles-intensivo/": (
        "education",
        [
            (
                "intro",
                gb("a795356c"),
                "Inglés: 4 habilidades, Marco Común Europeo, B2 al egresar",
                "",
            ),
            (
                "ruta",
                gb("10329c7b"),
                "Ruta de progreso: 4° A1, 6° A2, 8° B1, III° medio B2; Cambridge FCE y CAE; The Masters",
                "",
            ),
            ("certificaciones", gb("c73c9213"), "Logos de certificaciones", ""),
        ],
    ),
    "/nuestro-modelo-educativo/ciclos/": (
        "education",
        [
            ("ciclo_i", gb("227a8f84"), "I ciclo \u2013 Preschool (Bambolino a Kinder)", ""),
            ("ciclo_ii", gb("942bbb8f"), "II ciclo (1º a 6º básico)", ""),
            ("ciclo_iii", gb("0a1fed7d"), "III ciclo (7º básico a IV medio)", ""),
        ],
    ),
    "/nuestro-modelo-educativo/ciclos/i-ciclo-preescolar/": (
        "cycle",
        [
            ("intro", nth(1), "Educar con evidencia científica de cómo aprenden los niños", "p"),
            ("conscious_discipline", nth(3), "Programa socioemocional Conscious Discipline", "p"),
            ("juego", nth(4), "El juego libre y dirigido", "p"),
            (
                "ingles",
                nth(7),
                "Inglés: en Playgroup, Prekínder y Kínder las clases son en inglés casi en su totalidad; Jolly Phonics",
                "p",
            ),
        ],
    ),
    "/nuestro-modelo-educativo/ciclos/ii-ciclo/": (
        "cycle",
        [
            ("mision", nth(1), "Misión del II ciclo", "p"),
            ("estrategias", nth(2), "Estrategias innovadoras y estilos de aprendizaje", "p"),
        ],
    ),
    "/nuestro-modelo-educativo/ciclos/iii-ciclo/": (
        "cycle",
        [
            ("mision", nth(1), "Misión del III ciclo", "p"),
            ("valores", nth(2), "Responsabilidad, autonomía, sana convivencia y servicio", "p"),
        ],
    ),
    "/nuestro-modelo-educativo/ciclos/iv-ciclo/": (
        "cycle",
        [
            ("mision", nth(1), "Misión del IV ciclo (página antigua, fuera del menú)", "p"),
            (
                "ingles",
                nth(5),
                "Inglés: First Certificate en III°, intercambios Oak, The Masters, Stanford, Oxford y Yale",
                "p",
            ),
            (
                "selecciones",
                nth(7),
                "Selecciones: fútbol, básquetbol, atletismo, voleibol, gimnasia artística y hockey",
                "p",
            ),
            ("participacion_social", nth(8), "Programa de participación social", "p"),
        ],
    ),
    "/informacion-practica/": ("info", INFO_PRACTICA),
    "/informacion-practica/lost-found/": (
        "info",
        [
            ("intro", gb("e0deb280"), "Lost & Found: el cuidado de las pertenencias", ""),
            (
                "documentos",
                gb("1e1dda51"),
                "Protocolo, listado y valores de uniformes usados (PDF)",
                "",
            ),
            (
                "contacto",
                gb("9e5a71f3"),
                "Contacto: Astrid Bascuñán, lostfound@colegioeverest.cl",
                "",
            ),
        ],
    ),
    "/informacion-practica/casino/": (
        "info",
        [
            (
                "valores",
                gb("48918139"),
                "Casino Aramark: valores 2025, registro, contacto, información importante",
                "",
            ),
            ("pdf_aramark", gb("8afb06c9"), "«Información Aramark Colegio Everest 2025» (PDF)", ""),
        ],
    ),
    "/textos-y-utiles-escolares/": (
        "info",
        [
            ("listas", gb("768b6fbc"), "Las tres listas de textos y útiles 2026", ""),
            (
                "pdf_preschool",
                col("7a95a0a2"),
                "«Preschool (Mini Bambolino a Kínder)»: lista de materiales 2026 (PDF)",
                "",
            ),
            (
                "pdf_ii_ciclo",
                col("438e8c71"),
                "«II Ciclo (1° a 6° Básico)»: textos y útiles 2026 (PDF)",
                "",
            ),
            (
                "pdf_iii_ciclo",
                col("97a7f9c9"),
                "«III Ciclo (7° Básico a IV Medio)»: textos y útiles 2026 (PDF)",
                "",
            ),
        ],
    ),
    "/informacion-practica/cima/": (
        "info",
        [
            ("tiendas", gb("f58eb968"), "Dónde comprar uniformes: Tienda CIMA y Trenino", ""),
        ],
    ),
    "/informacion-practica/uniforme-del-colegio/": (
        "info",
        [
            ("tarjetas", gb("768b6fbc"), "Uniforme: tarjetas por ciclo", ""),
            (
                "pdf_preschool",
                col("7a95a0a2"),
                "Tarjeta «Preschool» (enlaza la lista de materiales 2026)",
                "",
            ),
            ("pdf_ii_iii", col("438e8c71"), "«II y III Ciclo»: uso del uniforme 2026 (PDF)", ""),
        ],
    ),
    "/informacion-practica/arriendo-de-canchas/": (
        "info",
        [
            ("video", gb("48610504"), "Cómo reservar cancha en la app (video)", ""),
            ("pdf_paso_a_paso", href("Guia-paso-a-paso"), "Guía «paso a paso» de la app (PDF)", ""),
            ("app_ios", col("f57b944d"), "App Canchas Everest en App Store", ""),
            ("app_android", col("4e64dcb0"), "App Canchas Everest en Google Play", ""),
        ],
    ),
    "/informacion-practica/enfermeria/": (
        "info",
        [
            (
                "documentos",
                gb("446a9566"),
                "Reglamento, protocolo DEA y protocolos de enfermería (PDF)",
                "",
            ),
        ],
    ),
    "/informacion-practica/atencion-de-familias/": (
        "info",
        [
            ("encargadas", gb("e4a5d0c6"), "Encargadas de Familia: nombres y correos", ""),
        ],
    ),
    "/informacion-practica/bus-car/": (
        "info",
        [
            ("texto", nth(1), "Servicio BUS-CAR de la Municipalidad de Lo Barnechea", "p"),
        ],
    ),
    "/informacion-practica/comunicados/": (
        "info",
        [
            ("texto", nth(1), "Cómo se comunica el colegio: redes sociales", "p"),
        ],
    ),
    "/informacion-practica/conectados/": ("info", []),
    "/calendario-mensual-y-fechas-importantes/": (
        "info",
        [
            (
                "documentos",
                gb("ccc2df1c"),
                "Calendario mensual, calendario académico y fechas importantes (PDF antiguos, 2024\u20132025)",
                "",
            ),
        ],
    ),
    "/noticias/": (
        "news",
        [
            ("siguiente", btn("f369558d"), "Botón «Siguente» de la lista de noticias", ""),
        ],
    ),
    "/comunidad-everest/centro-de-alumnos/": (
        "community",
        [
            ("texto", nth(1), "La finalidad del Centro de Alumnos", "p"),
        ],
    ),
    "/comunidad-everest/centro-de-padres/": (
        "community",
        [
            (
                "documentos",
                gb("56442950"),
                "Protocolo de fiestas y Reglamento del Fondo Solidario de Becas",
                "",
            ),
            (
                "pdf_fondo_becas",
                col("dcd481ed"),
                "Reglamento del Fondo Solidario de Becas (PDF)",
                "",
            ),
        ],
    ),
    "/comunidad-everest/ex-alumnos/": (
        "community",
        [
            (
                "generacion_2013",
                gb("37f79248"),
                "Generación 2013, celebración 10 años de egresados",
                "",
            ),
            ("comunidad", gb("1abb04c8"), "La comunidad de exalumnos: 2.591 egresados", ""),
            (
                "actualiza_datos",
                btn("892e31ba"),
                "Botón «ACTUALIZA TUS DATOS» (encuesta externa)",
                "",
            ),
            ("destacados", gb("afab8850"), "Destacados de exalumnos (carrusel)", ""),
            (
                "secciones",
                gb("875af3ae"),
                "Anuarios, Liga exalumnos, Noticias, Entrevistas, Eventos",
                "",
            ),
        ],
    ),
    "/comunidad-everest/ex-alumnos/entrevistas/": (
        "community",
        [("lista", gb("276b7712"), "Entrevistas a exalumnos", "")],
    ),
    "/comunidad-everest/ex-alumnos/eventos/": (
        "community",
        [("lista", gb("8fc05116"), "Eventos de exalumnos", "")],
    ),
    "/comunidad-everest/ex-alumnos/noticiasexalumnos/": (
        "community",
        [("lista", gb("92ad96c1"), "Noticias de exalumnos", "")],
    ),
    "/comunidad-everest/anuarios/": (
        "community",
        [("anuarios", gb("61a88651"), "Anuarios 2018 a 2023", "")],
    ),
    **{f"/comunidad-everest/anuarios/anuario-{y}/": ("yearbook", []) for y in range(2018, 2024)},
}

#: Pages the site serves that a visitor is never sent to, and why.
UNGUIDED: dict[str, str] = {
    "/nuestro-colegio/": "página padre vacía (el menú solo abre el desplegable)",
    "/nuestro-modelo-educativo/": "página padre vacía",
    "/comunidad-everest/": "página padre vacía",
    "/nuestro-modelo-educativo/deporte/": "está en el menú pero la página está vacía",
    "/instagram/": "página huérfana con un feed de Instagram roto",
    "/prueba-resultados-26gtk1/": "página de prueba",
    "/comunidad-everest/ex-alumnos-antigua/": "versión antigua de Exalumnos, fuera del menú",
    "/entrega-resultados-admision-2027/": "consulta de resultados por RUT, sin enlace en el sitio: nunca se llena",
}

#: The CTAs that leave the site; Javier only opens them in a new tab.
CTAS: dict[str, dict[str, str]] = {
    "postulacion": {
        "label": "Postulación ONLINE (Alexia)",
        "match": "FormularioMatriculacion",
        "place": f"{ADM}#cta_postular",
        "note": "Formulario de postulación en Alexia: pide RUN y datos del postulante. Solo se abre; nunca se llena.",
    },
    "visita": {
        "label": "Agenda AQUÍ (Microsoft Bookings)",
        "match": "bookings.cloud.microsoft",
        "place": f"{ADM}#cta_agendar_visita",
        "note": "Agenda de visitas con la Encargada de Admisión. Solo se abre.",
    },
    "alexia": {
        "label": "Alexia (plataforma de apoderados)",
        "match": "colegioeverest.alexiaeducl.com",
        "exclude": "FormularioMatriculacion",
        "place": "header#menu_alexia",
        "note": "Login de apoderados; también donde se hace la matrícula 2027 (Instructivo Matrícula).",
    },
    "pago_online": {
        "label": "Pago Online (upago)",
        "match": "pay.upago.cl",
        "place": "header#menu_pago_online",
        "note": "Portal de pago. Solo se abre.",
    },
    "handing": {
        "label": "Handing",
        "match": "handing.co",
        "place": "/#destacado_handing",
        "note": "App de comunicación con las familias; los calendarios académicos están en sus Documentos útiles.",
    },
    "lirmi": {
        "label": "Lirmi",
        "match": "lirmi.com",
        "place": "header#menu_superior",
        "note": "Login.",
    },
    "buk": {
        "label": "Buk",
        "match": "buk.cl",
        "place": "header#menu_superior",
        "note": "Portal de colaboradores.",
    },
}

#: PDFs on the school's server that no page links.
UNLINKED_PDFS: list[tuple[str, str]] = [
    (
        "/wp-content/uploads/2026/10/Ver-valores-de-matricula-y-colegiaturas-2027_.pdf",
        "Valores 2027 (UF): matrícula y colegiatura por nivel, descuentos familia numerosa",
    ),
    (
        "/wp-content/uploads/2026/10/Instructivo-Matricula.pdf",
        "Proceso de matrícula 2027 paso a paso en Alexia",
    ),
    (
        "/wp-content/uploads/2026/09/Nuevos_horarios_2027.pdf",
        "Nuevos horarios de salida 2027, 1° básico a IV medio",
    ),
]

#: One line on the PDFs that matter, by a piece of their file name.
DOC_NOTES: dict[str, str] = {
    "VACANTES-EVEREST-2027": "Vacantes 2027 por nivel (con edad requerida en preescolar y vacantes prioritarias NEEP)",
    "Valores_colegio_everest_2026": "Valores 2026 (UF): Bono de Incorporación, matrícula, seguro, colegiatura por nivel",
    "proyecto-educativo-colegio-everest": "Proyecto Educativo Institucional (PEI); los padres deben adherir a él para postular",
    "Proyecto-Educativo-Colegio-Everest": "Proyecto Educativo Institucional (PEI)",
    "Ideario-colegios-RC": "Ideario de los colegios Regnum Christi",
    "rice-everest_2027": "Reglamento Interno de Convivencia Escolar 2027",
    "2027-PROMOCION-Y-EVALUACION": "Reglamento de Promoción y Evaluación Escolar 2027",
    "REGLAMENTO-FONDO-SOLIDARIO-DE-BECAS": "Fondo Solidario de Becas: ayuda transitoria a familias del colegio en emergencia económica (no es beca de admisión)",
    "programa-de-apoyo-alumnos-necesidades-educativas-especiales": "Programa de apoyo a alumnos con necesidades educativas especiales (NEE)",
    "PISE": "Plan Integral de Seguridad Escolar",
    "lista_materiales_2026": "Lista de materiales 2026, Preschool (Mini Bambolino a Kínder)",
    "Textos-y-utiles-Escolares-1o-a-6o": "Textos y útiles 2026, 1° a 6° básico",
    "Textos-y-utiles-Escolares-7": "Textos y útiles 2026, 7° básico a IV medio",
    "Uniformes-Informacion-Practica-2026": "Uso del uniforme 2026, 1° básico a IV medio",
    "Documentos-utiles": "Una línea: los calendarios académicos están en Documentos útiles de Handing",
    "ALEXIA-APODERADOS": "Instructivo Alexia para apoderados",
    "REGLAMENTO-DE-ENFERMERIA": "Reglamento de enfermería 2025",
    "Protocolo-DEA-2025": "Protocolo de uso de los desfibriladores (DEA)",
    "Comunicado-Colegio-Everest-def": "Información Aramark 2025 (casino)",
    "Guia-paso-a-paso-Colegio-Everest-Easy-Cancha": "Guía de la app de arriendo de canchas",
    "ce-codigo-ambientes-seguro": "Código de promoción de ambientes sanos y seguros",
    "colegio-everest-informe-de-certificacion": "Informe de certificación Ceprome",
    "colegio-everest-diploma-de-certificacion": "Diploma de certificación Ceprome",
}

# ─── Levels (2027) ────────────────────────────────────────────────────────────
# From the admission page (age rule and window: verbatim) and the Vacantes 2027
# PDF. The site states an age only for the preschool levels; the rest carry
# none. ``born_by`` is the last birth date that meets the stated age by the
# cut-off (31 March 2027; 1 July 2026 for the second-semester intake). "1,6
# años" is read as one year and six months (18 months).

CUTOFF = "2027-03-31"
LEVELS: list[dict[str, Any]] = [
    {
        "key": "mini_bambolino",
        "name": "Mini Bambolino",
        "cycle": "I",
        "age_text": "1,6 años al 31 de marzo 2027",
        "min_age_months": 18,
        "born_by": "2025-09-30",
        "window_text": "1° al 20 de octubre 2026",
        "opens": "2026-10-01",
        "closes": "2026-10-20",
        "place": "fecha_bambolino",
        "vacancies": 28,
        "priority_neep": 1,
        "fee_band_2026": None,
        "fee_band_2027": "mb_b_pg",
        "admission_day": "Come and Play: fecha a coordinar con cada postulante (el paso 6 nombra «Playgroup y Bambolino»)",
        "results": "tres semanas después del Admission Day",
    },
    {
        "key": "bambolino",
        "name": "Bambolino",
        "cycle": "I",
        "age_text": "2 años al 31 de marzo 2027",
        "min_age_months": 24,
        "born_by": "2025-03-31",
        "window_text": "1° al 20 de octubre 2026",
        "opens": "2026-10-01",
        "closes": "2026-10-20",
        "place": "fecha_bambolino",
        "vacancies": 20,
        "priority_neep": 0,
        "fee_band_2026": "b_pg",
        "fee_band_2027": "mb_b_pg",
        "admission_day": "Come and Play: fecha a coordinar con cada postulante",
        "results": "tres semanas después del Admission Day",
    },
    {
        "key": "playgroup",
        "name": "Playgroup",
        "cycle": "I",
        "age_text": "3 años cumplidos al 31 de marzo 2027",
        "min_age_months": 36,
        "born_by": "2024-03-31",
        "window_text": "1 al 15 de abril de 2026",
        "opens": "2026-04-01",
        "closes": "2026-04-15",
        "place": "fecha_playgroup",
        "vacancies": 29,
        "priority_neep": 1,
        "fee_band_2026": "b_pg",
        "fee_band_2027": "mb_b_pg",
        "admission_day": "Come and Play: fecha a coordinar con cada postulante",
        "results": "tres semanas después del Admission Day",
    },
    {
        "key": "prekinder",
        "name": "Prekínder",
        "cycle": "I",
        "age_text": "4 años cumplidos al 31 de marzo 2027",
        "min_age_months": 48,
        "born_by": "2023-03-31",
        "window_text": "Ex alumnos y hermanos: noviembre 2025 / Familias nuevas 20 de febrero al 10 de marzo 2026",
        "opens": "2025-11-01",
        "closes": "2026-03-10",
        "place": "fecha_prekinder",
        "vacancies": 40,
        "priority_neep": 1,
        "fee_band_2026": "pk_k",
        "fee_band_2027": "pk_k",
        "admission_day": "sábado 21 de marzo 2026",
        "results": "23 de abril 2026, 20:00 hrs.",
    },
]
_UPPER = [
    ("kinder", "Kínder", "I", 2, "pk_k"),
    ("1_basico", "1° básico", "II", 0, "b1_4"),
    ("2_basico", "2° básico", "II", 1, "b1_4"),
    ("3_basico", "3° básico", "II", 2, "b1_4"),
    ("4_basico", "4° básico", "II", 1, "b1_4"),
    ("5_basico", "5° básico", "II", 3, "b5_8"),
    ("6_basico", "6° básico", "II", 0, "b5_8"),
    ("7_basico", "7° básico", "III", 1, "b5_8"),
    ("8_basico", "8° básico", "III", 1, "b5_8"),
    ("i_medio", "I medio", "III", 1, "media"),
    ("ii_medio", "II medio", "III", 1, "media"),
    ("iii_medio", "III medio", "III", "SIN VACANTES", "media"),
    ("iv_medio", "IV medio", "III", "SIN VACANTES", "media"),
]
for _i, (_key, _name, _cycle, _vac, _band) in enumerate(_UPPER):
    LEVELS.append(
        {
            "key": _key,
            "name": _name,
            "cycle": _cycle,
            "age_text": None,
            "min_age_months": None,
            "born_by": None,
            #: Not on the site: one year per level after Prekínder (4 años).
            "age_if_sequence": 5 + _i,
            "window_text": "julio a septiembre 2026",
            "opens": "2026-07-01",
            "closes": "2026-09-30",
            "place": "fecha_kinder_iv_medio",
            "vacancies": _vac,
            "priority_neep": 0 if isinstance(_vac, int) else None,
            "fee_band_2026": _band,
            "fee_band_2027": _band,
            "admission_day": "Evaluación de Inglés, matemáticas y lenguaje y entrevista con el psicólogo del nivel; fechas en agosto, septiembre y octubre",
            "results": "tres semanas después del Admission Day",
        }
    )

#: Fees as the PDFs give them, in UF, with their own decimal marks.
FEES: dict[str, Any] = {
    "2026": {
        "source": "/wp-content/uploads/2026/06/Valores_colegio_everest_2026.pdf",
        "linked": True,
        "bands": {
            "b_pg": {
                "label": "Bambolino - PlayGroup",
                "matricula": "9.25",
                "cuota": "10,26",
                "anual": "102,58",
            },
            "pk_k": {
                "label": "Pre-Kinder y Kinder",
                "matricula": "14.6",
                "cuota": "18,68",
                "anual": "186,80",
            },
            "b1_4": {
                "label": "1° a 4° básico",
                "matricula": "14.6",
                "cuota": "18,90",
                "anual": "189,00",
            },
            "b5_8": {
                "label": "5° a 8° básico",
                "matricula": "14.6",
                "cuota": "19,56",
                "anual": "195,63",
            },
            "media": {
                "label": "I a IV medio",
                "matricula": "14.6",
                "cuota": "20,06",
                "anual": "200,58",
            },
        },
        "seguro": "3.67 (columna «Valor seguro escolaridad - vida»; la tabla lo da una sola vez)",
        "cuotas": 10,
        "bono_incorporacion": {
            "1": "95 UF",
            "2": "80 UF",
            "3": "75 UF",
            "4": "65 UF",
            "5+": "0 UF",
        },
        "note": "Los valores de la colegiatura del año 2027 serán informados oportunamente. (Mini Bambolino no aparece en la tabla 2026.)",
    },
    "2027": {
        "source": "/wp-content/uploads/2026/10/Ver-valores-de-matricula-y-colegiaturas-2027_.pdf",
        "linked": False,
        "bands": {
            "mb_b_pg": {
                "label": "Mini Bambolino \u2013 Bambolino - Playgroup",
                "matricula": "10,646",
                "cuota": "10,57",
                "anual": "105,68",
            },
            "pk_k": {
                "label": "Prekinder y Kinder",
                "matricula": "15,996",
                "cuota": "19,33",
                "anual": "193,34",
            },
            "b1_4": {
                "label": "1° a 4° básico",
                "matricula": "15,996",
                "cuota": "19,56",
                "anual": "195,62",
            },
            "b5_8": {
                "label": "5° a 8° básico",
                "matricula": "15,996",
                "cuota": "20,25",
                "anual": "202,45",
            },
            "media": {
                "label": "I a IV medio",
                "matricula": "15,996",
                "cuota": "20,66",
                "anual": "206,62",
            },
        },
        "seguro": "La matrícula considera 1,396 UF por cobertura de seguro de escolaridad",
        "cuotas": 10,
        "familia_numerosa": {"3": "10%", "4": "25%", "5": "50%", "6+": "100%"},
        "note": "Desde 2025 las familias con más de 4 hijos en el colegio pagan como máximo 4 matrículas. El PDF no está enlazado en ninguna página.",
    },
}

# ─── Fetching ────────────────────────────────────────────────────────────────


class Blocked(SystemExit):
    pass


def cache_file(key: str, ext: str = "json") -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (hashlib.sha1(key.encode()).hexdigest()[:16] + "." + ext)


def http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL"})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500:  # a missing file stays missing
                raise SystemExit(f"{url}: HTTP {exc.code}") from exc
            last = exc
            time.sleep(5 * (attempt + 1))
        except Exception as exc:  # retried, then raised
            last = exc
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"{url}: {last} (site down, or the connection is refused here?)")


def get_json(url: str, offline: bool) -> Any:
    path = cache_file(url)
    if path.exists() and offline:
        return json.loads(path.read_text(encoding="utf-8"))
    if offline:
        raise SystemExit(f"{url}: not in the cache; run without --offline first")
    data = json.loads(http_get(url).decode("utf-8"))
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def rest_all(kind: str, fields: str, offline: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(1, 6):
        got = get_json(
            f"{SITE}/wp-json/wp/v2/{kind}?per_page=100&page={page}&_fields={fields}", offline
        )
        if not isinstance(got, list) or not got:
            break
        out += got
        if len(got) < 100:
            break
    return out


_VIS = """const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
const txt = (e) => (e.innerText || e.value || '').replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n+/g, '\\n').trim();"""

#: For each place: how many match, how many are laid out, its words, and the
#: link it is or holds (when it holds exactly one target).
_READ = (
    """(rows) => {"""
    + _VIS
    + """
  const out = [];
  for (const [key, sel] of rows) {
    let all = [];
    try { all = [...document.querySelectorAll(sel)]; } catch (e) { out.push({key, count: -1, visible: 0}); continue; }
    const shown = all.filter(vis);
    const el = shown[0] || all[0];
    if (!el) { out.push({key, count: 0, visible: 0}); continue; }
    const as = el.tagName === 'A' ? [el] : [...el.querySelectorAll('a[href]')];
    const hrefs = [...new Set(as.map(a => a.href).filter(h => h && !h.endsWith('#')))];
    out.push({key, count: all.length, visible: shown.length, text: txt(el).slice(0, 4000),
              href: hrefs.length === 1 ? hrefs[0] : ''});
  }
  return out;
}"""
)

#: The page as data: headings, links (with the heading of the card they sit
#: in), iframes, forms (fields only: nothing is filled), the content's text.
_INFO = (
    """() => {"""
    + _VIS
    + """
  const main = document.querySelector('#main') || document.body;
  const entry = document.querySelector('.entry-content') || main;
  const heads = [...main.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(vis)
    .map(h => ({level: +h.tagName[1], text: txt(h)})).filter(h => h.text);
  const near = (a) => {
    let x = a.parentElement;
    while (x && x !== main) {
      const h = x.querySelector('h1,h2,h3,h4,h5,h6,.gb-headline');
      if (h && txt(h) && !h.contains(a)) return txt(h).slice(0, 120);
      x = x.parentElement;
    }
    return '';
  };
  const links = [...main.querySelectorAll('a[href]')].filter(a => !a.closest('.slick-cloned'))
    .map(a => ({label: txt(a) || a.title || a.getAttribute('aria-label') || ((a.querySelector('img') || {}).alt) || '',
                href: a.href, near: near(a)}));
  const iframes = [...document.querySelectorAll('#main iframe, .site-footer iframe')]
    .map(f => ({src: f.src || f.dataset.src || '', title: f.title || f.name || ''}));
  const forms = [...main.querySelectorAll('form')].map(f => ({
    id: (f.closest('.wpcf7') || {}).id || f.id || '',
    fields: [...f.querySelectorAll('input, textarea, select')].filter(x => x.type !== 'hidden')
      .map(x => ({name: x.name, type: x.type || x.tagName.toLowerCase(),
                  required: x.required || x.getAttribute('aria-required') === 'true'})),
  }));
  const meta = document.querySelector('meta[name="description"], meta[property="og:description"]');
  return {title: document.title, h1: txt(document.querySelector('h1') || document.createElement('i')),
          description: meta ? meta.content : '', headings: heads, links, iframes, forms,
          text: txt(entry), status: document.body.innerText.slice(0, 200)};
}"""
)

#: The two menus as a tree, and the footer.
_SITE = (
    """() => {"""
    + _VIS
    + """
  const menu = (sel) => {
    const nav = document.querySelector(sel); if (!nav) return [];
    const ul = nav.querySelector('ul'); if (!ul) return [];
    return [...ul.children].filter(li => li.tagName === 'LI').map(li => {
      const a = li.querySelector(':scope > a');
      const sub = li.querySelector(':scope > ul');
      return {id: li.id, label: a ? txt(a) : '', href: a ? a.getAttribute('href') : '',
              dropdown: !!sub,
              children: sub ? [...sub.querySelectorAll(':scope > li > a')].map(c => ({label: txt(c), href: c.href})) : []};
    });
  };
  const foot = document.querySelector('.site-footer');
  return {top: menu('#secondary-navigation'), main: menu('#site-navigation'),
          footer: foot ? {text: txt(foot),
            links: [...foot.querySelectorAll('a[href]')].map(a => ({label: txt(a) || a.getAttribute('aria-label') || '', href: a.href})),
            map: ((foot.querySelector('iframe') || {}).src) || ''} : {}};
}"""
)


#: Hosts a page may load from while crawling: the site, and Cloudflare's
#: Turnstile (the contact form's check box). Everything else — Tag Manager,
#: YouTube, Maps, fonts — is aborted: one of them stalling holds back the
#: page's DOMContentLoaded for minutes, and none of them changes the layout
#: the catalogue checks (iframes keep their box without their content).
_HOSTS = (HOST, "colegioeverest.cl", "challenges.cloudflare.com")


def _only_site(route: Any) -> None:
    host = urlsplit(route.request.url).netloc.lower()
    if host in _HOSTS or route.request.url.startswith(("data:", "blob:")):
        route.continue_()
    else:
        route.abort()


def _goto(page: Any, url: str) -> None:
    """Load ``url``: wait for the DOM only (the server stalls), three tries."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=180_000)
            status = resp.status if resp is not None else 0
            body = page.evaluate("document.body ? document.body.innerText.slice(0, 300) : ''")
            if status in (403, 405) or "Not allowed" in body:
                raise Blocked(
                    f"{url}: HTTP {status} {body[:80]!r} (the site refuses this connection)"
                )
            break
        except Blocked:
            raise
        except Exception as exc:
            last = exc
            print(f"  retry {attempt + 1} {url}: {str(exc).splitlines()[0][:120]}", flush=True)
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"{url}: {last}")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("load", timeout=45_000)
    # Scroll through once, so lazy blocks and the sliders lay out.
    height = page.evaluate("document.body.scrollHeight")
    y = 0
    while y < height:
        page.evaluate(f"scrollTo(0, {y})")
        page.wait_for_timeout(110)
        y += 700
        height = page.evaluate("document.body.scrollHeight")
    page.evaluate("scrollTo(0, 0)")
    page.wait_for_timeout(600)


def render(page: Any, path: str, rows: list[Row]) -> dict[str, Any]:
    _goto(page, SITE + path)
    got = {
        "path": path,
        "reads": page.evaluate(_READ, [[k, s] for k, s, _, _ in rows]),
        "info": page.evaluate(_INFO),
    }
    if path == "/":
        got["site"] = page.evaluate(_SITE)
    return got


def rows_for(path: str) -> list[Row]:
    kind, rows = PAGES[path]
    own = rows if kind == "home" else INNER + rows
    return own + HEADER + FOOTER


def crawl(offline: bool, refresh: bool) -> dict[str, Any]:
    pages_api = rest_all("pages", "id,link,title,modified,parent,slug", offline)
    posts = rest_all("posts", "id,date,modified,link,title,content,excerpt", offline)
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    todo: list[tuple[str, list[Row]]] = [(p, rows_for(p)) for p in PAGES]
    for post in posts[:POST_SAMPLES]:
        path = site_path(post["link"])
        if path:
            todo.append((path, POST + HEADER + FOOTER))
    rendered: dict[str, Any] = {}
    missing = []
    for path, _ in todo:
        f = cache_file(SITE + path + "#rendered")
        if f.exists() and not refresh:
            rendered[path] = json.loads(f.read_text(encoding="utf-8"))
        else:
            missing.append(path)
    if missing and offline:
        raise SystemExit(f"not rendered in the cache: {missing}; run without --offline first")
    if missing:
        from playwright.sync_api import sync_playwright

        rows = dict(todo)
        blocked = 0
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")
            ctx.route("**/*", _only_site)
            page = ctx.new_page()
            for path in missing:
                t0 = time.time()
                try:
                    got = render(page, path, rows[path])
                    blocked = 0
                except Blocked as exc:
                    blocked += 1
                    print(exc, flush=True)
                    if blocked >= 3:
                        browser.close()
                        raise SystemExit("refused three times running: nothing written") from exc
                    continue
                except RuntimeError as exc:
                    print(f"FAILED {exc}", flush=True)
                    continue
                bad = [
                    r["key"] for r in got["reads"] if r.get("count") != 1 or r.get("visible") != 1
                ]
                print(
                    f"{path}: {len(got['reads'])} places in {time.time() - t0:.1f}s; off: {bad}",
                    flush=True,
                )
                cache_file(SITE + path + "#rendered").write_text(
                    json.dumps(got, ensure_ascii=False), encoding="utf-8"
                )
                rendered[path] = got
            browser.close()
    return {"pages_api": pages_api, "posts": posts, "rendered": rendered}


# ─── Records ────────────────────────────────────────────────────────────────


def site_path(url: str) -> str | None:
    m = re.match(r"^https?://(?:www\.)?colegioeverest\.cl(/[^?#]*)?", url)
    if not m:
        return None
    path = m.group(1) or "/"
    return path if path.endswith("/") else path + "/"


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def clean(text: str) -> str:
    text = (text or "").replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def html_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#038;", "&"),
    ):
        text = text.replace(a, b)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return clean(text)


def ok(read: dict[str, Any] | None, flags: str) -> bool:
    if read is None:
        return False
    if "o" in flags:
        return read.get("count") == 1
    return read.get("count") == 1 and read.get("visible") == 1


def keep(
    path: str, rows: list[Row], reads: dict[str, Any], label: str = ""
) -> list[dict[str, Any]]:
    out = []
    for key, sel, lab, flags in rows:
        r = reads.get(key)
        if not ok(r, flags):
            got = f"count {r.get('count')}, visible {r.get('visible')}" if r else "not read"
            print(f"  dropped {label or path} {key} ({sel}): {got}")
            continue
        assert r is not None
        row: dict[str, Any] = {"key": key, "selector": sel, "label": lab}
        if "h" in flags or "o" in flags:
            row["hidden"] = True
        if "o" in flags:
            row["optional"] = True
        if "p" in flags:
            row["positional"] = True
        if r.get("href"):
            row["href"] = r["href"]
        out.append(row)
    return out


def anchors_record(rendered: dict[str, Any]) -> dict[str, Any]:
    pages: dict[str, Any] = {}
    for path, (kind, _rows) in PAGES.items():
        got = rendered.get(path)
        if not got:
            print(f"  no render for {path}: left out of the catalogue")
            continue
        reads = {r["key"]: r for r in got["reads"]}
        own_rows = [r for r in rows_for(path) if r not in HEADER and r not in FOOTER]
        foot_reads = {k: reads.get(k) for k, *_ in FOOTER}
        head_reads = {k: reads.get(k) for k, *_ in HEADER}
        pages[path] = {
            "kind": kind,
            "title": got["info"]["h1"] or got["info"]["title"],
            "header": all(ok(r, "") for r in head_reads.values()),
            "footer": all(ok(r, "") for r in foot_reads.values()),
            "anchors": keep(path, own_rows, reads),
        }
    home = {r["key"]: r for r in rendered["/"]["reads"]}
    post_paths = [p for p in rendered if p not in PAGES]
    post: list[dict[str, Any]] = []
    if post_paths:
        # A post place is kept only when every sample showed it once.
        samples = [{r["key"]: r for r in rendered[p]["reads"]} for p in post_paths]
        post = keep("post", POST, samples[0], "post")
        post = [a for a in post if all(ok(s.get(a["key"]), "") for s in samples)]
        for a in post:
            a.pop("href", None)
    header = keep("/", HEADER, home, "header")
    footer = keep("/", FOOTER, home, "footer")
    # A menu item or the footer holds several links; only single-link items keep one.
    for a in header + footer:
        if a["key"] not in {"menu_alexia", "menu_pago_online", "menu_admision", "menu_contacto"}:
            a.pop("href", None)
    return {
        "_meta": {
            "site": SITE,
            "header_px": HEADER_PX,
            "scroll_gap_px": GAP_PX,
            "viewport": "1440x900",
            "note": "Built by build.py; every selector matched exactly one laid-out element on the live page "
            "(optional ones: exactly one element). GenerateBlocks classes repeat across pages: a key is only "
            "valid on its own page. positional places are .entry-content > :nth-child(n).",
        },
        "header": header,
        "footer": footer,
        "post": post,
        "pages": pages,
    }


def _link_kind(url: str) -> str:
    low = url.lower()
    if low.startswith("tel:"):
        return "tel"
    if low.startswith("mailto:"):
        return "mail"
    if low.split("?")[0].endswith(".pdf"):
        return "pdf"
    host = urlsplit(url).netloc.lower()
    if host and host.removeprefix("www.") != "colegioeverest.cl":
        return "external"
    return "internal"


def page_links(info: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    docs: list[dict[str, str]] = []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in info.get("links", []):
        url = link["href"]
        kind = _link_kind(url)
        if kind == "internal" or url in seen:
            continue
        seen.add(url)
        rec = {
            "label": clean(link["label"])[:120],
            "url": url,
            "near": link.get("near", ""),
            "kind": kind,
        }
        (docs if kind == "pdf" else out).append(rec)
    return docs, out


def pages_record(crawled: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = crawled["rendered"]
    modified = {
        site_path(p["link"]): p.get("modified", "")[:10]
        for p in crawled["pages_api"]
        if p.get("link")
    }
    out: list[dict[str, Any]] = []
    for path, (kind, _rows) in PAGES.items():
        got = rendered.get(path)
        if not got:
            continue
        info = got["info"]
        reads = {r["key"]: r for r in got["reads"]}
        sections = []
        for key, _sel, label, flags in rows_for(path):
            r = reads.get(key)
            if (
                "h" in flags
                or "o" in flags
                or not ok(r, flags)
                or key in {"titulo", "contenido"}
                or (key, _sel, label, flags) in HEADER
                or (key, _sel, label, flags) in FOOTER
            ):
                continue
            assert r is not None
            sections.append(
                {"key": key, "heading": label, "text": clean(r.get("text", ""))[:TEXT_CAP]}
            )
        docs, links = page_links(info)
        rec: dict[str, Any] = {
            "path": path,
            "url": SITE + path,
            "title": info["h1"] or info["title"],
            "kind": kind,
            "description": clean(info.get("description", "")),
            "modified": modified.get(path, ""),
            "sections": sections,
            "headings": [clean(h["text"]) for h in info["headings"]][:60],
            "documents": docs,
            "links": links,
            "iframes": [f for f in info["iframes"] if "googletagmanager" not in f["src"]],
            "forms": info["forms"],
            "text": clean(info["text"])[:6000],
        }
        out.append(rec)
    for path, why in UNGUIDED.items():
        out.append(
            {
                "path": path,
                "url": SITE + path,
                "title": path,
                "kind": "unguided",
                "empty": True,
                "note": why,
            }
        )
    for post in crawled["posts"][:POSTS_KEPT]:
        path = site_path(post["link"])
        if not path:
            continue
        title = html_text(post["title"]["rendered"])
        body = html_text(post["content"]["rendered"])
        out.append(
            {
                "path": path,
                "url": post["link"],
                "title": title,
                "kind": "post",
                "date": post["date"][:10],
                "sections": [
                    {"key": "titulo", "heading": title, "text": ""},
                    {
                        "key": "contenido",
                        "heading": f"La noticia «{title}»",
                        "text": body[: TEXT_CAP * 3],
                    },
                ],
                "text": body[: TEXT_CAP * 3],
            }
        )
    return out


def site_record(crawled: dict[str, Any]) -> dict[str, Any]:
    home = crawled["rendered"]["/"]
    site = home.get("site", {})
    hosts: dict[str, list[str]] = {}
    for path, got in crawled["rendered"].items():
        for link in got["info"]["links"]:
            if _link_kind(link["href"]) == "external":
                hosts.setdefault(urlsplit(link["href"]).netloc.lower(), [])
                if path not in hosts[urlsplit(link["href"]).netloc.lower()]:
                    hosts[urlsplit(link["href"]).netloc.lower()].append(path)
    ctas = {}
    for key, cta in CTAS.items():
        urls = sorted(
            {
                link["href"]
                for got in [home, crawled["rendered"].get(ADM, {"info": {"links": []}})]
                for link in got["info"]["links"] + [{"href": c["href"]} for c in _menu_links(site)]
                if cta["match"] in link["href"]
                and not (cta.get("exclude") and cta["exclude"] in link["href"])
            }
        )
        ctas[key] = {**cta, "urls": urls}
    return {
        "site": SITE,
        "language": "es (sin versión en inglés)",
        "platform": "WordPress + GeneratePress + GenerateBlocks; Contact Form 7 con Cloudflare Turnstile",
        "navigation": "Cada navegación recarga la página completa. El encabezado no es fijo.",
        "menu": {"top": site.get("top", []), "main": site.get("main", [])},
        "dropdowns": {
            "menu_nuestro_colegio": "#menu-item-107",
            "menu_modelo_educativo": "#menu-item-284",
            "menu_comunidad": "#menu-item-400",
        },
        "dropdown_open_class": "sfHover",
        "footer": site.get("footer", {}),
        "phones": {
            "principal": "+56 2 2757 8800",
            "admision": "+56 2 2757 8804",
            "enfermeria": "+56 2 2757 8800 anexo 210",
        },
        "ctas": ctas,
        "unguided": UNGUIDED,
        "external_hosts": dict(sorted(hosts.items())),
        "rest": {"pages": len(crawled["pages_api"]), "posts": len(crawled["posts"])},
        "news_listing": "/noticias/ pagina con ?query-54c839b3-page=N; las noticias viven en la raíz (/<slug>/)",
    }


def _menu_links(site: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for item in site.get("top", []) + site.get("main", []):
        out.append({"href": item.get("href") or ""})
        out += [{"href": c.get("href") or ""} for c in item.get("children", [])]
    return out


def documents_record(crawled: dict[str, Any], pdfs: bool, offline: bool) -> list[dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for path, got in crawled["rendered"].items():
        for link in got["info"]["links"]:
            url = link["href"]
            if _link_kind(url) != "pdf":
                continue
            d = docs.setdefault(url, {"url": url, "labels": [], "pages": [], "linked": True})
            label = clean(link["label"])
            if label and label not in d["labels"]:
                d["labels"].append(label)
            if path not in d["pages"]:
                d["pages"].append(path)
    for rel, note in UNLINKED_PDFS:
        docs.setdefault(
            SITE + rel,
            {"url": SITE + rel, "labels": [], "pages": [], "linked": False, "note": note},
        )
    for d in docs.values():
        name = unquote(d["url"].rsplit("/", 1)[-1])
        d["file"] = name
        for part, note in DOC_NOTES.items():
            if part in name:
                d.setdefault("note", note)
                break
        if pdfs:
            d.update(pdf_facts(d["url"], offline))
    return sorted(docs.values(), key=lambda d: (not d["linked"], d["url"]))


def pdf_facts(url: str, offline: bool) -> dict[str, Any]:
    """Pages and size; the text goes to the cache only."""
    meta = cache_file(url + "#pdf")
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    if offline:
        return {}
    try:
        data = http_get(url, timeout=180)
    except SystemExit as exc:
        print(f"  pdf {url}: {exc}")
        m = re.search(r"HTTP (\d{3})$", str(exc))
        if not m:
            return {}
        # The page links a file the server does not have: a site bug, kept.
        facts = {"status": int(m.group(1))}
        meta.write_text(json.dumps(facts), encoding="utf-8")
        return facts
    facts: dict[str, Any] = {"bytes": len(data)}
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        facts["n_pages"] = len(reader.pages)
        if len(data) <= 12_000_000:
            text = "\n".join((pg.extract_text() or "") for pg in reader.pages)[:8000]
            cache_file(url + "#text", "txt").write_text(text, encoding="utf-8")
    except Exception as exc:  # a broken PDF is listed without facts
        print(f"  pdf {url}: {exc}")
    meta.write_text(json.dumps(facts), encoding="utf-8")
    return facts


def pdf_text(url: str) -> str:
    f = cache_file(url + "#text", "txt")
    return f.read_text(encoding="utf-8") if f.exists() else ""


_VAC_NAMES = {
    "mini_bambolino": r"Mini Bambolino",
    "bambolino": r"(?<!Mini )Bambolino",
    "playgroup": r"Playgroup",
    "prekinder": r"Prek[ií]nder",
    "kinder": r"(?<!Pre)(?<!Pre-)K[ií]nder",
    "1_basico": r"1° B[áa]sico",
    "2_basico": r"2° B[áa]sico",
    "3_basico": r"3° B[áa]sico",
    "4_basico": r"4° B[áa]sico",
    "5_basico": r"5° B[áa]sico",
    "6_basico": r"6° B[áa]sico",
    "7_basico": r"7° B[áa]sico",
    "8_basico": r"8° B[áa]sico",
    "i_medio": r"\bI Medio",
    "ii_medio": r"\bII Medio",
    "iii_medio": r"\bIII Medio",
    "iv_medio": r"\bIV Medio",
}


def levels_record(anchors: dict[str, Any]) -> dict[str, Any]:
    adm = {a["key"] for a in anchors["pages"].get(ADM, {}).get("anchors", [])}
    vac_text = pdf_text(SITE + "/wp-content/uploads/2026/03/VACANTES-EVEREST-2027.pdf")
    for lv in LEVELS:
        if lv["place"] not in adm:
            print(f"  level {lv['key']}: place {lv['place']} not in the catalogue")
        if vac_text:
            m = re.search(
                _VAC_NAMES[lv["key"]] + r"\s*\n(?:[^\n]*años[^\n]*\n)?\s*(\d+|SIN VACANTES)",
                vac_text,
            )
            seen = m.group(1) if m else None
            want = str(lv["vacancies"])
            if seen != want:
                print(f"  level {lv['key']}: vacancies {want} here, the PDF reads {seen!r}")
    return {
        "_meta": {
            "cutoff": CUTOFF,
            "page": ADM,
            "sources": [
                ADM,
                "/wp-content/uploads/2026/03/VACANTES-EVEREST-2027.pdf",
                FEES["2026"]["source"],
                FEES["2027"]["source"],
            ],
            "note": "age_text and window_text are the admission page's words. The site gives an age only for "
            "Mini Bambolino, Bambolino, Playgroup and Prekínder; age_if_sequence (Kínder up) is NOT on the "
            "site. born_by: last birth date meeting the age at the cut-off ('1,6 años' read as 18 months). "
            "Vacancies: Vacantes 2027 PDF, which says the numbers change with movements per level. "
            "Admission fee (valor proceso): $45.000 per student.",
            "second_semester_2026": {
                "name": "Mini Bambolino II semestre 2026",
                "age_text": "1,6 años cumplidos al 1 de julio de 2026",
                "window_text": "1 al 15 de mayo de 2026",
                "opens": "2026-05-01",
                "closes": "2026-05-15",
                "place": "fecha_mini_bambolino_2s",
            },
        },
        "levels": LEVELS,
        "fees": FEES,
    }


def write_site_map(
    anchors: dict[str, Any], pages: list[dict[str, Any]], site: dict[str, Any]
) -> None:
    lines = [
        "# Mapa del sitio y lugares que Javier puede mostrar",
        "",
        "Sources: colegioeverest.cl, generado por build.py desde L3/anchors.json y L3/site.json (cada selector verificado en el sitio).",
        "",
        "Cada página con sus lugares: la clave va en un cue y solo vale en su propia página. El encabezado",
        "(menús) y el pie (dirección, teléfono, mapa, links) están en todas las páginas.",
        "",
        "## Menú",
    ]
    for item in site["menu"]["main"] + site["menu"]["top"]:
        label = item.get("label", "")
        if item.get("children"):
            kids = "; ".join(
                f"{c['label']} ({site_path(c['href']) or c['href']})" for c in item["children"]
            )
            lines.append(f"- {label} (desplegable): {kids}")
        else:
            lines.append(f"- {label}: {site_path(item.get('href') or '') or item.get('href')}")
    lines += ["", "## Encabezado y pie (todas las páginas)"]
    for a in anchors["header"] + anchors["footer"]:
        if not a.get("hidden"):
            lines.append(f"- `{a['key']}`: {a['label']}")
    by_path = {p["path"]: p for p in pages}
    for path, page in anchors["pages"].items():
        rec = by_path.get(path, {})
        lines += ["", f"## {path} — {page['title']}"]
        for a in page["anchors"]:
            if not a.get("hidden"):
                lines.append(f"- `{a['key']}`: {a['label']}")
        hidden = [a["key"] for a in page["anchors"] if a.get("hidden")]
        if hidden:
            lines.append(f"- (del adaptador: {', '.join(hidden)})")
        if rec.get("documents"):
            lines.append(f"- PDF enlazados: {len(rec['documents'])}")
    lines += ["", "## Plantilla de noticia (cada noticia en /<slug>/)"]
    for a in anchors["post"]:
        lines.append(f"- `{a['key']}`: {a['label']}")
    lines += ["", "## Páginas a las que no se lleva al visitante"]
    for path, why in UNGUIDED.items():
        lines.append(f"- {path} — {why}")
    (HERE / "L2" / "site-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_news(pages: list[dict[str, Any]]) -> None:
    lines = [
        "# Noticias recientes",
        "",
        f"Sources: colegioeverest.cl/wp-json/wp/v2/posts, generado por build.py (las {POSTS_KEPT} más recientes).",
        "",
        "Cada noticia es su propia página en la raíz del sitio. La lista completa está en /noticias/ y el",
        "carrusel de la portada (`noticias_carrusel`) muestra las últimas nueve. Fechas de publicación.",
        "",
    ]
    for p in pages:
        if p["kind"] != "post":
            continue
        first = re.split(r"(?<=[.!?])\s", p["text"].replace("\n", " "), maxsplit=1)[0][:220]
        lines.append(f"- {p['date']} — **{p['title']}** — {p['path']}")
        if first:
            lines.append(f"  {first}")
    (HERE / "L2" / "noticias.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def dump(path: Path, data: Any, lines: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if lines and isinstance(data, list):
        body = "[\n" + ",\n".join(json.dumps(d, ensure_ascii=False) for d in data) + "\n]\n"
    else:
        body = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    path.write_text(body, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("command", choices=["crawl"])
    ap.add_argument("--offline", action="store_true", help="build from the cache only")
    ap.add_argument("--refresh", action="store_true", help="render every page again")
    ap.add_argument(
        "--pdfs", action="store_true", help="fetch the PDFs for size, pages and text (cache)"
    )
    args = ap.parse_args()
    crawled = crawl(args.offline, args.refresh)
    if "/" not in crawled["rendered"] or ADM not in crawled["rendered"]:
        raise SystemExit("the home or the admission page did not render: nothing written")
    anchors = anchors_record(crawled["rendered"])
    pages = pages_record(crawled)
    site = site_record(crawled)
    documents = documents_record(crawled, args.pdfs, args.offline)
    dump(L3 / "anchors.json", anchors)
    dump(L3 / "pages.json", pages, lines=True)
    dump(L3 / "site.json", site)
    dump(L3 / "documents.json", documents)
    dump(L3 / "levels.json", levels_record(anchors))
    write_site_map(anchors, pages, site)
    write_news(pages)
    n = sum(len(p["anchors"]) for p in anchors["pages"].values())
    print(
        f"wrote {L3}: {len(anchors['pages'])} pages, {n} places, {len(pages)} page records, {len(documents)} PDFs"
    )


if __name__ == "__main__":
    sys.exit(main())
