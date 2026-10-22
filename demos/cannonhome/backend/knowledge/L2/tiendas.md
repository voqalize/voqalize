# Tiendas y retiro en tienda

Sources: https://cannonhome.cl/stores (header "Tiendas"; /nuestras-tiendas) ; https://cannonhome.cl/retiro-tiendas (incl. "Tiendas disponibles para retiro" and its FAQ) ; https://cannonhome.cl/politicas-de-despacho ("Retiro en tienda") ; https://cannonhome.cl/quienes-somos — crawled 2026-10-22

## Retiro en tienda: cómo funciona
- Se compra en cannonhome.cl y se elige **"Retiro en tienda"** en los métodos de envío, se selecciona la tienda y se indica quién retira (el titular o una persona autorizada). **Sin costo de despacho.**
- Solo en **productos, regiones y comunas seleccionadas**; la disponibilidad se informa durante la compra (en la ficha: "Ingresa tu ubicación" y "Stock en Tienda / Elige tu tienda").
- Llegan dos correos: la confirmación de compra y, cuando está listo, **"Listo para Retiro"**. Solo se retira después de ese segundo correo; la fecha estimada se informa en la compra.
- El pedido espera **7 días corridos** desde el primer aviso; después la compra se **anula automáticamente** y se devuelve el dinero (crédito: a la misma tarjeta; débito: Servicio al Cliente pide los datos para transferir).
- Solo se retira en **la tienda elegida**; no se puede cambiar después.
- Recomendaciones: llevar el QR y el número de pedido (en el celular o impresos), revisar el horario de la tienda, llevar bolsa propia.
- Si no llegó el correo "Listo para Retiro": revisar spam; ver el estado en "Seguimiento de envíos" (/sales/guest/form/).

### Qué se presenta (la página se contradice)
- Sección "¿Qué necesito para retirar mi compra?": el titular presenta **el código QR del correo y el número de pedido**; un tercero, lo mismo, "no se requiere autorización adicional ni documentación extra".
- Pasos y FAQ de la misma página: "Dirígete a la tienda con tu **cédula de identidad**" y "la persona que retira deberá presentar su cédula de identidad, junto con el número de orden"; si retira otra persona, "deberás proporcionar su **Nombre y Rut** al momento de realizar la compra".
- Say both: llevar QR, número de pedido y cédula; si retira otra persona, se indica al comprar.

## Tiendas (/stores, 53 listadas)
"Quiénes somos" dice **55 tiendas físicas**; /stores lista 53. Each store card has address, comuna, región, an email and "¿Cómo llegar?". La página las ordena por distancia si el navegador comparte ubicación.

- **Región Metropolitana**: Mall Alto Las Condes (Las Condes), Mall Alto Peñalolén, Mall Arauco Maipú, Mall Arauco Premium Outlet Buenaventura (Quilicura), Mall Barrio Independencia, Mall Costanera Center (Providencia), Mall Easton Outlet (Quilicura), Mall Florida Center (La Florida), Mall Midmall Outlet (Maipú), Mall Parque Arauco (Las Condes), Mall Paseo San Bernardo, Mall Patio Outlet Florida (La Florida), Mall Plaza Alameda (Estación Central), Mall Plaza Egaña (La Reina), Mall Plaza Oeste (Cerrillos), Mall Plaza Vespucio (La Florida), Mall Portal La Dehesa (Lo Barnechea), Mall Portal Ñuñoa, Mall Style Outlet (Pudahuel), Mall Vivo Imperio (Santiago, Huérfanos 840), Mall Vivo Maipú, Outlet La Fábrica (San Joaquín), Outlet Los Toros (Puente Alto), Tienda Centro 605 (21 de Mayo 605, Santiago), Tienda Liquidadora (Lampa), Tienda Outlet Irarrázaval (Pedro de Valdivia 3349, Ñuñoa), Tienda Padre Hurtado (Av. Padre Hurtado Norte 1225, Vitacura), Tienda Patronato (Patronato 407, Recoleta).
- **Antofagasta**: Mall Espacio Urbano Antofagasta, Mall Parque Angamos.
- **Coquimbo**: Mall Arauco Premium Outlet Coquimbo, Mall Open Plaza Ovalle, Mall Patio Outlet Peñuelas (La Serena).
- **Valparaíso**: CannonHome Espacio Urbano (Viña del Mar), Mall Arauco Premium Outlet Curauma (Valparaíso), Mall Open Plaza La Calera, Mall Paseo Quilpué, Mall Viña Park Outlet, Tienda Viña del Mar (14 Norte 961).
- **O'Higgins**: Mall Outlet Rancagua, Mall Plaza América (Rancagua).
- **Maule**: Mall Plaza Maule (Talca).
- **Ñuble**: Mall Arauco Chillán, Mall Vivo Outlet Chillán.
- **Biobío**: Mall Arauco Premium Outlet San Pedro (San Pedro de la Paz), Mall Plaza El Trébol (Talcahuano), Tienda Concepción Centro (Barros Arana 677).
- **Araucanía**: Mall Easton Temuco, Mall Vivo Outlet Temuco.
- **Los Ríos**: Mall Plaza de los Ríos (Valdivia).
- **Los Lagos**: Mall Outlet Paseo Alerce (Puerto Montt), Mall Paseo Chiloé (Castro), Mall Paseo Costanera (Puerto Montt).

## Tiendas para retiro y horarios (/retiro-tiendas)
Most mall stores open every day **10:00–20:00 / 20:30 / 21:00**. Street stores close on Sundays: Tienda Padre Hurtado (L–V 10:15–18:30, sáb 10:15–13:30), Tienda Outlet Irarrázaval (L–V 10:00–19:00, sáb 10:00–15:00), Tienda Outlet Patronato (L–V 10:00–18:00, sáb 10:00–16:00), Tienda Liquidadora Lampa (L–sáb 10:00–19:00), Tienda Centro 605 (L–sáb 10:00–19:00), Tienda Viña del Mar y Tienda Concepción Centro (L–V 09:30–19:30, sáb 10:00–15:00). The full list with each store's hours is in L3 `pages.json` (`/retiro-tiendas`); read the store's own line before quoting hours.

Pickup list also includes stores **not on /stores**: Mall Plaza Los Dominicos (Las Condes), Mall Plaza Tobalaba (Puente Alto), Mall Plaza Sur (San Bernardo). Stores on /stores but **not** on the pickup list include Costanera Center, Plaza Alameda, Outlet La Fábrica, Outlet Los Toros, Espacio Urbano Viña, Outlet Rancagua, Paseo Chiloé.

### Disagreements between the two lists
- Mall Parque Arauco: "Local 353 Nivel 3" (/stores) vs "Local 566" (/retiro-tiendas).
- Mall Alto Las Condes: "Local 2103" vs "Local 3080".
- Mall Arauco Maipú: "Local 665b - 666 - 667" vs "Local 318A-318B".
- Mall Easton Outlet: "Local 114" vs "Locales 221-C213".
- /retiro-tiendas gives Mall Paseo Quilpué the La Calera address (copy error) and Mall Viña Park Outlet no address.
When it matters, show /stores and say the store confirms.

## Comprar en tienda
- Mismos precios que online, aunque el sitio puede tener promociones exclusivas más bajas (FAQ 8).
- Cambios de compras online en cualquier tienda con la boleta (ver `cambios-y-devoluciones`).
