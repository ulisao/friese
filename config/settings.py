"""
Django settings for config project (Friese).

UN SOLO archivo de settings para los dos ambientes (tarea 6.1): todo lo que
cambia entre desarrollo y producción se resuelve por variables de entorno, sin
settings_dev / settings_prod separados. Así `manage.py`, `wsgi.py`, `asgi.py` y
los cron jobs de django-crontab siguen apuntando a `config.settings` y no hay
manera de correr un comando con el módulo de settings equivocado.

- `DJANGO_ENV` elige el ambiente: `development` (default) o `production`.
- En desarrollo, cada variable cae a un default cómodo para poder clonar el repo
  y correr sin configurar nada.
- En producción NO hay defaults para lo crítico: si falta algo, el proceso no
  arranca y el error lista todas las variables faltantes juntas (ver el chequeo
  al final del archivo).

La documentación de cada variable está en `.env.example`, en la raíz del repo.
"""

from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga de variables de entorno desde .env (raíz del repo). En producción las
# variables las inyecta la plataforma (Railway/Render) y no hay archivo .env:
# load_dotenv no hace nada si el archivo no existe, y nunca pisa una variable
# que ya venga del entorno real.
load_dotenv(BASE_DIR / ".env")


# --- Helpers de entorno -----------------------------------------------------

# Variables obligatorias que faltan. Se juntan todas y se reportan de una sola
# vez al final del archivo, para no tener que deployar N veces para descubrirlas
# de a una.
MISSING_ENV_VARS = []


def env(name, default=""):
    """Variable de entorno como texto, sin espacios sobrantes."""
    return os.environ.get(name, default).strip()


def env_bool(name, default):
    return env(name, "true" if default else "false").lower() == "true"


def split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def env_required(name):
    """Variable obligatoria en TODOS los ambientes."""
    value = env(name)
    if not value:
        MISSING_ENV_VARS.append(name)
    return value


def env_required_in_production(name, dev_default):
    """
    Variable obligatoria SOLO en producción; en desarrollo cae a `dev_default`.
    Son las que tienen un valor local razonable (localhost, la casilla de prueba
    de Resend) pero que en producción tienen que setearse a mano sí o sí.
    """
    value = env(name)
    if value:
        return value
    if IS_PRODUCTION:
        MISSING_ENV_VARS.append(name)
        return ""
    return dev_default


# --- Ambiente ---------------------------------------------------------------

DJANGO_ENV = env("DJANGO_ENV", "development").lower()
if DJANGO_ENV not in ("development", "production"):
    raise ImproperlyConfigured(
        f"DJANGO_ENV inválido: {DJANGO_ENV!r}. "
        "Valores válidos: 'development' o 'production'."
    )
IS_PRODUCTION = DJANGO_ENV == "production"


# SECURITY WARNING: keep the secret key used in production secret!
# El default sirve solo para desarrollo; en producción es obligatoria y además
# se rechaza explícitamente que sea esta misma clave.
DEV_SECRET_KEY = "django-insecure-dev-only-change-me"
SECRET_KEY = env_required_in_production("SECRET_KEY", DEV_SECRET_KEY)
# Cualquier clave con el prefijo que pone `startproject` es una clave de
# desarrollo, no solo la de arriba: Django la marca como insegura (W009 de
# `check --deploy`) y con ella se pueden forjar sesiones y tokens de reseteo.
if IS_PRODUCTION and SECRET_KEY.startswith("django-insecure-"):
    MISSING_ENV_VARS.append("SECRET_KEY (no puede ser una clave de desarrollo)")

# SECURITY WARNING: don't run with debug turned on in production!
# En producción DEBUG queda apagado siempre: no se puede prender por env, ni por
# error ni a propósito. La variable DEBUG solo tiene efecto en desarrollo.
DEBUG = False if IS_PRODUCTION else env_bool("DEBUG", True)

# En producción hay que listar los hosts reales (el dominio del backend); el
# default de localhost no sirve y dejarlo pasar daría 400 en todas las requests.
ALLOWED_HOSTS = split_csv(
    env_required_in_production("ALLOWED_HOSTS", "localhost,127.0.0.1")
)


