# Friese

Plataforma B2B de trazabilidad logística: **evidencia fotográfica con fecha
certificada por servidor para remitos de entrega**.

El problema que resuelve es una discusión concreta del depósito: llegó menos
mercadería de la que dice el remito, o llegó rota, y no hay forma de probar en qué
estado salió. Friese deja registrada la foto del despacho, se la muestra al
receptor por un link único, y guarda su respuesta —conforme o queja— con fecha y
hora del servidor.

> **Alcance de la promesa:** el sistema tiene timestamp de servidor y hash SHA-256
> de cada foto. **No** tiene firma digital ni sellado de tiempo de un tercero
> confiable. El lenguaje de cara al cliente dice "reduce las discusiones", nunca
> "prueba irrefutable". Sostener esa distinción es deliberado.

---

## El flujo, de punta a punta

```
OPERADOR (app móvil)                RECEPTOR (link, sin login)
─────────────────────               ─────────────────────────
1. Crea el remito         draft
2. Agrega productos
3. Saca la foto                     (cámara en vivo, sin galería)
4. Despacha           dispatched ──► 5. Abre el link → arranca el reloj de 48hs
   · genera public_token               · ve remito, items y fotos
   · descuenta el trial                · saca su propia foto si hay problema
   · suma al UsageLog
   · manda el email               ┌──► 6a. Conforme      accepted
                                  ├──► 6b. Reporta       disputed → email al admin
                                  └──► 6c. Silencio 48hs accepted (auto_closed)
```

Las reglas que no son obvias y **conviene no romper**:

- El `public_token` se genera **solo al despachar**, nunca antes.
- El `link_opened_at` se sella en la **primera** apertura y no se toca más. Si se
  reescribiera en cada visita, el receptor podría correr el plazo para siempre.
- Un remito en `draft` se edita; **despachado es inmutable**.
- El `UsageLog` se actualiza **solo por signals**, nunca a mano.
- El cierre por silencio marca `auto_closed=True`, para distinguirlo de una
  aceptación expresa. La diferencia importa el día que haya una discusión.

---

## Stack

| Capa | Elección |
|---|---|
| Backend | Django 5.1 + Django REST Framework |
| Auth | `djangorestframework-simplejwt` (access 45 min, refresh 75 días, con rotación y blacklist) |
| Base | PostgreSQL 17.6 en Supabase — **plan Free** |
| Frontend | React 19 + Vite, **JavaScript sin TypeScript** |
| UI | shadcn/ui + Tailwind 4, modo oscuro |
| Estado | Zustand (en memoria, nunca `localStorage`) |
| Fotos | Cloudflare R2 (S3-compatible, vía boto3) |
| Emails | Resend (API HTTP) |
| Panel | Django Admin nativo, reskineado — sin frontend propio |
| Deploy | Backend en Railway, frontend en Vercel |

Python **3.13** (ver `.python-version`; `nixpacks.toml` pinnea `python313`).

---

## Estructura del repo

```
config/          settings, urls, branding del panel, páginas de error
users/           User, OperatorInvite, auth por cookie, reseteo de contraseña, QR
companies/       Company, UsageLog, tiers, mixins multi-tenant del admin
catalog/         Product (con unit obligatorio)
shipments/       Shipment, ShipmentItem, Evidence — el corazón del producto
support/         SupportTicket (soporte desde el panel del cliente)
ops/             Backups: base de datos y fotos de evidencia
smoke_tests/     37 scripts de verificación contra entornos reales
templates/       Admin, páginas de error, historial de cambios
static/admin/    CSS y logos del reskin del panel
frontend/        La app de Vite: operador Y receptor, un solo deploy
```

---

## Levantar el proyecto localmente

### Backend

```bash
py -3.13 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser
python manage.py runserver
```

`createcachetable` **no es opcional**: el rate limiting de los endpoints públicos
usa un cache en la base, y `migrate` no crea esa tabla.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Levanta en `http://localhost:5173`. El dev server proxea `/api` hacia
`http://127.0.0.1:8000`, así que el frontend y la API quedan en el mismo origen:
sin CORS y sin contenido mixto.

**Para probar la cámara desde el celular** hace falta contexto seguro
(`getUserMedia` solo corre en https o localhost):

```bash
DEV_HTTPS=1 npm run dev
```

---

## Variables de entorno

`.env.example` está documentado línea por línea — es la referencia real. El
resumen:

