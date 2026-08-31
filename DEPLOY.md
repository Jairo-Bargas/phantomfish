# Publicar Phantom Fish en internet (Fly.io)

Objetivo: que la app viva en un servidor con una dirección `https://...` a la que
entren los dos desde el celular, **sin depender de tu PC ni de la wifi de casa**.

- **Costo:** ~US$2–4 por mes (una máquina chica siempre prendida + 1 GB de disco).
  Fly pide tarjeta al registrarse aunque el uso sea mínimo.
- **No necesitás instalar Docker.** Fly compila la app en sus servidores.
- Todo se hace desde **PowerShell**, parado en `C:\Cloude\PhantomFish`.

---

## Una sola vez: instalar la herramienta y crear la cuenta

### 1. Instalar `flyctl`

```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Cerrá y volvé a abrir PowerShell. Verificá con:

```powershell
fly version
```

Si dice "no se reconoce", agregá esta línea a PowerShell (la ruta la imprimió el instalador):

```powershell
$env:Path += ";$HOME\.fly\bin"
```

### 2. Crear la cuenta de Fly

```powershell
fly auth signup
```

Se abre el navegador. Registrate y cargá una tarjeta (es requisito de Fly).
Si ya tenés cuenta: `fly auth login`.

---

## Publicar (parado en `C:\Cloude\PhantomFish`)

### 3. Crear la app

```powershell
fly apps create phantomfish-gestion
```

Si el nombre está tomado, elegí otro (ej. `phantomfish-jairo`) y cambiá la línea
`app = "..."` arriba de todo en `fly.toml`.

### 4. Crear el disco persistente (base de datos + comprobantes)

```powershell
fly volumes create phantomfish_data --region eze --size 1 --yes
```

`eze` = Buenos Aires. Si tira que no hay capacidad, probá `gru` (San Pablo) o `scl`
(Santiago) y cambiá también `primary_region` en `fly.toml`.

### 5. Cargar las claves secretas

```powershell
fly secrets set SECRET_KEY="33a97682d16187d1b5c3e96166aa93da45b2d3baa17f44d4cb925e949218e62f" SEED_PASSWORD="elegí-una-contraseña-inicial"
```

`SEED_PASSWORD` es la contraseña con la que entran Jairo y Sebastián la primera vez
(después cada uno la cambia desde la app).

### 6. Desplegar

```powershell
fly deploy
```

Tarda unos minutos la primera vez. Cuando termina, la app está online.

### 7. Abrirla

```powershell
fly open
```

Te lleva a `https://phantomfish-gestion.fly.dev`. **Esa es la dirección** que se
guardan los dos en el celular ("Agregar a pantalla de inicio").

---

## Primer ingreso

| Usuario     | Contraseña            |
|-------------|-----------------------|
| `jairo`     | la de `SEED_PASSWORD` |
| `sebastian` | la de `SEED_PASSWORD` |

Al entrar te obliga a cambiarla.

---

## Cambios más adelante

Cada vez que se modifica el código:

```powershell
fly deploy
```

La base de datos y los comprobantes quedan intactos en el disco.

## Si ya cargaste pagos en la versión local

Después del primer `fly deploy`, subí tu archivo local y reiniciá:

```powershell
fly ssh sftp put phantomfish.db /data/phantomfish.db
fly apps restart phantomfish-gestion
```

(Hacelo antes de empezar a cargar datos en la versión online, para no pisar nada.)

## Comandos útiles

```powershell
fly logs                     # ver qué está pasando
fly status                   # estado de la máquina
fly ssh console              # entrar al servidor
fly ssh sftp get /data/phantomfish.db backup.db   # bajar un backup de la base
fly scale memory 512         # darle más memoria si hace falta
```

## Backups

La base entera es un archivo. Bajá una copia cada tanto:

```powershell
fly ssh sftp get /data/phantomfish.db "backup-$(Get-Date -Format yyyy-MM-dd).db"
```