# Application definition

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    # Blacklist de refresh tokens: necesaria para BLACKLIST_AFTER_ROTATION y para
    # la revocación manual desde el admin (ver docs/desarrollo.md sección 4).
    'rest_framework_simplejwt.token_blacklist',
    # Tareas periódicas sobre el cron del sistema (ver CRONJOBS más abajo).
    'django_crontab',
]

LOCAL_APPS = [
    'companies',
    'users',
    'catalog',
    'shipments',
    # Infraestructura, no dominio: no tiene modelos ni endpoints. Hoy vive acá el
    # backup de la base (tarea 7.1, `manage.py backup_database`).
    'ops',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# User extendido (company + role). Debe fijarse antes de la primera migración.
AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database — Supabase (PostgreSQL) vía DATABASE_URL.
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
# Obligatoria en los dos ambientes: no hay default posible. Si falta, el dict
# queda vacío y el chequeo del final del archivo corta con un error claro (antes
# de que Django intente conectarse a nada).

DATABASE_URL = env_required("DATABASE_URL")

DATABASES = {
    'default': (
        dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
        if DATABASE_URL
        else {}
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'es-ar'

TIME_ZONE = 'America/Argentina/Buenos_Aires'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images) — servidos con Whitenoise.
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Cache — lo usa el rate limiting de los endpoints públicos (tarea 6.2) para
# contar las requests de cada IP.
#
# Va en la BASE y no en el default (memoria del proceso) porque el contador tiene
# que ser UNO SOLO para todo el backend: el smoke test de la 6.6 midió que en
# producción pasaban ~120 requests por minuto contra un cupo de 30/min, porque
# gunicorn corre varios workers y cada uno llevaba su propia cuenta en su propia
# memoria (30 x 4 workers). Con el cache en la base los workers comparten el
# contador y el cupo vale lo que dice `DEFAULT_THROTTLE_RATES`. De paso, el
# contador sobrevive a los deploys (antes se reiniciaba en cada uno).
#
# La tabla se crea con `python manage.py createcachetable` (es idempotente: si ya
# existe, no hace nada). NO la crea `migrate`, así que va en el comando previo al
# deploy — ver railway.json.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": env("CACHE_TABLE", "friese_cache_table"),
        "OPTIONS": {
            # Default de Django: 300 entradas, y al llegar borra un tercio. Cada IP
            # que toca el endpoint público ocupa una entrada, así que con el default
            # una ráfaga desde muchas IPs podría descartar contadores vigentes —
            # justo lo que el límite tiene que sostener. 10k entradas es holgado y
            # la tabla se limpia sola.
            "MAX_ENTRIES": int(env("CACHE_MAX_ENTRIES", "10000")),
        },
    }
}


# DRF — autenticación por JWT por defecto.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Rate limiting de los endpoints públicos del receptor (tarea 6.2). Las clases
    # NO se aplican por default: se declaran vista por vista en shipments/views.py,
    # así el operador autenticado (que trabaja contra la misma API) nunca queda
    # limitado por el cupo del receptor. Ver shipments/throttling.py.
    #
    # Dos ventanas a la vez, el patrón burst/sustained de DRF: la corta corta el
    # martilleo inmediato; la larga corta el goteo constante que igual sumaría
    # miles de requests por hora. Los valores son generosos para un receptor real
    # (abre el link, sube N fotos de a una y responde: ~15 requests en total) y
    # cortos para un script.
    "DEFAULT_THROTTLE_RATES": {
        "public_burst": env("PUBLIC_THROTTLE_BURST", "30/min"),
        "public_sustained": env("PUBLIC_THROTTLE_SUSTAINED", "300/hour"),
    },
    # De qué IP se cuenta el cupo. En producción el backend está detrás del proxy
    # de la plataforma (Railway/Render), así que REMOTE_ADDR es el proxy y hay que
    # leer X-Forwarded-For: con NUM_PROXIES=1 DRF toma la ÚLTIMA dirección de la
    # cadena, que es la que agrega el proxy y el cliente no puede falsear (si se
    # dejara en None, DRF usaría la cadena entera, que sí es falseable con un
    # header inventado y permitiría saltarse el límite). En desarrollo no hay
    # proxy: 0 = usar REMOTE_ADDR y ignorar el header.
    "NUM_PROXIES": int(env("NUM_PROXIES", "1")) if IS_PRODUCTION else 0,
}

