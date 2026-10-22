# Exámenes de laboratorio explicados (the 19 /examenes/* pages)

Sources: https://www.clini.cl/examenes/antigeno-prostatico-psa-total-y-libre, /examenes/beta-hcg, /examenes/complejo-vitamina-b-y-vitamina-b12, /examenes/creatinina, /examenes/cuales-son-los-valores-normales-de-hematocrito, /examenes/curva-de-tolerancia-a-la-glucosa-y-curva-de-insulina, /examenes/curva-de-tolerancia-a-la-glucosa-y-curva-de-insulina-2, /examenes/examen-de-orina-completo, /examenes/examen-de-sangre, /examenes/examenes-fta-abs-rpr-y-vdrl, /examenes/hemoglobina-glicada, /examenes/perfil-bioquimico, /examenes/perfil-hepatico-enfermedades-del-higado-y-vesicula-biliar, /examenes/perfil-lipidico, /examenes/test-de-antigenos, /examenes/test-para-las-alergias, /examenes/tiroideos, /examenes/vih-test-de-anticuerpos-y-test-de-antigenos, /examenes/vitamina-d (all at https://www.clini.cl); prices from the "Principales Exámenes de Laboratorio" cards on the /laboratorio/* branch pages (whose "Conocer más" buttons open these pages).

Each page has the same shape: a first block whose heading is the exam's name (below), with "Ayuno:" and a "Reservar hora" button (agenda-web `?servicio=62&prestacion=30`), then explanatory sections. They explain what an exam measures in general terms. Javier may say what the page says an exam is for and how to prepare; he never interprets a person's value (the pages themselves say a doctor reads results). They are not in any menu: reach them from the lab branch cards, search, or a cue.

| Page (path under /examenes/) | First heading (cue) | Ayuno (page) | Fonasa / particular (branch card) | Notes from the page |
|---|---|---|---|---|
| antigeno-prostatico-psa-total-y-libre | Antígeno Prostatico (PSA) total y libre | No aplica | $12.340 / $24.690 | PSA used to screen and follow prostate disease; mentions further PSA types if a value is abnormal. |
| beta-hcg | Beta hCG | No necesita | $2.710 / $5.420 | Pregnancy hormone; section "¿Qué consideraciones debo tener antes de un examen Beta hCG?"; reference values by week. |
| complejo-vitamina-b-y-vitamina-b12 | Vitamina B12 | No aplica | $3.890 / $7.780 | Section "Suplementos de Vitamina B, ¿para qué sirven?". |
| creatinina | Creatinina | No aplica | $680 / $1.370 | Kidney function; normal values vary by lab. |
| cuales-son-los-valores-normales-de-hematocrito | Hematocrito | No es necesario | $390 / $790 | Section "¿Qué pasa cuando el hematocrito está bajo?". |
| curva-de-tolerancia-a-la-glucosa-y-curva-de-insulina | Curva de tolerancia a la glucosa y Curva de insulina | 8 horas | $10.060 / $20.120 | Basal sample fasting, then samples after the glucose load; results "en menos de 24 horas". |
| curva-de-tolerancia-a-la-glucosa-y-curva-de-insulina-2 | Curva de insulina | 8 horas | $10.060 / $20.120 | A near-copy of the page above (title "Curva de tolerancia a la glucosa y de insulina"). |
| examen-de-orina-completo | Examen de orina | No necesita | $980 / $5.130 | Also explains urocultivo ("Examen Urocultivo ¿Qué es?"); tell staff about any treatment. |
| examen-de-sangre | Hemograma | 8 Horas (field) / "no requiere de ayuno" (text) | $1.580 / $3.170 | Results "en menos de 12 horas". |
| examenes-fta-abs-rpr-y-vdrl | FTA-ABS, RPR y VDRL | No es necesario | $5.520 / $11.060 | Syphilis tests; "No se requiere ninguna preparación especial". |
| hemoglobina-glicada | Hemoglobina Glicada | NO | $2.320 / $4.640 | Reflects the last 3 months; results "en menos de 12 horas". |
| perfil-bioquimico | Perfil Bioquímico | 8 horas | $4.480 / $8.960 | Section "¿Qué es el Perfil Bioquímico?". |
| perfil-hepatico-enfermedades-del-higado-y-vesicula-biliar | Perfil Hepático | 6 horas | $5.240 / $10.490 | Liver tests; lists other related tests. |
| perfil-lipidico | Perfil Lipídico | 9 horas | $3.190 / $6.380 | 9 h fasting and no alcohol; results "en menos de 24 horas". |
| test-de-antigenos | TEST DE ANTÍGENOS de laboratorio (SARS CoV-2) | No | $4.850 / $9.710 | Nasal swab at CLINI's tomas de muestras; report "en el plazo de 1 hora"; a PCR may be advised to confirm a negative. |
| test-para-las-alergias | Test para las alergias (35 alergenos) | No aplica | $97.200 / $194.760 | Blood test for allergy antibodies. |
| tiroideos | Hormonas tiroideas | No necesita | $9.720 / $19.110 | If on thyroid medication, the sample goes before the day's dose; results "en menos de 24 horas". |
| vih-test-de-anticuerpos-y-test-de-antigenos | VIH: Test de anticuerpos y Test de antígenos | No aplica | $3.710 / $7.430 | Explains antibody vs antigen tests and the time after exposure. |
| vitamina-d | Vitamina D | No aplica | $8.640 / $17.280 | 25-hidroxi vitamina D; sample sent to certified labs, results "en pocos días". |

Cotizador catalogue equivalents (Fonasa / particular): Hemograma VHS $1.580 / $3.170; Perfil lipídico $3.190 / $6.380 (Ayuno 9 hrs.); Perfil bioquímico $4.480 / $8.960 (Ayuno 8 hrs.); Perfil hepático $5.240 / $10.490 (Ayuno 6 hrs.); Perfil tiroideo $9.720 / $19.440; Vitamina D total $8.640 / $17.280; Hemoglobina glicada $2.320 / $4.640; Creatinina $680 / $1.370; Orina completa $980 / $1.960 (4 horas sin orinar). Use the live price lookup for the visitor's exact exam.

## How Javier uses these pages
- "¿Necesito ayuno para el perfil lipídico?" → the page says 9 h and no alcohol; offer `{page: /examenes/perfil-lipidico}`.
- "¿Cuánto cuesta la vitamina D?" → Fonasa $8.640 / particular $17.280 (branch card and cotizador agree).
- Booking from any of them: "Reservar hora" → agenda-web Laboratorio (`?servicio=62&prestacion=30`); or phone 22 994 4003, WhatsApp +56 9 8246 3202.
- Several pages say samples can also be taken "a domicilio", but /domicilio/servicios is a 404: don't offer home sampling; suggest the call center if asked.

## Where the site disagrees with itself
- Hemograma: "Ayuno: 8 Horas" vs "el hemograma no requiere de ayuno" on the same page; the cotizador says "Sin indicaciones".
- Examen de orina particular: $5.130 (card) vs $1.960 (cotizador "Orina completa").
- Hormonas tiroideas particular: $19.110 (card) vs $19.440 (cotizador and /laboratorio "Perfil Tiroideo").
- PSA: the card "PSA total y libre" is $12.340 / $24.690; the cotizador's "Antígeno prostático específico" is $4.670 / $9.340 (possibly a different item; say which one you quote).
- Two curve pages with near-identical content and different titles ("Curva de intolerancia a la insulina" vs "Curva de tolerancia a la glucosa y de insulina").
