# Phantom Fish — Gestión administrativa

App para los dos socios: registrar **pagos, aportes, compras, ventas y comprobantes**
(PDF / imágenes), con control de que cada pago quedó bien repartido y export a Excel.

- **Backend:** FastAPI + SQLAlchemy
- **Base de datos:** SQLite (archivo `phantomfish.db`) — se puede abrir con
  [DB Browser for SQLite](https://sqlitebrowser.org) "como un Excel". Migrable a PostgreSQL
  cambiando `DATABASE_URL`.
- **Frontend:** HTML mobile-first servido por el mismo backend, instalable en el celular (PWA).
- **Cotización:** [dolarapi.com](https://dolarapi.com) (pública, sin API key). Siempre se
  muestra el valor para confirmarlo antes de guardar; nunca se aplica solo.

## Arrancar en local (Windows)

```powershell
./run.ps1
```

Eso crea el entorno, instala dependencias, copia `.env` y levanta el servidor en
`http://localhost:8000`. Si estás en la misma wifi, el celular entra por
`http://<IP-de-la-PC>:8000` (la IP la imprime el script).

### A mano (cualquier sistema)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/Mac: .venv/bin/python
cp .env.example .env                                       # y editar SECRET_KEY
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Primer ingreso

Usuarios que se crean solos la primera vez (contraseña = `SEED_PASSWORD` del `.env`,
por defecto `phantomfish`). Al entrar te obliga a cambiarla.

| Usuario     | Socio      | Reparto |
|-------------|------------|---------|
| `jairo`     | Jairo      | 35 %    |
| `sebastian` | Sebastián  | 65 %    |

Los porcentajes se editan en **Socios**. Cambiarlos no toca los pagos ya cargados.

## Cómo funciona el control de aportes

Cada pago guarda su total en ARS y en USD **congelados** (con la cotización usada ese día).
Al cargarlo, los aportes se reparten automático 35 / 65; con "Editar montos" se ajusta para
una excepción. La app muestra siempre dos celdas:

- **Total del pago**
- **Suma de aportes (Jairo + Sebastián)**

Si no coinciden, la fila queda marcada en rojo (en la app y en el Excel).

## Estructura

```
app/
  main.py            arranque FastAPI
  models.py          tablas (SQLAlchemy)
  money.py           Decimal exacto + tipos que no pierden centavos en SQLite
  auth.py            login por usuario/contraseña, sesión en cookie firmada
  storage.py         guardado de comprobantes en disco
  services/
    payments.py      cálculo ARS/USD y reparto de aportes
    summary.py       tablero (Resumen_Socios)
    exchange_rate.py cliente de dolarapi.com
    excel_export.py  genera la planilla .xlsx
  routers/           endpoints web
  templates/ static/ frontend
tests/               pytest (12 casos)
scripts/gen_icons.py regenera los íconos PWA (requiere Pillow)
schema.sql           esquema de referencia para PostgreSQL
```

## Tests

```bash
.venv/Scripts/python -m pytest -q
```

## Poner en producción (más adelante)

1. Servidor Linux (VPS DonWeb u otro) con Python 3.11+.
2. `DATABASE_URL` a PostgreSQL y correr las tablas (`schema.sql` o `python -m app.seed`).
3. `SECRET_KEY` nueva y larga; servir detrás de HTTPS (nginx / Caddy).
4. `uvicorn app.main:app` gestionado por systemd o un contenedor.
5. Backups del archivo `.db` (si seguís con SQLite) o `pg_dump` (si Postgres).