# JWT (djangorestframework-simplejwt) — valores EXACTOS de docs/desarrollo.md
# sección 4. No cambiar sin pedido explícito.
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=45),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=75),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# Cookie del refresh token (tarea 6.7). El refresh dejó de viajar en el cuerpo de
# la respuesta: vive en una cookie httpOnly, fuera del alcance de JavaScript.
REFRESH_COOKIE_NAME = env("REFRESH_COOKIE_NAME", "friese_refresh")
# El spec de la tarea proponía `Path=/api/auth/refresh/` para que el navegador la
# mande a un solo endpoint. Se usa `/api/auth/` porque el LOGOUT también necesita
# leerla para poder blacklistear el token, y con el path más angosto no la
# recibiría. Bajo `/api/auth/` solo viven login, refresh, logout y el alta por QR:
# la cookie sigue sin viajar en ninguna request de datos de la app.
REFRESH_COOKIE_PATH = env("REFRESH_COOKIE_PATH", "/api/auth/")

# El navegador solo manda la cookie si el frontend pide las credenciales
# (`withCredentials`) Y el backend declara que las acepta para ese origen.
CORS_ALLOW_CREDENTIALS = True


# Base del frontend público (receptor): con esto se arma el link del remito que
# se le envía al receptor al despachar. La pantalla del receptor (tarea 3.4) vive
# en la MISMA app de Vite que la del operador, en la ruta pública /remito/{token},
# así que en desarrollo el default es el dev server de Vite. En producción es
# obligatoria: con el default, todos los emails saldrían con un link a localhost.
FRONTEND_PUBLIC_URL = env_required_in_production(
    "FRONTEND_PUBLIC_URL", "http://localhost:5173"
)


# Resend — emails transaccionales por API HTTP (secciones 1.1 y 2.1).
# Si RESEND_API_KEY está vacía no se envía nada: el email queda en el log y la
# operación que lo disparó (el despacho) se completa igual.
# En producción es obligatoria: sin ella no sale ningún email del sistema.
RESEND_API_KEY = env_required_in_production("RESEND_API_KEY", "")
# Casilla remitente. Resend solo deja enviar desde un dominio VERIFICADO en la cuenta;
# mientras no haya uno, la única dirección disponible es onboarding@resend.dev, que
# además solo puede escribirle al dueño de la cuenta de Resend (sirve para probar, no
# para producción). Al verificar el dominio propio, basta con cambiar esta variable
# (ej. remitos@friese.app). El nombre visible lo arma el código con el de la empresa
# emisora (ver shipments/emails.py). Obligatoria en producción justamente porque el
# default solo le puede escribir al dueño de la cuenta de Resend.
RESEND_FROM_EMAIL = env_required_in_production(
    "RESEND_FROM_EMAIL", "onboarding@resend.dev"
)


# Horas que tienen que pasar desde el despacho, sin que el receptor abra el link,
# para mandarle el recordatorio (tarea 5.2, comando send_pending_reminders).
# El spec (sección 8, Fase 5) dice "X horas" sin definir X: 24 es una decisión de
# esa tarea, confirmada con el usuario. Un día hábil completo de margen, y el
# recordatorio sale a la misma hora del día que el despacho (no de madrugada).
REMINDER_AFTER_HOURS = int(env("REMINDER_AFTER_HOURS", "24"))


# Tamaño máximo de una foto de evidencia, en MB. Lo valida el serializer de la
# subida (shipments/serializers.py), y aplica igual al operador autenticado que al
# receptor por el link público — que es el que más importa, porque ese endpoint no
# tiene sesión. Una foto de celular de 12 Mpx ronda los 3-5 MB, así que 15 entra
# cómodo sin dejar la puerta abierta a subir cualquier cosa.
MAX_EVIDENCE_UPLOAD_MB = int(env("MAX_EVIDENCE_UPLOAD_MB", "15"))


