# Phantom Fish — Núcleo de gestión: esquema de base de datos

## Cómo se relacionan las tablas

```
partners (socios)
    │
    │  1 pago puede tener aportes de varios socios
    ▼
payment_contributions ──────► payments (pagos)
                                   │
                                   │ un pago puede cubrir una compra
                                   ▼
                              purchases (compras al proveedor)
                                   │
                                   ▼
                              purchase_items (detalle: producto, cantidad, precio)
                                   │
                                   ▼ (opcional, a futuro)
                              products (catálogo) ──► inventory_movements (stock)
                                   ▲
                                   │
                              sale_items ◄── sales (ventas)

documents   → referencia centralizada de comprobantes de cualquier tabla
audit_log   → quién cambió qué y cuándo
exchange_rate_log → historial de cotizaciones consultadas (auditoría)
```

## Decisiones de diseño y por qué

- **`payment_contributions` es una tabla aparte, no columnas `aporte1`/`aporte2`.**
  Así soporta que en el futuro haya un tercer socio, o que una compra la paguen
  entre tres personas, sin rediseñar nada.

- **`payments.amount_ars`, `amount_usd` y `exchange_rate` son fijos para siempre.**
  Igual que una factura no cambia si mañana cambia el dólar: el valor que se
  guardó el día del pago es el histórico real, no se recalcula después.

- **`purchase_items.product_name` y `sale_items.product_name` son una "foto" del
  nombre**, no solo un link al catálogo. Si el día de mañana renombran un
  producto, las ventas viejas no cambian retroactivamente.

- **`products` e `inventory_movements` ya están creadas pero no son obligatorias
  de usar desde el día uno.** Pueden cargar compras y ventas sin tocarlas, y
  activar el control de stock más adelante sin migrar nada.

- **`audit_log` desde el principio.** Cuando en seis meses alguien pregunte
  "¿por qué este número cambió", vas a poder reconstruirlo. Barato de tener,
  carísimo de no tener cuando hace falta.

- **`exchange_rate_log` separado de `payments.exchange_rate`.** El log guarda
  todo lo que la API de cotización devolvió (auditoría de la fuente externa);
  el pago guarda solo el valor que el usuario efectivamente confirmó y usó.

## Stack recomendado

- **Backend:** Python + FastAPI (tipado con Pydantic ayuda a evitar errores en
  cálculos de plata; se integra directo con `openpyxl` para el export a Excel).
- **Base de datos:** PostgreSQL.
- **Cotización:** `dolarapi.com` (pública, gratuita, sin API key) — el backend
  la consulta y el frontend siempre muestra el valor para confirmar antes de
  guardar, nunca se aplica en silencio.
- **Frontend:** evolución de la app que ya armamos (misma UI, ahora hablando
  contra la API en vez de guardar localmente).

## Próximos pasos en Claude Code

1. Pegar este esquema y crear el proyecto FastAPI + PostgreSQL (local con
   Docker o SQLite para arrancar, Postgres real antes de ir a producción).
2. Endpoints CRUD para `partners`, `payments`, `payment_contributions`,
   `purchases`, `purchase_items`, `sales`, `sale_items`.
3. Endpoint que consulta `dolarapi.com` y devuelve la cotización del día.
4. Endpoint `/export/excel` que arma el mismo formato de planilla que ya
   tienen, con `openpyxl`, a partir de los datos reales.
5. Conectar la app del celu a estos endpoints en vez de `window.storage`.
6. Login simple para los dos socios.
7. Elegir hosting (Postgres + backend): Railway, Render o Neon para arrancar
   gratis/barato; evaluar el VPS de DonWeb si prefieren todo en un solo lugar.
