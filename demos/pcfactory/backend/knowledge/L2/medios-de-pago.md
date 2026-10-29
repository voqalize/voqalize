# Precios y medios de pago

Sources: https://www.pcfactory.cl/centro-de-ayuda/precios-y-medios-de-pago ; https://www.pcfactory.cl/centro-de-ayuda/terminos-y-condiciones (§3, §5) ; product and listing pages ; api.pcfactory.cl /catalogo/mediosdepago ; /black-days — read 2026-10-29

## Los tres precios (cómo decirlos)
Cada producto muestra tres montos (read live in a call, never from memory):
- **Transferencia / Débito** — el precio grande, el titular. Es el "Precio Efectivo / Precio Oferta Efectivo" de los T&C: pago con transferencia, depósito o ETPay (y en tienda, efectivo). Es hasta 5% menor que el precio con otros medios.
- **Otros medios de pago** — el precio con tarjeta de crédito (y otros medios). Es el "Precio Normal / Precio Oferta".
- **Precio de referencia** — el precio tachado: "el precio típico del producto en el mercado", para que veas cuánto ahorras. El "-N%" se calcula contra él.
- Site contradiction: the label says "Transferencia / Débito", but the T&C (§5.1) say debit "no se considera hecha en efectivo, pero puede dar origen a un descuento especial". The product API has a separate `debito` price that the page does not show. Say "con transferencia o débito" as the label does.
- Precios en pesos chilenos, con IVA. No incluyen despacho, garantía extendida ni otros cargos. Los precios de oferta se mantienen durante la vigencia informada o hasta agotar stock. En vitrinas y tiendas se publica el precio efectivo.
- Outlet Tecnológico: un solo precio, sin descuento por medio de pago.

## Medios de pago
- **Online**: transferencia (en el módulo del sitio, comprobante dentro de 72 horas) o **ETPay**; tarjetas de **débito y crédito emitidas en Chile** (Webpay/Transbank). **No se aceptan tarjetas internacionales en el sitio web.** El API de medios de pago lista: ETPay, Transferencia, RutPay (BancoEstado), CompraAquí, Webpay Débito, Webpay Crédito.
- **En tienda**: efectivo en pesos chilenos, transferencia/depósito, débito y crédito chilenos; tarjetas extranjeras (con Pin Pass, con pasaporte) solo en compra presencial.
- **Cuotas sin interés**: solo cuando se informa expresamente. /black-days: "hasta 12 cuotas sin interés en productos seleccionados con tarjetas de crédito Santander, Banco de Chile y BancoEstado" (event page; check on the product).
- Problemas con el pago: revisa datos de la tarjeta, saldo, conexión, que la tarjeta esté habilitada para compras online; luego tu banco; luego el formulario de contacto.
- Boleta o factura se elige en el paso de entrega y llega al correo.