# Tareas periódicas (django-crontab) — docs/desarrollo.md sección 6.
# Se registran en el cron del sistema con `python manage.py crontab add` (y se
# quitan con `crontab remove`) al deployar — requiere un host Linux con cron.
#
# 1) Cierre automático: los remitos despachados cuya ventana de respuesta de 48hs
#    venció sin respuesta del receptor pasan a 'accepted'. Se corre cada 15 minutos
#    (el spec fija la ventana de 48hs, no la frecuencia del chequeo): así el remito
#    se cierra a lo sumo 15 minutos después de vencer, y la query es una sola sobre
#    los remitos en 'dispatched'.
# 2) Recordatorio: los remitos despachados hace más de REMINDER_AFTER_HOURS cuyo
#    link nunca se abrió. Se corre cada hora: con un umbral medido en horas, afinar
#    más el minuto exacto del envío no aporta nada y evita una query de más.
CRONJOBS = [
    (
        "*/15 * * * *",
        "django.core.management.call_command",
        ["close_expired_shipments"],
    ),
    (
        "0 * * * *",
        "django.core.management.call_command",
        ["send_pending_reminders"],
    ),
]


# Cloudflare R2 — almacenamiento de las fotos de evidencia (secciones 1.1 y 2.1).
# Es S3-compatible: se accede con boto3 contra el endpoint de la cuenta. Las
# credenciales son obligatorias en producción: sin ellas la subida de evidencia
# (el corazón del producto) responde 502 en cada foto.
R2_ACCOUNT_ID = env_required_in_production("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = env_required_in_production("R2_ACCESS_KEY", "")
R2_SECRET_KEY = env_required_in_production("R2_SECRET_KEY", "")
R2_BUCKET_NAME = env_required_in_production("R2_BUCKET_NAME", "")
R2_ENDPOINT_URL = env(
    "R2_ENDPOINT_URL", f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
)
# Base de la URL que se guarda en Evidence.file_url. En desarrollo, si no se setea,
# cae al endpoint S3, que NO es accesible sin firmar. En producción es obligatoria
# y explícita (dominio propio del bucket, ver pendientes de la tarea 2.4): un
# file_url mal formado deja la evidencia inaccesible para siempre.
R2_PUBLIC_BASE_URL = env_required_in_production(
    "R2_PUBLIC_BASE_URL", f"{R2_ENDPOINT_URL}/{R2_BUCKET_NAME}"
)


# --- Backup de la base de datos (tarea 7.1) ---------------------------------
#
# El plan de Supabase del proyecto es el FREE, que NO incluye backups gestionados ni
# point-in-time-recovery: el dump que hace `manage.py backup_database` es la ÚNICA
# copia que existe de la base. El procedimiento de restauración está en BACKUP.md.
#
# Ninguna de estas variables entra en el chequeo de obligatorias del final del archivo,
# a propósito: si falta una, tiene que fallar el backup (que avisa por email y deja la
# ejecución del cron en rojo), no el arranque de la API. Un backup mal configurado no
# es motivo para tirar abajo el despacho de remitos.

# Conexión que usa pg_dump. Si está vacía se deriva del DATABASE_URL de la app,
# cambiando el puerto del pooler de Supabase de 6543 (modo transacción, que no sirve
# para pg_dump) a 5432 (modo sesión). Ver `ops/backup.build_backup_dsn`.
BACKUP_DATABASE_URL = env("BACKUP_DATABASE_URL")

# Binario de pg_dump. Tiene que ser de una versión >= la del servidor (Supabase corre
# PostgreSQL 17): un pg_dump viejo se niega a dumpear una base más nueva. En Railway
# lo instala `nixpacks.toml`; en el PATH del sistema alcanza con el nombre.
PG_DUMP_PATH = env("PG_DUMP_PATH", "pg_dump")
BACKUP_CONNECT_TIMEOUT_SECONDS = int(env("BACKUP_CONNECT_TIMEOUT_SECONDS", "30"))

# Bucket de backups: SEPARADO del de las fotos de evidencia y con su propio token de
# R2 (scopeado solo a él). Así, si se filtra la credencial de la app —que sube fotos
# desde un endpoint público, sin sesión— con ella no se pueden borrar los backups.
# Las claves caen a las de la app solo para poder probar el comando en desarrollo sin
# configurar un segundo token; en producción se setean las propias.
R2_BACKUP_BUCKET_NAME = env("R2_BACKUP_BUCKET_NAME", "friese-backup")
R2_BACKUP_ACCESS_KEY = env("R2_BACKUP_ACCESS_KEY") or R2_ACCESS_KEY
R2_BACKUP_SECRET_KEY = env("R2_BACKUP_SECRET_KEY") or R2_SECRET_KEY
R2_BACKUP_PREFIX = env("R2_BACKUP_PREFIX", "db")

# Retención. 30 días cubre el caso real que motiva un backup lógico: un borrado por
# error que nadie nota el mismo día. MIN_KEEP es un piso duro — la poda nunca deja
# menos de 7 copias, aunque estén todas vencidas, para que un cron caído mucho tiempo
# no termine vaciando el bucket.
BACKUP_RETENTION_DAYS = int(env("BACKUP_RETENTION_DAYS", "30"))
BACKUP_MIN_KEEP = int(env("BACKUP_MIN_KEEP", "7"))

# Antigüedad máxima aceptable del último backup. El criterio de la tarea es "menos de
# 24hs en todo momento" y el cron corre cada 12hs, así que 26 deja margen para que una
# corrida se atrase sin dar un falso positivo, y sigue avisando MUCHO antes de las 24
# reales (a las 26h ya se saltearon dos corridas seguidas).
BACKUP_MAX_AGE_HOURS = int(env("BACKUP_MAX_AGE_HOURS", "26"))

# Casillas que reciben el aviso si el backup falla o si el último quedó vencido
# (separadas por coma). Sin esto, un cron que se rompe pasa inadvertido justo hasta el
# día que hay que restaurar.
BACKUP_ALERT_EMAIL = env("BACKUP_ALERT_EMAIL")


# --- Respaldo de las fotos de evidencia (tarea 7.2) --------------------------
#
# El backup de la base guarda las URLs de las fotos, no los bytes. Las fotos son el
# producto, así que tienen su propia copia en un segundo bucket, que hace
# `manage.py backup_evidence`. R2 no implementa versionado de objetos (verificado:
# `list_object_versions` responde 501) ni replicación entre buckets, así que la copia
# es un job periódico. Detalle en `ops/evidence_backup.py` y en BACKUP.md sección 7.
#
# Igual que las del backup de la base, ninguna es obligatoria para arrancar: si falta
# una, falla el respaldo —que avisa por email—, no el despacho de remitos.

# Bucket destino, con su propio token scopeado solo a él. El endpoint es configurable
# aparte para poder mudar la copia a otra cuenta de Cloudflare o a otro proveedor
# S3-compatible sin tocar código. Las claves caen a las de la app solo para poder
# probar en desarrollo sin configurar un segundo token.
R2_EVIDENCE_BACKUP_BUCKET_NAME = env(
    "R2_EVIDENCE_BACKUP_BUCKET_NAME", "friese-evidence-backup"
)
R2_EVIDENCE_BACKUP_ACCESS_KEY = env("R2_EVIDENCE_BACKUP_ACCESS_KEY") or R2_ACCESS_KEY
R2_EVIDENCE_BACKUP_SECRET_KEY = env("R2_EVIDENCE_BACKUP_SECRET_KEY") or R2_SECRET_KEY
R2_EVIDENCE_BACKUP_ENDPOINT_URL = env(
    "R2_EVIDENCE_BACKUP_ENDPOINT_URL", R2_ENDPOINT_URL
)

# Carpeta dentro del bucket destino. Vacío = la copia conserva la MISMA key que el
# original, que es lo que hace que restaurar sea copiar de vuelta sin traducir nada.
R2_EVIDENCE_BACKUP_PREFIX = env("R2_EVIDENCE_BACKUP_PREFIX", "")

# A partir de cuántas horas una foto sin copiar deja de ser "recién subida" y pasa a
# ser un problema. La copia corre cada 6hs: 26 tolera varias corridas salteadas sin dar
# falsos positivos, y es el mismo criterio que BACKUP_MAX_AGE_HOURS.
EVIDENCE_BACKUP_MAX_AGE_HOURS = int(env("EVIDENCE_BACKUP_MAX_AGE_HOURS", "26"))


# CORS — permite al frontend (operador/receptor) consumir la API.
# En dev se listan los orígenes locales; en prod es obligatoria (los dominios de
# Vercel), porque con el default el frontend real no podría llamar a la API.
CORS_ALLOWED_ORIGINS = split_csv(
    env_required_in_production(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )
)


# --- Seguridad: HTTPS y headers (tarea 6.2) ---------------------------------

# Headers que van SIEMPRE, en los dos ambientes: no dependen de HTTPS, así que
# activarlos en desarrollo no rompe nada. Coinciden con los defaults de Django
# 5.1, pero se dejan explícitos para que estén a la vista y no cambien solos si
# un día cambia el default.
SECURE_CONTENT_TYPE_NOSNIFF = True  # X-Content-Type-Options: nosniff
X_FRAME_OPTIONS = "DENY"  # X-Frame-Options: nadie puede embebernos en un iframe
SECURE_REFERRER_POLICY = "same-origin"  # el token del link no viaja a terceros
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# HTTPS forzado — SOLO en producción. En desarrollo el server es http://localhost
# y cualquiera de estas opciones dejaría la app inaccesible (redirect a un https
# que no existe, o cookies que el browser nunca manda).
SECURE_SSL_REDIRECT = IS_PRODUCTION  # todo http:// se redirige a https://
SESSION_COOKIE_SECURE = IS_PRODUCTION  # la sesión del admin, solo por HTTPS
CSRF_COOKIE_SECURE = IS_PRODUCTION

if IS_PRODUCTION:
    # El TLS lo termina el proxy de la plataforma (Railway/Render) y la request
    # llega a Django por http: sin esto, Django la ve como insegura y
    # SECURE_SSL_REDIRECT la redirige a https… que vuelve a entrar igual → loop
    # infinito. Es seguro confiar en el header porque estas plataformas SIEMPRE
    # lo reescriben; detrás de un proxy que no lo haga, no habría que usarlo.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS: le dice al browser que a este dominio solo se entra por HTTPS, sin
# esperar al redirect (ni siquiera la primera request del día viaja en claro).
# Configurable por env para poder arrancar con un valor chico (ej. 3600) los
# primeros días de producción: mientras el header esté vigente, un browser que
# ya lo recibió NO va a poder entrar por http aunque se apague acá.
# PRELOAD queda en False: el preload de Chrome exige inscribir el dominio en una
# lista y sacarlo después lleva meses; no se declara algo que no se hizo.
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000")) if IS_PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = False

# Orígenes en los que Django confía para un POST con CSRF (form del admin). Con
# HTTPS forzado el admin se sirve por https y Django compara el Origin/Referer
# contra esta lista: si queda vacía, el login del admin falla la validación de
# CSRF. Por eso en producción, si no se setea la variable, se deriva de
# ALLOWED_HOSTS asumiendo https (que es lo único que se acepta).
CSRF_TRUSTED_ORIGINS = split_csv(env("CSRF_TRUSTED_ORIGINS")) or (
    [f"https://{host}" for host in ALLOWED_HOSTS if "*" not in host]
    if IS_PRODUCTION
    else []
)


# --- Chequeo final de configuración -----------------------------------------
# Se corre al importar los settings, así que si falta algo el proceso no arranca
# (ni runserver, ni gunicorn, ni un management command del cron).
if MISSING_ENV_VARS:
    raise ImproperlyConfigured(
        f"Faltan variables de entorno obligatorias (DJANGO_ENV={DJANGO_ENV}): "
        + ", ".join(MISSING_ENV_VARS)
        + ". Están documentadas en .env.example."
    )
