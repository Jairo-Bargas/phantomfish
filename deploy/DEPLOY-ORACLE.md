# Guía para publicar Phantom Fish en internet (paso a paso, detallada)

Al terminar vas a tener la app funcionando en una dirección tipo
`https://phantomfish.duckdns.org`, que abren los dos desde el celular **sin
depender de ninguna computadora prendida**, y **sin pagar nada**.

---

## Antes de empezar

Necesitás:

- **Una computadora personal con Windows 10 u 11** (la de Sebastián). No la del trabajo.
- **~40 minutos**, una sola vez.
- **Una tarjeta** (débito o crédito). Oracle la pide solo para verificar que sos una
  persona real. Con lo que vamos a usar **no cobra nunca**. Puede hacer una retención
  temporal de ~US$1 que se devuelve sola.
- **Un celular** a mano para probar al final.
- **El archivo `phantomfish-proyecto.zip`** (te lo pasa Jairo por pendrive).

No hace falta saber programar. Vas a copiar y pegar.

---

## Cómo leer esta guía

Vas a trabajar en **3 lugares distintos**. Cada paso te dice en cuál estás:

| Símbolo | Dónde | Qué es |
|---|---|---|
| 🌐 **NAVEGADOR** | Chrome / Edge | Páginas web de Oracle y DuckDNS. Se hace con el mouse. |
| 💻 **TU COMPU** | PowerShell | La terminal de Windows, corriendo en la compu de Sebastián. |
| 🖥️ **EL SERVIDOR** | PowerShell (después del `ssh`) | La **misma** ventana de PowerShell, pero conectada al servidor de Oracle. |

Sobre 💻 y 🖥️: es **una sola ventana** de PowerShell. Al principio los comandos
pasan en tu compu. Cuando corras el comando `ssh ...`, esa misma ventana "se
transforma" y todo lo que escribas pasa en el servidor. Cuando escribís `exit`,
vuelve a ser tu compu.

### Cómo abrir PowerShell

Menú Inicio → escribí **PowerShell** → Enter. Se abre una ventana azul o negra.
Ahí vas a pegar los comandos (clic derecho pega, o Ctrl+V).

---

## PARTE 1 — Traer el proyecto a la compu 💻

1. Copiá `phantomfish-proyecto.zip` del pendrive a la carpeta **Descargas**.
2. Clic derecho sobre el zip → **Extraer todo...** → **Extraer**.
3. Te queda una carpeta `phantomfish-proyecto` con archivos adentro (`app`, `deploy`,
   `Dockerfile`, etc.).
4. Abrí PowerShell y **entrá a esa carpeta**. Pegá esto (ajustá si la extrajiste en
   otro lado):

   ```powershell
   cd $HOME\Downloads\phantomfish-proyecto
   ```

   Para confirmar que estás bien parado, pegá `dir` y tenés que ver `app`, `deploy`,
   `Dockerfile`, `requirements.txt`.

✅ **Hasta acá:** el proyecto está en la compu y PowerShell está parado en su carpeta.

---

## PARTE 2 — Crear la cuenta de Oracle Cloud 🌐

1. Entrá a **https://www.oracle.com/cloud/free/** y clic en **Start for free**.
2. Elegí **Country/Territory: Argentina**. Poné tu mail y **Verify my email**.
3. Andá al mail, abrí el mensaje de Oracle y clic en el link de verificación.
4. Completá:
   - **Password:** una contraseña para la cuenta de Oracle (anotala).
   - **Cloud Account Name:** un nombre corto, por ejemplo `phantomfish`. (Es el
     nombre de tu "espacio" en Oracle, no importa mucho.)
   - **Home Region:** ⚠️ **IMPORTANTE, NO SE PUEDE CAMBIAR DESPUÉS.** Elegí
     **Brazil East (Sao Paulo)**. Si no aparece, **South America East (Vinhedo)**.
5. Cargá dirección y teléfono. Te llega un SMS con un código, ponelo.
6. **Add payment method:** cargá la tarjeta. Abajo dice que los recursos "Always
   Free" no se cobran. Aceptá.
7. Aceptá los términos → **Start my free trial**.
8. Espera 3–5 minutos mientras "prepara" la cuenta. Cuando termina te lleva al
   panel (se ve `cloud.oracle.com` con un menú ☰ arriba a la izquierda).