| Grupo | Variables |
|---|---|
| Ambiente | `DJANGO_ENV`, `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS` |
| Base | `DATABASE_URL` (pooler de Supabase) |
| Frontend | `FRONTEND_PUBLIC_URL`, `CORS_ALLOWED_ORIGINS` |
| R2 | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_BASE_URL` |
| Resend | `RESEND_API_KEY`, `RESEND_FROM_EMAIL` |
| Notificaciones | `REMINDER_AFTER_HOURS`, `SUPPORT_NOTIFICATION_EMAIL` |
| Backups | `R2_BACKUP_*`, `R2_EVIDENCE_BACKUP_*`, `BACKUP_ALERT_EMAIL` |

Dos cosas del diseño de la config que ahorran horas de debugging:

1. **`env_required_in_production()`** — en desarrollo hay defaults cómodos; en
   producción la variable es obligatoria y, si falta, **el arranque falla listando
   todas las que faltan de una vez**, no de a una.
2. **`FRONTEND_PUBLIC_URL` es una sola variable** y de ahí salen *todos* los links
   que el backend arma hacia la app: el remito del receptor, la invitación por QR,
   el reseteo de contraseña y el "Ver sitio" del panel. Es lo que evita que se
   escape un `localhost` a un email de producción.

El frontend tiene su propio `frontend/.env.example`. Ojo: Vite **embebe** las
variables en el build, así que cambiarlas en Vercel no tiene efecto sin un redeploy
con el cache desactivado.

---

## Modelos

| Modelo | Para qué |
|---|---|
| `Company` | El cliente. `trial_shipments_remaining` arranca en 10. `is_active` es la palanca de corte por falta de pago. |
| `User` | Operador o admin, siempre atado a una Company. Login individual, nunca compartido. |
| `OperatorInvite` | Token UUID que va en el QR. **Solo para el alta inicial**, jamás como login. |
| `Product` | `unit` es choices fijas: bolsas / kg / m3 / ton / unidad. |
| `Shipment` | El remito. Estados: draft → dispatched → accepted / disputed → closed. |
| `ShipmentItem` | Producto + cantidad + notas dentro de un remito. |
| `Evidence` | La foto. `type` dispatch o reception, `file_url` en R2, `file_hash` SHA-256. |
| `UsageLog` | Contador mensual por empresa para facturar. Tiers: 1–50 Arranque, 51–200 Crecimiento, 201+ Volumen. |
| `SupportTicket` | Soporte que abre el cliente desde su propio panel. |

`Shipment`, `Evidence`, `Company` y `User` llevan historial de cambios
(`django-simple-history`): queda registro de quién editó qué y cuándo, incluso
desde el Django Admin.

---

## API

Todo cuelga de `/api/`.

**Autenticación** — el refresh token viaja en una cookie httpOnly, no en JS.

```
POST /api/auth/login/                  access en body + refresh en cookie
POST /api/auth/refresh/                rota el token (blacklistea el anterior)
POST /api/auth/logout/
POST /api/auth/register-operator/      alta por token de invitación
POST /api/auth/password-reset/
POST /api/auth/password-reset/confirm/
```

**Operador** — requieren JWT y filtran por la company del usuario:

```
GET    /api/products/
GET    /api/shipments/
POST   /api/shipments/
GET    /api/shipments/{id}/
GET    /api/shipments/{id}/items/
POST   /api/shipments/{id}/items/
PATCH  /api/shipments/{id}/dispatch/   genera token, descuenta trial, manda email
POST   /api/shipments/{id}/evidence/   foto de despacho
```

**Receptor** — público, sin auth, con rate limit:

```
GET  /api/public/shipment/{token}/
POST /api/public/shipment/{token}/evidence/
POST /api/public/shipment/{token}/accept/
POST /api/public/shipment/{token}/dispute/
```

Las rutas públicas usan el converter `<uuid:token>`: un token con formato inválido
da 404 en el ruteo, sin llegar a tocar la base.

**El alta de productos y de invitaciones vive en el Django Admin**, no en la API.
El spec original listaba `POST /api/products/` y `/api/invites/`; se decidió
cubrirlos desde el panel y nunca se revirtió.

---

## Rutas del frontend

Una sola app de Vite sirve las dos caras del producto.

| Ruta | Quién | Auth |
|---|---|---|
| `/login` | Operador / admin | pública |
| `/` `/remitos/nuevo` `/remitos/:id` | Operador | protegida |
| `/remito/:token` | **Receptor** | pública |
| `/alta-operador/:token` | Operador nuevo (QR) | pública |
| `/recuperar-contrasena` `/restablecer/:uid/:token` | Cualquiera | pública |
| `/terminos` `/privacidad` | Cualquiera | pública |

---

## Producción

```
app.friese.com.ar   →  Vercel   (operador + receptor, un solo proyecto)
api.friese.com.ar   →  Railway  (Django + gunicorn, 2 workers)
                       Supabase (PostgreSQL 17.6, plan Free)
                       R2       (friese-evidence + los dos buckets de respaldo)
