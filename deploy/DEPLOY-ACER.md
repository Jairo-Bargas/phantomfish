# Guía para publicar Phantom Fish — versión para la notebook Acer (Windows 8)

Igual que la guía general, pero adaptada a Windows 8: se agrega **Git for Windows**
(que trae las herramientas de SSH que Windows 8 no tiene) y los comandos van en
**Git Bash** en vez de PowerShell.

Al terminar: la app en `https://phantomfish.duckdns.org`, funcionando sola, gratis.

---

## Los 3 lugares donde vas a trabajar

| Símbolo | Dónde | Qué es |
|---|---|---|
| 🌐 **NAVEGADOR** | El navegador de la Acer | Páginas de Oracle y DuckDNS. Con el mouse. |
| 💻 **GIT BASH** | La terminal negra que instala Git for Windows | Comandos en tu compu. |
| 🖥️ **EL SERVIDOR** | La **misma** Git Bash, después del comando `ssh` | Comandos en el servidor de Oracle. |

💻 y 🖥️ son **la misma ventana**: antes del `ssh` estás en tu compu, después estás
en el servidor, y con `exit` volvés.

Para pegar en Git Bash: **clic derecho** dentro de la ventana (Ctrl+V no siempre anda).

---

## PARTE 0 — Instalar Git for Windows 🌐

1. En el navegador de la Acer, entrá a **https://git-scm.com/download/win**.
2. Se baja solo el instalador ("64-bit Git for Windows Setup").
3. Ejecutalo. Va a pasar por muchas pantallas: **dejá todo como viene**, apretá
   **Next** en todas, y al final **Install**.
4. Al terminar, destildá "View Release Notes" y **Finish**.
5. Menú Inicio → escribí **Git Bash** → abrilo. Se abre una ventana negra con texto
   verde/violeta. Esa es la terminal que vas a usar.
6. Probá que quedó bien. Escribí y Enter:

   ```bash
   ssh -V
   ```

   Tiene que responder algo como `OpenSSH_9.x`. Si responde eso, está listo.

> **Si el instalador dice que no es compatible con tu Windows:** bajá una versión un
> poco más vieja desde
> https://github.com/git-for-windows/git/releases/tag/v2.47.1.windows.1
> (el archivo `Git-2.47.1-64-bit.exe`).

✅ **Hasta acá:** tenés Git Bash funcionando.

---

## PARTE 1 — Ubicar el zip 💻

El archivo `phantomfish-proyecto.zip` que pasaste por pendrive: fijate en qué carpeta
quedó. Lo más práctico es tenerlo en **Descargas**.

En Git Bash, comprobá que está ahí:

```bash
ls ~/Downloads/phantomfish-proyecto.zip
```

- Si responde la ruta del archivo → perfecto, seguí.
- Si dice `No such file or directory` → movelo a la carpeta Descargas con el
  explorador de Windows, o decime en qué carpeta está.

No hace falta descomprimirlo en la Acer. El zip entero se sube al servidor y se
descomprime allá.

✅ **Hasta acá:** sabés dónde está el zip.

---

## PARTE 2 — Crear la cuenta de Oracle Cloud 🌐

1. Entrá a **https://www.oracle.com/cloud/free/** → **Start for free**.
2. **Country/Territory: Argentina**. Poné tu mail → **Verify my email**.
3. Abrí el mail de Oracle y clic en el link de verificación.
4. Completá:
   - **Password:** una contraseña para la cuenta (anotala).
   - **Cloud Account Name:** algo corto, ej. `phantomfish`.
   - **Home Region:** ⚠️ **NO SE CAMBIA DESPUÉS.** Elegí **Brazil East (Sao Paulo)**.
     Si no está, **South America East (Vinhedo)**.
5. Dirección y teléfono. Te llega un SMS con un código, ponelo.
6. **Add payment method:** cargá la tarjeta (es verificación; lo "Always Free" no se
   cobra). Puede hacer una retención de ~US$1 que se devuelve.
7. Aceptá términos → **Start my free trial**.
8. Espera 3–5 min a que prepare la cuenta. Te lleva al panel (`cloud.oracle.com`,
   con un menú **☰** arriba a la izquierda).

