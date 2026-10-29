# Ofertas del mes (el banner del inicio y el interruptor de campaña)

Sources: www.agroplanet.cl, home page hero carousel (the words are part of each slide's image; read 2026-10-29) and the listings' filters (`category/getCategory` facets, drawn as an on/off switch in "Filtros"). **Volatile: the campaign changes every month** (today "Octubre"). No prices here: a product's price and its offer are read live.

## El banner del inicio ("OCTUBRE CON ◎ DE OFERTAS")
Cada diapositiva dice "OCTUBRE CON ◎ DE OFERTAS", un recuadro rojo "HASTA nn% DCTO EN <rubro>" con la letra chica **"EN PRODUCTOS SELECCIONADOS"**, y el botón "Ver productos", que abre la categoría entera (no una lista de ofertas).

| El banner dice | "Ver productos" abre |
|---|---|
| Hasta 67% de descuento en repuestos de implementos | Repuestos de Implementos `/categoria/repuestos_de_implementos/AG17` |
| Hasta 50% en insumos | Insumos Agrícolas `/categoria/insumos_agricolas/AG16` |
| Hasta 50% en implementos | Implementos Agrícolas `/categoria/implementos_agricolas/AG12` |
| Hasta 30% en lubricantes | Lubricantes Y Fluidos `/categoria/lubricantes_y_fluidos/AG01` |
| Hasta 30% en neumáticos y cámaras | Neumáticos, Cámaras Y Llantas. `/categoria/neumaticos_camaras_y_llantas./AG05` |
| Hasta 30% en baterías | Baterías `/categoria/baterias/AG02` |
| Hasta 30% en "agrofertas" | El banner muestra motobombas, motosegadoras y partidores de leña (Agroferretería), pero su botón abre Repuestos de Implementos (AG17). Para las agrofertas, llevo a **Agroferretería** `/categoria/agroferreteria/AG15` con el interruptor "Agrofertas Octubre". |
| Hasta 28% en repuestos de tractor | Repuestos De Tractor `/categoria/repuestos_de_tractor/AG10` |

Digo que es **lo que dice el banner de este mes**, "hasta" y "en productos seleccionados": nunca prometo un porcentaje para un producto. El descuento de un producto lo leo en vivo.

## El interruptor de campaña (faceta "Campaña")
Algunos listados dibujan, sobre "Precio", un interruptor con el nombre de la campaña. Al encenderlo quedan solo los productos de la campaña y "Filtros Aplicados" muestra su nombre con una (x):
- **"Agrofertas Octubre"**: en Agroferretería (`/categoria/agroferreteria/AG15`) y en Implementos Agrícolas (`/categoria/implementos_agricolas/AG12`).
- **"Accesorios Octubre"**: en Baterías (`/categoria/baterias/AG02`), cables robacorriente.
Para "muéstrame solo las ofertas": filter_listing con `Campaña: Agrofertas Octubre` en esa categoría, o `{filter: Campaña | Agrofertas Octubre}` en el listado que está en pantalla.

No hay página de ofertas: /ofertas responde "Página no encontrada (404)", y buscar "oferta", "agrofertas" u "octubre" no encuentra nada.

## Cómo se ve el descuento
- La tarjeta del listado, la ficha, /carro y el Resumen de /cotizacion muestran el **precio normal**.
- El **"Subtotal:" del mini-carro** (el ícono del carro) aplica el descuento de la oferta.
- Por eso digo el precio que muestra la página, y que la tienda aplica el descuento (tanto por ciento) en el carro, quedando en torno al precio de oferta que leí en vivo. El precio firme llega con la cotización.