✅ **Hasta acá:** tenés cuenta de Oracle y estás dentro del panel.

> Si te dice que la región elegida no tiene capacidad para cuentas gratis, volvé a
> intentar con la otra (Sao Paulo ↔ Vinhedo).

---

## PARTE 3 — La llave SSH 💻

Es un par de archivos que funcionan como cerradura y llave, para entrar al servidor
sin contraseña. Se crean en **tu compu**.

1. En PowerShell, pegá:

   ```powershell
   ssh-keygen -t ed25519 -f $HOME\.ssh\phantomfish -C phantomfish
   ```

2. Te pregunta `Enter passphrase (empty for no passphrase):` → apretá **Enter**.
   Después `Enter same passphrase again:` → **Enter** de nuevo.
3. Muestra un texto raro con un dibujito de símbolos ("randomart"). Eso está **bien**.

   Ahora hay dos archivos en `C:\Users\<tu-usuario>\.ssh\`:
   - `phantomfish` → la llave **privada** (no se comparte, no se toca).
   - `phantomfish.pub` → la llave **pública** (esta la vamos a pegar en Oracle).

4. Mostrá la pública para copiarla. Pegá:

   ```powershell
   Get-Content $HOME\.ssh\phantomfish.pub
   ```

5. Aparece **una línea larga** que empieza con `ssh-ed25519 AAAA...` y termina en
   `phantomfish`. Seleccionala **completa** con el mouse y copiala (Ctrl+C).
   Dejala en el portapapeles para el próximo paso.

✅ **Hasta acá:** tenés la llave creada y la parte pública copiada.

---

## PARTE 4 — Crear el servidor 🌐

1. En el panel de Oracle, clic en el menú **☰** (arriba a la izquierda) →
   **Compute** → **Instances**.
2. Botón **Create instance**.
3. **Name:** escribí `phantomfish`.
4. **Placement / Security:** no toques nada, dejá lo que viene.
5. Sección **Image and shape**:
   - En **Image**, clic en **Edit** (o "Change image"). En la lista elegí
     **Canonical Ubuntu**. En "Image version" dejá **22.04**. Clic **Select image**.
   - En **Shape**, clic en **Edit** (o "Change shape"):
     - Pestaña **Ampere**.
     - Elegí **VM.Standard.A1.Flex**.
     - Abajo, **Number of OCPUs: 1** y **Amount of memory (GB): 6**.
     - Tiene que decir **"Always Free-eligible"**. Clic **Select shape**.
   - *Si más adelante al crear te dice "Out of host capacity":* volvé acá, en Shape
     entrá a **Specialty and previous generation** y elegí **VM.Standard.E2.1.Micro**
     (también dice "Always Free-eligible"). Es más chico pero alcanza.
6. Sección **Networking:** dejá todo como viene. Solo verificá que
   **"Assign a public IPv4 address"** esté en **Yes**.
7. Sección **Add SSH keys:**
   - Elegí la opción **Paste public keys**.
   - En el recuadro grande, **pegá** (Ctrl+V) la línea que copiaste en la Parte 3.
8. **Boot volume:** no toques nada.
9. Clic en **Create** (abajo).
10. La instancia aparece con un ícono **naranja** ("Provisioning"). Esperá 1–2
    minutos hasta que se ponga **verde** ("Running").
11. En la página de la instancia, buscá y **anotá** estos dos datos:
    - **Public IP address** → algo como `140.238.140.25`. **Copialo, lo vas a usar mucho.**
    - **Username** (en la sección "Instance access") → para Ubuntu es `ubuntu`.

✅ **Hasta acá:** el servidor existe y anda. Tenés su IP pública anotada.

En el resto de la guía, **cada vez que veas `LA_IP`, reemplazá por esa IP real.**

---

## PARTE 5 — Abrir los puertos 80 y 443 🌐

Por defecto el servidor no deja entrar tráfico web. Hay que habilitarlo.

1. En la página de la instancia, bajá hasta la sección **Primary VNIC**.
2. Clic en el link de la **Subnet** (dice algo como `subnet-20240101-1234`).
3. En la página de la subnet, sección **Security Lists** → clic en
   **Default Security List for vcn-...**.
4. Estás en la pestaña **Ingress Rules**. Clic en **Add Ingress Rules**.
5. Cargá la **primera** regla:
   - **Source Type:** CIDR
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Destination Port Range:** `80`
   - **Description:** `http`
6. Clic en **+ Another Ingress Rule** y cargá la **segunda**, igual pero:
   - **Destination Port Range:** `443`
   - **Description:** `https`
7. Clic en **Add Ingress Rules** (abajo).

✅ **Hasta acá:** el servidor acepta tráfico web.

---

## PARTE 6 — El nombre de la app (DuckDNS) 🌐

Un nombre gratis que apunta a tu servidor.

1. Entrá a **https://www.duckdns.org**.
2. Clic en alguno de los botones de arriba para entrar con tu cuenta
   (Google, GitHub, etc.). Es gratis y no piden tarjeta.
3. Ya adentro, vas a ver un recuadro **"domains"**. Escribí `phantomfish`
   (o el nombre que quieras) y clic en **add domain**.
4. Aparece una fila con `phantomfish`. En la columna **current ip**, escribí
   **LA_IP** (la IP pública de tu servidor) y clic en el botón de actualizar
   (el lápiz o "update ip").

✅ **Hasta acá:** `phantomfish.duckdns.org` lleva a tu servidor.

---

## PARTE 7 — Subir el proyecto al servidor 💻

1. En PowerShell (parado en la carpeta del proyecto, ver Parte 1), pegá esto
   **reemplazando `LA_IP`**:

   ```powershell
   scp -i $HOME\.ssh\phantomfish $HOME\Downloads\phantomfish-proyecto.zip ubuntu@LA_IP:~
   ```

2. La **primera vez** te dice algo como
   `The authenticity of host ... can't be established ... Are you sure you want to
   continue connecting (yes/no/[fingerprint])?` → escribí **`yes`** y Enter.
3. Muestra una barra de progreso y termina. El proyecto ya está en el servidor.

✅ **Hasta acá:** el `.zip` está en el servidor.

> **Si el comando se queda colgado o dice "Connection timed out":** el firewall de
> tu red (o del trabajo) está bloqueando el puerto 22. Probá desde otra red (datos
> del celular compartidos, por ejemplo). Si sigue, avisá y lo hacemos por otra vía.

---

## PARTE 8 — Instalar y arrancar 🖥️

1. **Conectate al servidor.** En PowerShell, pegá (con `LA_IP` real):

   ```powershell
   ssh -i $HOME\.ssh\phantomfish ubuntu@LA_IP
   ```

   Ahora el texto a la izquierda cambia a algo como `ubuntu@phantomfish:~$`.
   **Estás dentro del servidor.**

2. Descomprimí el proyecto y corré el instalador. Pegá **de a una** estas líneas:

   ```bash
   python3 -m zipfile -e ~/phantomfish-proyecto.zip ~/phantomfish
   ```
   ```bash
   bash ~/phantomfish/deploy/setup.sh
   ```

   El instalador baja Docker (tarda 1–2 min) y abre el firewall del servidor.
   Al final imprime un cartel con instrucciones.

3. **Salí y volvé a entrar** (esto es necesario para que Docker ande sin permisos
   especiales):

   ```bash
   exit
   ```
   ```powershell
   ssh -i $HOME\.ssh\phantomfish ubuntu@LA_IP
   ```

4. Preparás el archivo de configuración:

   ```bash
   cd ~/phantomfish/deploy
   ```
   ```bash
   cp .env.example .env
   ```
   ```bash
   nano .env
   ```

   Se abre un editor de texto dentro de la terminal. Cambiá **dos líneas**:
   - `SITE_ADDRESS=phantomfish.duckdns.org` → poné tu nombre real de DuckDNS.
   - `SEED_PASSWORD=cambiala-por-una-tuya` → poné una contraseña (la que van a usar
     Jairo y Sebastián la primera vez).

   Para guardar: **Ctrl+O**, Enter. Para salir: **Ctrl+X**.

5. Arrancá la app:

   ```bash
   docker compose up -d --build
   ```

   La **primera vez tarda varios minutos** (arma la app y saca el certificado de
   `https`). Cuando vuelve el cursor, mirá que esté todo bien:

   ```bash
   docker compose ps
   ```

   Los dos servicios (`app` y `caddy`) tienen que decir **running** o **Up**.

✅ **Hasta acá:** la app está corriendo en el servidor.

---

## PARTE 9 — Entrar y probar 🌐📱

1. En el navegador de la compu (o del celular), entrá a
   **https://phantomfish.duckdns.org** (tu nombre).

   > Si dice "no es seguro" o error de certificado: esperá 2–3 minutos y recargá.
   > Caddy tarda un poco en sacar el certificado la primera vez.

2. Ingresá:

   | Usuario     | Contraseña                          |
   |-------------|-------------------------------------|
   | `jairo`     | la que pusiste en `SEED_PASSWORD`   |
   | `sebastian` | la que pusiste en `SEED_PASSWORD`   |

3. La primera vez te obliga a cambiar la contraseña.
4. En el celular: menú del navegador → **"Agregar a pantalla de inicio"**. Queda
   como una app más.

🎉 **Listo. La app está publicada y funciona con todo apagado.**

---

## PARTE 10 — Actualizar la app más adelante

Cuando haya una versión nueva del proyecto (nuevo `.zip`):

**En tu compu** 💻 (parado en la carpeta del proyecto nuevo):

```powershell
scp -i $HOME\.ssh\phantomfish $HOME\Downloads\phantomfish-proyecto.zip ubuntu@LA_IP:~
```

**En el servidor** 🖥️:

```bash
python3 -m zipfile -e ~/phantomfish-proyecto.zip ~/phantomfish
cd ~/phantomfish/deploy
docker compose up -d --build
```

La base de datos y los comprobantes **no se tocan**: viven en un volumen aparte.

---

## PARTE 11 — Backups (hacelo cada tanto)

**En el servidor** 🖥️:

```bash
cd ~/phantomfish/deploy
docker compose cp app:/data/phantomfish.db ~/backup-$(date +%F).db
```

**En tu compu** 💻 (bajás la copia):

```powershell
scp -i $HOME\.ssh\phantomfish ubuntu@LA_IP:~/backup-*.db $HOME\Downloads\
```

Guardá esos archivos en un lugar seguro. Con ese archivo solo se puede reconstruir
todo.

---

## PARTE 12 — Si ya cargaste datos en la versión local (el `.bat`)

Solo si probaste la app en local y cargaste pagos reales.

1. Cerrá la ventana negra del `.bat`.
2. Copiá el archivo `phantomfish.db` (está en la carpeta del proyecto en la compu
   donde usaste el `.bat`) a **Descargas**.
3. **En tu compu** 💻:

   ```powershell
   scp -i $HOME\.ssh\phantomfish $HOME\Downloads\phantomfish.db ubuntu@LA_IP:~
   ```

4. **En el servidor** 🖥️:

   ```bash
   cd ~/phantomfish/deploy
   docker compose stop app
   docker compose cp ~/phantomfish.db app:/data/phantomfish.db
   docker compose start app
   ```

---

## Si algo no anda

**En el servidor** 🖥️, parado en `~/phantomfish/deploy`:

```bash
docker compose ps            # estado de los dos servicios
docker compose logs app      # errores de la app
docker compose logs caddy    # errores del certificado https
docker compose restart       # reiniciar todo
docker compose up -d --build # reconstruir y arrancar
```

| Síntoma | Qué revisar |
|---|---|
| La página no abre / "tardó demasiado en responder" | Puertos 80 y 443 en la Security List de Oracle (Parte 5). Y que DuckDNS tenga la IP correcta (Parte 6). |
| "No es seguro" / error de certificado | Esperá 2–3 min y recargá. Si sigue: `docker compose logs caddy`. Casi siempre es que el puerto 80 no está abierto o DuckDNS apunta mal. |
| `ssh` o `scp` se cuelgan | El puerto 22 está bloqueado en tu red. Probá desde otra red. |
| `docker: command not found` | No cerraste y volviste a abrir el `ssh` después del `setup.sh` (paso 3 de la Parte 8). |
| Entrás pero la app da error 500 | `docker compose logs app` y mandámelo. |

Cualquier error, sacá una captura o copiá el texto y pasámelo.
