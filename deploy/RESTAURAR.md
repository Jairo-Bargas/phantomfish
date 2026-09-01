# Restaurar un respaldo

Solo si algo se borró/rompió y hay que volver a un estado anterior. Es una
operación delicada: **hace un backup del estado actual primero.**

Todo esto en el **servidor**, por SSH.

## 1. Ver los respaldos disponibles

```
ls -lh /data/backups
```

Los `db-YYYY-MM-DD.db` son solo la base. Los `full-YYYY-MM-DD.tgz` incluyen
también los comprobantes.

## 2. Restaurar solo la base de datos

```
cd /home/ubuntu/phantomfish/deploy
docker compose stop app
docker compose cp app:/data/phantomfish.db /home/ubuntu/db-antes-de-restaurar.db
docker compose run --rm --entrypoint sh app -c "cp /data/backups/db-2026-09-01.db /data/phantomfish.db && rm -f /data/phantomfish.db-wal /data/phantomfish.db-shm"
docker compose start app
```

(Cambiá `db-2026-09-01.db` por el archivo que quieras restaurar.)

## 3. Restaurar base + comprobantes (desde un `full-*.tgz`)

```
cd /home/ubuntu/phantomfish/deploy
docker compose stop app
docker compose run --rm --entrypoint sh app -c "
  cd /data &&
  cp phantomfish.db /home/ubuntu/db-antes.db 2>/dev/null || true &&
  tar xzf backups/full-2026-09-01.tgz &&
  mv phantomfish.db phantomfish.db.new &&
  rm -f phantomfish.db-wal phantomfish.db-shm &&
  mv phantomfish.db.new phantomfish.db
"
docker compose start app
```

## 4. Verificar

Entrá a la app y revisá que los datos estén como esperabas. Si algo quedó mal,
el estado anterior quedó guardado en `/home/ubuntu/db-antes-de-restaurar.db`.