✅ **Hasta acá:** cuenta creada, estás en el panel.

> Si el navegador de la Acer muestra mal alguna pantalla de Oracle, esa parte
> hacela desde el celular (el panel de Oracle anda en el navegador del teléfono).

---

## PARTE 3 — La llave SSH 💻

1. En Git Bash, pegá (clic derecho) y Enter:

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/phantomfish -C phantomfish
   ```

2. Pregunta `Enter passphrase (empty for no passphrase):` → **Enter**.
   `Enter same passphrase again:` → **Enter**.
3. Muestra un dibujito de símbolos ("randomart"). Está bien.
4. Mostrá la llave pública:

   ```bash
   cat ~/.ssh/phantomfish.pub
   ```

5. Aparece **una línea** que empieza con `ssh-ed25519 AAAA...` y termina en
   `phantomfish`. Seleccionala **completa** con el mouse y copiala (clic derecho →
   Copy, o Ctrl+Insert). Dejala en el portapapeles.

✅ **Hasta acá:** llave creada, parte pública copiada.

---

## PARTE 4 — Crear el servidor 🌐

1. Menú **☰** → **Compute** → **Instances** → **Create instance**.
2. **Name:** `phantomfish`.
3. **Placement / Security:** no toques nada.
4. **Image and shape:**
   - **Image** → **Edit** → **Canonical Ubuntu** → versión **22.04** → **Select image**.
   - **Shape** → **Edit** → pestaña **Ampere** → **VM.Standard.A1.Flex** →
     **1 OCPU**, **6 GB** de memoria → tiene que decir **"Always Free-eligible"** →
     **Select shape**.
   - *Si al crear te dice "Out of host capacity":* volvé a Shape → pestaña
     **Specialty and previous generation** → **VM.Standard.E2.1.Micro** (también
     gratis, más chico).
5. **Networking:** dejá todo. Verificá que **"Assign a public IPv4 address"** = **Yes**.
6. **Add SSH keys:** elegí **Paste public keys** y **pegá** la línea de la Parte 3.
7. **Boot volume:** no toques nada.
8. **Create**.
9. Ícono naranja ("Provisioning") → esperá 1–2 min → verde ("Running").
10. **Anotá** de la página de la instancia:
    - **Public IP address** (ej. `140.238.140.25`) — la vas a usar mucho.
    - **Username** (sección "Instance access") — para Ubuntu es `ubuntu`.

De acá en más, **donde diga `LA_IP`, poné esa IP real.**

✅ **Hasta acá:** servidor andando, IP anotada.

---

## PARTE 5 — Abrir los puertos 80 y 443 🌐

1. En la página de la instancia, bajá a **Primary VNIC** → clic en el link de la
   **Subnet**.
2. Sección **Security Lists** → **Default Security List for vcn-...**.
3. Pestaña **Ingress Rules** → **Add Ingress Rules**.
4. Primera regla:
   - **Source Type:** CIDR
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Destination Port Range:** `80`
   - **Description:** `http`
5. **+ Another Ingress Rule** → segunda regla, igual pero **Destination Port Range:
   `443`**, description `https`.
6. **Add Ingress Rules**.

✅ **Hasta acá:** el servidor acepta tráfico web.

---

## PARTE 6 — El nombre (DuckDNS) 🌐

1. Entrá a **https://www.duckdns.org** → iniciá sesión con Google/GitHub (gratis).
2. En el recuadro **"domains"** escribí `phantomfish` → **add domain**.
3. En la fila que aparece, columna **current ip**: poné **LA_IP** → botón de
   actualizar (lápiz / "update ip").

✅ **Hasta acá:** `phantomfish.duckdns.org` apunta a tu servidor.

---

## PARTE 7 — Subir el proyecto al servidor 💻

En Git Bash, pegá esto **con `LA_IP` reemplazada**:

```bash
scp -i ~/.ssh/phantomfish ~/Downloads/phantomfish-proyecto.zip ubuntu@LA_IP:~
```

- La **primera vez** dice `Are you sure you want to continue connecting (yes/no)?` →
  escribí **`yes`** y Enter.
- Muestra una barra de progreso y termina.

✅ **Hasta acá:** el zip está en el servidor.

> **Si se cuelga o dice "Connection timed out":** tu red bloquea el puerto 22. Probá
> compartiendo datos del celular a la compu, o avisame.

---

## PARTE 8 — Instalar y arrancar 🖥️

1. Conectate al servidor:

   ```bash
   ssh -i ~/.ssh/phantomfish ubuntu@LA_IP
   ```

   El texto a la izquierda cambia a `ubuntu@phantomfish:~$`. **Estás en el servidor.**

2. Descomprimí y corré el instalador (de a una línea):

   ```bash
   python3 -m zipfile -e ~/phantomfish-proyecto.zip ~/phantomfish
   ```
   ```bash
   bash ~/phantomfish/deploy/setup.sh
   ```

   Baja Docker (1–2 min) y abre el firewall del servidor.

3. Salí y volvé a entrar (necesario para que Docker ande sin permisos especiales):

   ```bash
   exit
   ```
   ```bash
   ssh -i ~/.ssh/phantomfish ubuntu@LA_IP
   ```

4. Configuración:

   ```bash
   cd ~/phantomfish/deploy
   ```
   ```bash
   cp .env.example .env
   ```
   ```bash
   nano .env
   ```

   En el editor cambiá **dos líneas**:
   - `SITE_ADDRESS=phantomfish.duckdns.org` → tu nombre real de DuckDNS.
   - `SEED_PASSWORD=cambiala-por-una-tuya` → una contraseña para el primer ingreso.

   Guardar: **Ctrl+O**, Enter. Salir: **Ctrl+X**.

5. Arrancá:

   ```bash
   docker compose up -d --build
   ```

   La primera vez **tarda varios minutos**. Cuando vuelve el cursor:

   ```bash
   docker compose ps
   ```

   Los dos servicios (`app` y `caddy`) tienen que decir **running** / **Up**.

✅ **Hasta acá:** la app corre en el servidor.

---

## PARTE 9 — Entrar y probar 🌐📱

1. En el navegador (compu o celular): **https://phantomfish.duckdns.org**.

   > Si dice "no es seguro" o error de certificado: esperá 2–3 min y recargá.

2. Entrá con usuario `jairo` o `sebastian`, contraseña = la de `SEED_PASSWORD`.
   Te obliga a cambiarla.
3. En el celular: menú del navegador → **"Agregar a pantalla de inicio"**.

🎉 **Listo.**

---

## Actualizar más adelante

💻 en Git Bash (con el zip nuevo en Descargas):

```bash
scp -i ~/.ssh/phantomfish ~/Downloads/phantomfish-proyecto.zip ubuntu@LA_IP:~
```

🖥️ en el servidor:

```bash
python3 -m zipfile -e ~/phantomfish-proyecto.zip ~/phantomfish
cd ~/phantomfish/deploy
docker compose up -d --build
```

La base de datos y los comprobantes no se tocan.

## Backups (cada tanto)

🖥️ en el servidor:

```bash
cd ~/phantomfish/deploy
docker compose cp app:/data/phantomfish.db ~/backup-$(date +%F).db
```

💻 en Git Bash (bajás la copia):

```bash
scp -i ~/.ssh/phantomfish ubuntu@LA_IP:~/backup-*.db ~/Downloads/
```

## Si algo no anda

🖥️ en `~/phantomfish/deploy`:

```bash
docker compose ps
docker compose logs app
docker compose logs caddy
docker compose restart
```

| Síntoma | Revisar |
|---|---|
| La página no abre | Puertos 80/443 en la Security List de Oracle (Parte 5) + DuckDNS con la IP correcta (Parte 6). |
| Error de certificado | Esperá 2–3 min. Si sigue: `docker compose logs caddy`. |
| `ssh`/`scp` se cuelgan | Puerto 22 bloqueado en tu red. Probá otra red. |
| `docker: command not found` | Faltó salir y volver a entrar por `ssh` después del `setup.sh` (Parte 8, paso 3). |

Cualquier error: captura o texto, y me lo pasás.
