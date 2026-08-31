# Actualizar la app (subir una versión nueva)

La base de datos y los comprobantes viven en un volumen de Docker aparte
(`phantomfish_appdata`), así que **actualizar el código nunca toca los datos.**

Las **migraciones son automáticas**: al arrancar, la app crea las tablas nuevas y
agrega las columnas nuevas si faltan (nunca borra ni cambia datos existentes).
No hay que correr nada a mano.

**Recomendado antes de una actualización con cambios de base:** bajá un backup
(último comando de esta guía).

---

## Opción A — Con GitHub (recomendado, una vez configurado)

### Configuración inicial (una sola vez)

1. Crear un repositorio **privado** en github.com llamado `phantomfish`
   (sin README).
2. En la compu donde está el proyecto:

   ```
   git remote add origin https://github.com/TU-USUARIO/phantomfish.git
   git push -u origin main
   ```

   (Git abre el navegador para que inicies sesión en GitHub la primera vez.)

3. Pasar el servidor a usar Git. Conectado por SSH al servidor:

   ```
   cd ~
   docker compose -f phantomfish/deploy/docker-compose.yml down
   rm -rf phantomfish
   git clone https://github.com/TU-USUARIO/phantomfish.git phantomfish
   ```

   Volver a poner el `.env` (SITE_ADDRESS y SEED_PASSWORD):

   ```
   cd ~/phantomfish/deploy
   cp .env.example .env
   nano .env
   docker compose up -d --build
   ```

### Cada actualización (de ahí en más)

En la compu del proyecto: `git add -A && git commit -m "cambios" && git push`

En el servidor (por SSH):

```
cd ~/phantomfish
git pull
cd deploy
docker compose up -d --build
```

---

## Opción B — Con pendrive + zip (como la primera vez)

En la compu: llevás `phantomfish-proyecto.zip` al pendrive.

En el servidor (Git Bash → SSH):

```
scp -i /c/Users/Jairo/.ssh/phantomfish /e/Descargas/phantomfish-proyecto.zip ubuntu@LA_IP:.
```

Después, conectado por SSH al servidor:

```
python3 -m zipfile -e phantomfish-proyecto.zip phantomfish
cd phantomfish/deploy
docker compose up -d --build
```

> Nota: `python3 -m zipfile -e` sobrescribe archivos pero no borra los que ya no
> existen. Para una actualización 100% limpia con este método, borrá primero
> `~/phantomfish` (los datos están en el volumen, no ahí) y volvé a extraer + poner
> el `.env`.

---

## Verificar que quedó bien

```
docker compose ps          # app y caddy en "running"
docker compose logs app --tail 20
```

Y entrá a `https://tu-nombre.duckdns.org`.

## Backup antes de una actualización grande

```
docker compose cp app:/data/phantomfish.db ~/backup-$(date +%F).db
```
