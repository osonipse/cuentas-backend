# Cuentas Backend · MVP

Backend local que conecta la app Cuentas con [Enablebanking](https://enablebanking.com) para sincronizar movimientos bancarios automáticamente vía Open Banking PSD2.

## Arquitectura

```
App Cuentas (HTML)  ←→  Backend (FastAPI)  ←→  Enablebanking API  ←→  Banco
   localhost:8000           localhost:8000          api.enablebanking.com
```

El backend corre en tu máquina. Los datos se guardan en `data.json` localmente. Ningún dato de usuario se envía a servidores de Cuentas — solo las llamadas necesarias a Enablebanking para autenticar y descargar transacciones.

## Setup (5 minutos)

### 1. Ejecuta el setup automático
```bash
bash setup.sh
```

Esto instala dependencias, genera tu par de claves RSA y crea el `.env`.

### 2. Crea tu cuenta en Enablebanking
1. Ve a [enablebanking.com/sign-in](https://enablebanking.com/sign-in/)
2. Entra con tu email (magic link, sin contraseña)
3. Ve a **API Applications** → **New Application**
4. Sube `public_key.pem` (generada por el setup)
5. Copia tu **Application ID**

### 3. Configura el .env
```bash
nano .env
```
```env
EB_APP_ID=tu-application-id
EB_KEY_PATH=./private_key.pem
EB_SANDBOX=true   # Cambia a false cuando tengas cuenta de producción
```

### 4. Arranca el servidor
```bash
python3 main.py
```

### 5. Conecta tu banco
Abre en el navegador:
```
http://localhost:8000/connect?bank=BBVA&country=ES
```

Serás redirigido al banco. Tras autorizar, las transacciones se importan automáticamente y aparecen en la app.

## Endpoints

| Endpoint | Descripción |
|---|---|
| `GET /` | Panel de estado |
| `GET /banks?country=ES` | Bancos disponibles |
| `GET /connect?bank=BBVA&country=ES` | Inicia conexión con banco |
| `GET /callback` | Callback OAuth (automático) |
| `GET /transactions` | Transacciones guardadas |
| `GET /accounts` | Cuentas conectadas |
| `POST /sync` | Re-sincronizar todas las cuentas |
| `DELETE /data` | Borrar todos los datos locales |
| `GET /status` | Estado JSON |

## Bancos disponibles en España (sandbox)

- ✅ BBVA (sandbox completo)
- ✅ Sabadell (sandbox)
- ✅ Santander (producción)
- ✅ CaixaBank (producción)
- ✅ ING (producción)
- + todos los bancos de la lista Redsys

## Conectar con la app Cuentas

La app `finanza2.html` detecta automáticamente el backend si está corriendo en el puerto 8000. Busca el banner verde "Script activo" en la app.

Si la app no detecta el backend, ve a la URL directamente:
```
file:///ruta/a/finanza2.html?sync_port=8000
```

## Datos y privacidad

- Todo se guarda en `data.json` en tu máquina
- Enablebanking opera bajo su propia licencia AISP (licencia AISP propia no requerida para usar su API como partner)
- Las transacciones nunca se envían a servidores de Cuentas
- Puedes borrar todo con `DELETE /data` o borrando `data.json`

## Seguridad

- Guarda `private_key.pem` de forma segura — nunca la subas a GitHub
- El `.gitignore` ya la excluye
- Para producción, cambia `EB_SANDBOX=false` y despliega con HTTPS