```

La API **tiene que** servirse desde `api.friese.com.ar` y no desde el
`.up.railway.app`: el refresh token va en cookie, y con la API en otro dominio la
cookie queda cross-site — que es exactamente lo que bloquea Safari en iPhone.

### Tareas periódicas

Seis servicios cron en Railway, todos sobre este mismo repo:

| Servicio | Comando | Frecuencia |
|---|---|---|
| `cron-close` | `close_expired_shipments` | cada 15 min |
| `cron-reminders` | `send_pending_reminders` | cada hora |
| `cron-backup` | `backup_database` | 3 y 15 hs |
| `cron-backup-check` | `backup_database --check-only` | 5 y 17 hs |
| `cron-evidence-backup` | `backup_evidence` | cada 6 hs |
| `cron-evidence-check` | `backup_evidence --check-only` | 8 hs |

Los chequeos corren **en servicios separados** del backup a propósito: si el cron
del backup no arranca nunca, no hay nadie adentro para avisar que falló.

**Cada uno de los seis necesita las 12 variables obligatorias de producción para
arrancar**, use o no lo que configuran. Es el error de deploy más común del
proyecto y está detallado en `BACKUP.md` sección 8.

---

## Backups

Dos copias separadas, porque son dos cosas distintas:

| Qué | Dónde |
|---|---|
| La base | `r2://friese-backup/db/`, retención 30 días |
| Las fotos | `r2://friese-evidence-backup/`, sin poda |

Supabase está en plan Free: **no hay backups gestionados ni PITR**. El dump de este
proyecto no es redundancia, es la única copia que existe.

El respaldo de fotos no tiene poda a propósito — podar es borrar, y borrar es
justo lo que esto evita.

**El procedimiento de restauración completo está en [`BACKUP.md`](BACKUP.md)**, y
se probó de punta a punta contra un dump real: la base restaurada quedó idéntica
tabla por tabla.

---

## Smoke tests

`smoke_tests/` tiene 37 scripts que corren contra entornos **reales** (base, R2,
Resend y el navegador de verdad), no contra mocks. No son tests unitarios:
verifican criterios de aceptación.

```bash
python smoke_tests/e2e.py            # flujo completo contra producción
python smoke_tests/e2e.py cleanup    # borra TODO lo que creó (base y R2)
python smoke_tests/state.py          # foto de la base, solo lectura
```

Algunos que vale la pena conocer:

| Script | Qué prueba |
|---|---|
| `e2e.py` / `ui_flow.py` | El MVP completo, por API y por navegador |
| `isolation.py` | Que una empresa no vea datos de otra |
| `evidence_hash.py` | Que el SHA-256 guardado sea el del archivo real |
| `evidence_restore_real.py` | Borra una foto **real** de R2 y la recupera del respaldo |
| `shared_throttle.py` | Que el rate limit cuente igual con varios workers |
| `audit_history.py` | Que editar desde el admin deje huella |
| `hardening.py` | Headers de seguridad en producción |

`e2e.py cleanup` existe porque estos scripts crean datos de verdad. Correrlo.

---

## Documentación del proyecto

Los documentos de especificación **no están en el repo** (`.gitignore`): producto,
desarrollo, diseño, tareas por fase, checklist legal/fiscal y el log de progreso
viven aparte, como archivos `Friese_*.md`.

`Friese_PROGRESS.md` es el estado real del proyecto: qué se hizo, cuándo, con qué
desvíos y qué quedó pendiente. **Leerlo antes de tocar nada.**

---

## Convenciones

- Frontend en **JavaScript puro**. Sin TypeScript.
- Login de operador **siempre individual**. Nunca compartido por dispositivo — es
  lo que sostiene que la evidencia sea atribuible a una persona.
- Los valores de JWT (45 min / 75 días / rotación / blacklist) **no se cambian**
  sin pedido explícito.
- El approach más simple que funcione. Sin abstracciones ni refactors no pedidos.
- Los comentarios del código explican **por qué**, no qué. Si un comentario deja de
  ser cierto, se actualiza en el mismo commit que lo invalida.

---

Proyecto privado. Todos los derechos reservados.
