# Backup y restauración — Friese

Todo lo que hay que saber para no perder los datos, y para recuperarlos si se pierden.
Son **dos** copias separadas, porque son dos cosas distintas:

| Qué | Dónde | Sección |
|---|---|---|
| La **base** (remitos, empresas, usuarios) | `r2://friese-backup/db/` | 1 a 6 |
| Las **fotos de evidencia** | `r2://friese-evidence-backup/` | [7](#7-respaldo-de-las-fotos-de-evidencia) |

Si estás acá porque algo se rompió: [restaurar la base](#3-restauración) o
[recuperar una foto](#72-recuperar-una-foto).

---

## 1. Qué cubre Supabase (confirmado)

El proyecto está en el **plan Free de Supabase**, que **no incluye backups
gestionados ni point-in-time-recovery**. Los backups diarios arrancan en el plan Pro
(retención de 7 días) y el PITR es un add-on aparte, arriba del Pro.

O sea: **del lado de Supabase no hay nada que restaurar**. Si la base se borra, se
corrompe o alguien ejecuta un `DELETE` sin `WHERE`, la única copia que existe es la que
hace este proyecto.

> Para verificarlo o para ver si el plan cambió: dashboard de Supabase → el proyecto →
> **Database → Backups**. En el plan Free esa pantalla ofrece contratar Pro; no lista
> backups.

Por eso el backup propio de acá abajo **no es redundancia, es la red principal**.

---

## 2. Qué hace el backup automático

Un `pg_dump` completo del esquema `public` (que es todo lo que la aplicación usa),
comprimido y subido a un bucket de Cloudflare R2 separado del de las fotos.

| | |
|---|---|
| Comando | `python manage.py backup_database` |
| Dónde corre | Railway, servicio cron propio (`railway.cron-backup.json`) |
| Cada cuánto | **cada 12 horas** — 03:00 y 15:00 UTC (00:00 y 12:00 de Argentina) |
| Vigilancia | un segundo cron chequea a las 05:00 y 17:00 UTC que haya backup fresco |
| Destino | `r2://friese-backup/db/AAAA/MM/friese-db-AAAAMMDDTHHMMSSZ.sql.gz` |
| Formato | SQL plano comprimido con gzip (se restaura con `psql`, sin `pg_restore`) |
| Retención | 30 días, y **nunca menos de 7 copias** aunque estén todas vencidas |
| Tamaño hoy | ~45 KB comprimidos (base de 12 MB) |
| Si falla | sale un email a `BACKUP_ALERT_EMAIL` y la corrida queda en rojo en Railway |

**Por qué cada 12hs y no cada 24:** el criterio es tener siempre un backup de menos de
24hs. Con una corrida diaria, cualquier falla suelta ya incumple. Con dos, una corrida
que falla todavía deja el último backup en 24hs.

**Qué NO incluye:** las fotos de evidencia. Están en R2, no en la base; el dump solo
guarda sus URLs. Esas tienen su propia copia: ver la [sección 7](#7-respaldo-de-las-fotos-de-evidencia).

### Verificar que hay un backup fresco

```bash
python manage.py backup_database --check-only
```

Sale con código 0 e imprime el último backup y su antigüedad. Si no hay ninguno, o si
el más nuevo pasó `BACKUP_MAX_AGE_HOURS` (26 por default), sale con código != 0 y manda
el aviso por email.

Esto corre **solo, dos veces por día** en un segundo servicio cron
(`railway.cron-backup-check.json`), a las 05:00 y 17:00 UTC — **dos horas después de
cada backup**.

**Por qué hace falta un chequeo aparte, si el backup ya avisa cuando falla:** porque
solo avisa si *corre*. Si el servicio cron se borra, queda pausado o nunca se dio de
alta, no falla nada — simplemente no pasa nada, y eso no genera ningún aviso. El
chequeo mira el bucket desde afuera, así que detecta la ausencia además de la falla.

Con backups cada 12hs y un límite de 26hs, la cuenta queda así:

| Situación | Antigüedad al chequear | Resultado |
|---|---|---|
| Todo bien | 2hs | OK |
| Se salteó **una** corrida | 14hs | OK (todavía dentro de las 24hs) |
| Se saltearon **dos seguidas** | 26hs | **Avisa** |

Si preferís enterarte apenas se saltea una sola corrida, poné
`BACKUP_MAX_AGE_HOURS=14`. Avisa antes, a cambio de algún falso positivo cuando una
corrida se atrasa.

---

## 3. Restauración

Probado de punta a punta el **2026-08-12** contra un dump real de producción: la base
restaurada quedó **idéntica tabla por tabla** a la de producción y la aplicación
funciona sobre ella (ver la entrada de la tarea 7.1 en `PROGRESS.md`).

### Antes de empezar

Necesitás **psql 17.6 o más nuevo**. Dos motivos: el dump viene de PostgreSQL 17.6, y
usa las directivas `\restrict` / `\unrestrict`, que un psql anterior no entiende.

> **El editor SQL del dashboard de Supabase no sirve** para esto: no procesa las
> directivas de psql. Hay que usar `psql` de verdad.

En Windows no viene nada instalado: bajar los binarios (sin instalador, sin permisos de
administrador) de `https://get.enterprisedb.com/postgresql/postgresql-17.6-1-windows-x64-binaries.zip`
y descomprimir; `psql.exe` queda en `pgsql\bin`.

### Paso 1 — Bajar el backup que querés restaurar

Desde el dashboard de Cloudflare (R2 → bucket `friese-backup` → carpeta `db/`), o
desde Python con las credenciales del proyecto:

```python
# python manage.py shell
from ops.backup import get_backup_client, list_backups
from django.conf import settings

client = get_backup_client()
backups = list_backups(client)          # del más viejo al más nuevo
for b in backups[-10:]:
    print(b["LastModified"], b["Size"], b["Key"])

key = backups[-1]["Key"]                # el más reciente
client.download_file(settings.R2_BACKUP_BUCKET_NAME, key, "backup.sql.gz")
print("bajado:", key)
```

Descomprimir:

```bash
gzip -dc backup.sql.gz > backup.sql
```

### Paso 2 — Comprobar que el archivo está entero

```bash
tail -5 backup.sql
```

Tiene que terminar con `-- PostgreSQL database dump complete`. Si esa línea no está, el
dump está cortado: **no lo uses**, agarrá el anterior.

### Paso 3 — Preparar la base destino

Nunca restaures encima de la base que estás investigando: primero levantás la copia,
mirás que esté bien, y recién después decidís.

```bash
createdb -h HOST -p PUERTO -U USUARIO friese_restore

# El dump trae `CREATE SCHEMA public;`, así que el schema public que Postgres crea
# solo tiene que salir de en medio o el restore falla en la primera sentencia.
psql -h HOST -p PUERTO -U USUARIO -d friese_restore \
     -c "DROP SCHEMA IF EXISTS public CASCADE;"
```

### Paso 4 — Restaurar

```bash
psql -h HOST -p PUERTO -U USUARIO -d friese_restore \
     -v ON_ERROR_STOP=1 -f backup.sql
```

**`ON_ERROR_STOP=1` no es opcional.** Sin eso psql sigue de largo ante cualquier error
y termina con código 0 dejándote media base restaurada, que es peor que ninguna.

### Paso 5 — Confirmar que la aplicación funciona sobre la base restaurada

```bash
DATABASE_URL="postgresql://USUARIO:PASS@HOST:PUERTO/friese_restore" \
  python manage.py migrate --check
```

Sin salida y código 0 significa que el esquema restaurado es exactamente el que esperan
las migraciones del repo. Después, un chequeo rápido de datos:

```bash
DATABASE_URL="..." python manage.py shell -c "
from shipments.models import Shipment, Evidence
from users.models import User
print('remitos', Shipment.objects.count())
print('fotos', Evidence.objects.count())
print('usuarios', User.objects.count())
"
```

### Paso 6 — Poner la base restaurada en producción

Solo cuando el paso 5 haya dado bien: cambiar `DATABASE_URL` en Railway (en los
**cuatro** servicios: web y los tres crons) y redeployar.

### Restaurar en un proyecto nuevo de Supabase

Es el caso de desastre real. Mismos pasos, con tres detalles:

1. La conexión tiene que ser el **pooler en modo sesión (puerto 5432)** o la conexión
   directa. Por el pooler de transacción (6543) el restore falla.
2. Un proyecto nuevo ya trae el schema `public`: aplica igual el `DROP SCHEMA` del
   paso 3.
3. El dump se toma con `--no-privileges`, así que no restaura los `GRANT` de los roles
   de Supabase. **A este proyecto no le hace falta** (Django se conecta con un solo rol
   y no usa PostgREST ni Supabase Auth). Si algún día se usara la API de Supabase,
   habría que reponerlos a mano:
   ```sql
   GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
   GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;
   ```

### Recuperar UNA tabla o unas filas, sin pisar todo

El caso más frecuente no es perder la base entera, es un borrado por error. Restaurá el
dump en una base aparte (pasos 1 a 4) y copiá de ahí solo lo que falta:

```bash
# Ejemplo: recuperar un remito borrado, con sus items y sus fotos.
psql -d friese_restore -c "\copy (select * from shipments_shipment where id = 246) to 'remito.csv' csv"
psql -d PRODUCCION      -c "\copy shipments_shipment from 'remito.csv' csv"
```

Ojo con el orden: primero la empresa y el usuario, después el remito, después los items
y la evidencia. Al revés, las foreign keys rechazan el INSERT.

---

## 4. Puesta en marcha

Lo que hay que configurar una sola vez para que el backup empiece a correr.

### 4.1 — Bucket y token en Cloudflare

1. R2 → **Create bucket** → nombre `friese-backup`.
   **Dejarlo privado**: sin dominio público ni URL `r2.dev`. El dump tiene emails,
   hashes de contraseña y los tokens públicos de todos los remitos.
2. R2 → **Manage API Tokens** → **Create API Token**:
   - Permiso **Object Read & Write**
   - **Specify bucket** → solo `friese-backup`
3. Guardar el Access Key ID y el Secret Access Key.

> El token que usa la app para subir fotos (`R2_ACCESS_KEY`) está scopeado a
> `friese-evidence` y **no puede** crear buckets ni tocar este. Es a propósito: ese
> token vive en un backend que expone endpoints públicos sin sesión, y si se filtra no
> tiene que alcanzar para borrar los backups.

### 4.2 — Variables en Railway

En el servicio nuevo de backup **y** en el web (para poder correr `--check-only` a
mano), además de las que ya tiene el proyecto:

```
R2_BACKUP_BUCKET_NAME=friese-backup
R2_BACKUP_ACCESS_KEY=<el del token nuevo>
R2_BACKUP_SECRET_KEY=<el del token nuevo>
BACKUP_ALERT_EMAIL=tu-casilla@dominio
```

Todas las demás tienen default (ver `.env.example`). **Ninguna es obligatoria para que
arranque la API**: si falta alguna, falla el backup —que avisa por email y deja el cron
en rojo—, no el despacho de remitos.

### 4.3 — Los servicios cron en Railway

**Dos** servicios nuevos, igual que los dos que ya existen. Mismo repo, cambia el
**Config file path**:

| Servicio | Config file path | Cuándo corre | Qué hace |
|---|---|---|---|
| backup | `railway.cron-backup.json` | `0 3,15 * * *` | el dump y la subida |
| chequeo | `railway.cron-backup-check.json` | `0 5,17 * * *` | avisa si no hay backup fresco |

Cada archivo ya trae su `startCommand` y su `cronSchedule`: no hay que configurarlos a
mano en Railway.

Los dos necesitan las mismas variables (las del punto 4.2 **más** las que ya tienen los
otros crons: sin las 12 obligatorias de producción, Django ni siquiera arranca).

El `pg_dump` lo instala `nixpacks.toml` (paquete `postgresql_17`), que aplica a todos
los servicios del repo. El de chequeo no lo usa —solo lee el bucket— pero lo hereda
igual.

### 4.4 — Confirmar que quedó andando

Después del primer deploy, forzar una corrida desde Railway y después:

```bash
python manage.py backup_database --check-only
```

---

## 5. Lo que este backup NO resuelve

- **Las fotos de evidencia.** Están en R2, el dump solo guarda las URLs. Tienen su
  propia copia, con su propio comando y su propio cron: [sección 7](#7-respaldo-de-las-fotos-de-evidencia).
- **Perder la cuenta de Cloudflare.** Los backups y las fotos viven en la misma cuenta:
  aísla contra perder Supabase, no contra perder Cloudflare. Una copia mensual bajada a
  mano a otro lado cubre ese hueco.
- **El dump no está cifrado.** La protección es que el bucket sea privado y que el
  token esté scopeado. Si en algún momento los backups salen de R2 (bajarlos a una
  máquina, mandarlos a otro proveedor), hay que cifrarlos.
- **Borrar y no darse cuenta en 30 días.** Pasada la retención, el dump con los datos
  buenos ya no está.

---

## 6. Si algo falla

**`pg_dump: server version 17.6; pg_dump version 16.x`**
El `pg_dump` es más viejo que el servidor y se niega a dumpear. En Railway lo fija
`nixpacks.toml`; localmente, apuntá `PG_DUMP_PATH` a un binario 17+.

**El build de Railway falla con `collision between .../postgresql-17.0/bin/pg_config`**
**`and .../postgresql-16.4-dev/bin/pg_config`**
Pasó de verdad la primera vez que se deployó esto. nixpacks agrega `postgresql_16.dev`
por su cuenta al ver `psycopg` en `requirements.txt`; si `nixpacks.toml` SUMA
`postgresql_17` con `nixPkgs = ["...", "postgresql_17"]`, quedan dos paquetes que traen
`bin/pg_config` y Nix no puede armar el perfil.

La solución es reemplazar el 16 por el 17 en vez de sumarlo, o sea la lista explícita
sin `"..."` que hoy tiene `nixpacks.toml`:

```toml
[phases.setup]
nixPkgs = ["python313", "gcc", "postgresql_17"]
```

Sacar `postgresql_16.dev` no rompe nada porque el proyecto usa `psycopg[binary]`, que
instala una wheel con su propia libpq y nunca compila. **El costo es que esa lista pasa
a ser la lista completa:** si cambia `.python-version`, hay que actualizar `python313`
a mano acá.

**El build de Railway falla con `undefined variable 'postgresql_17'`**
El nixpkgs que pinnea nixpacks es viejo. Fijar el archivo en `nixpacks.toml`:

```toml
[phases.setup]
nixpkgsArchive = "<commit de nixpkgs que tenga postgresql_17>"
nixPkgs = ["python313", "gcc", "postgresql_17"]
```

**`unsupported startup parameter` / el dump corta a la mitad**
Se está conectando por el pooler en **modo transacción** (puerto 6543), que no sirve
para `pg_dump`. El comando cambia solo el puerto a 5432; si se forzó otra conexión con
`BACKUP_DATABASE_URL`, revisá el puerto.

**`el servidor no soporta SSL, pero SSL es requerida`**
Destino sin TLS (típico de un Postgres local de prueba). Agregale `?sslmode=disable` al
DSN.

**El email de aviso no llega**
`BACKUP_ALERT_EMAIL` vacía, o `RESEND_API_KEY` sin cargar en ese servicio. El comando
igual sale con código != 0 y la corrida figura fallada en Railway.

---

## 7. Respaldo de las fotos de evidencia

Las fotos **son** el producto: un remito restaurado que apunta a una foto que ya no
existe no prueba nada. El backup de la base guarda las URLs, no los bytes, así que la
evidencia tiene su propia copia en un segundo bucket.

| | |
|---|---|
| Comando | `python manage.py backup_evidence` |
| Dónde corre | Railway, servicio cron propio (`railway.cron-evidence-backup.json`) |
| Cada cuánto | **cada 6 horas** (00, 06, 12 y 18 UTC) |
| Vigilancia | `railway.cron-evidence-check.json`, todos los días a las 08:00 UTC |
| Origen | `r2://friese-evidence` (el bucket donde escribe la app) |
| Destino | `r2://friese-evidence-backup`, **misma key** que el original |
| Si falla | email a `BACKUP_ALERT_EMAIL` y la corrida queda en rojo en Railway |

**La copia nunca borra nada del destino.** Es lo que hace que un borrado por error en
el bucket principal sea recuperable: el respaldo solo crece. Tampoco pisa lo que ya
está — las keys llevan un uuid4 y son inmutables, así que una key que ya existe es la
misma foto.

**La ventana de exposición es de 6 horas**: una foto sacada y borrada por error dentro
de la misma ventana todavía no tiene copia. Para achicarla, bajar el `cronSchedule` de
`railway.cron-evidence-backup.json`; la copia es incremental (compara los dos listados y
solo sube lo que falta), así que correr más seguido casi no cuesta.

### 7.1 — Por qué un job y no versionado o replicación

- **Versionado de objetos: R2 no lo tiene.** Verificado contra el bucket real —
  `list_object_versions` responde **`501 NotImplemented`**. No es un problema de
  permisos: las llamadas de configuración de bucket con ese mismo token responden 403.
  Sin API para listar ni recuperar versiones anteriores, no hay de dónde restaurar.
- **Replicación bucket a bucket: R2 no la ofrece** como sí hace S3. Lo que tiene son
  herramientas para migrar *hacia* R2 (Super Slurper, Sippy), que es el problema
  inverso.
- Y aun si existiera, una replicación que propaga borrados replicaría también el error
  que esto intenta cubrir. El job solo copia, nunca borra.

### 7.2 — Recuperar una foto

Este es el procedimiento que pide el criterio de aceptación de la tarea.
**Probado de punta a punta el 2026-08-12** (ver la entrada de la 7.2 en `PROGRESS.md`).

**Caso 1 — sabés qué foto falta.** La key es lo que va después del dominio en
`Evidence.file_url` (ej. `evidence/39/26/dispatch/562ee27c….jpg`):

```bash
python manage.py backup_evidence --restore evidence/39/26/dispatch/562ee27c….jpg
```

Baja la copia, verifica su `sha256` contra el que se guardó al copiarla, la sube al
bucket principal con la misma key y confirma el tamaño contra el storage. Como la key
no cambia, el `file_url` que ya tiene la fila de `Evidence` **vuelve a funcionar solo**:
no hay que tocar la base.

> Si la key ya existe en el principal, el comando **corta y no pisa nada**. Restaurar
> encima de un archivo que está es, o un error de tipeo, o una foto que no se había
> perdido.

**Caso 2 — no sabés qué falta.** El chequeo lo dice, comparando la base contra el
bucket:

```bash
python manage.py backup_evidence --check-only
```

Lista las fotos que alguna fila de `Evidence` promete y que ya no están en el bucket
principal, y de cada una dice si el respaldo la tiene. Para devolverlas todas:

```bash
python manage.py backup_evidence --restore-missing
```

Si alguna no está tampoco en el respaldo, el comando la nombra y sale con código != 0:
esa foto se perdió de verdad, y hay que decírselo a la empresa dueña del remito.

**Caso 3 — se perdió el bucket entero.** Crear el bucket nuevo, apuntarle
`R2_BUCKET_NAME` (y `R2_PUBLIC_BASE_URL` al dominio público del nuevo), y correr
`--restore-missing`: restaura todo lo que la base referencia. Las fotos huérfanas —las
que ningún `Evidence` referencia— no se restauran, y está bien: no las mira nadie.

### 7.3 — Qué mira el chequeo diario

`backup_evidence --check-only` no solo audita el respaldo; también detecta la pérdida:

| Situación | Qué significa | ¿Avisa? |
|---|---|---|
| Foto en el principal, sin copia, de más de `EVIDENCE_BACKUP_MAX_AGE_HOURS` (26) | el cron de copia se rompió o no está dado de alta | **sí** |
| Foto en el principal, sin copia, reciente | normal: espera la próxima corrida | no |
| Key que un `Evidence` referencia y **ya no está** en el principal | **una foto se perdió.** La app nunca borra evidencia | **sí**, y dice si es recuperable |
| Objeto solo en el respaldo, sin `Evidence` que lo referencie | borrado a propósito junto con su fila (la limpieza de los smoke tests) | no |

Esa tercera fila es la más valiosa: avisa de una foto perdida **el día que se pierde**,
no el día que un cliente la reclama.

### 7.4 — Puesta en marcha

**Bucket y token en Cloudflare**

1. R2 → **Create bucket** → nombre `friese-evidence-backup`.
   **Dejarlo privado**: sin dominio público ni URL `r2.dev`. Es una copia de las mismas
   fotos; no hay motivo para exponerlas en una segunda URL que nadie controla.
2. R2 → **Manage API Tokens** → **Create API Token**:
   - Permiso **Object Read & Write**
   - **Specify bucket** → solo `friese-evidence-backup`

**Variables** (en los dos servicios cron nuevos, y en el web para poder correr los
comandos a mano):

```
R2_EVIDENCE_BACKUP_BUCKET_NAME=friese-evidence-backup
R2_EVIDENCE_BACKUP_ACCESS_KEY=<el del token nuevo>
R2_EVIDENCE_BACKUP_SECRET_KEY=<el del token nuevo>
```

El aviso por email reusa `BACKUP_ALERT_EMAIL`, que ya está cargada. El resto tiene
default (ver `.env.example`). Ninguna es obligatoria para que arranque la API: si falta
alguna falla el respaldo —que avisa—, no el despacho de remitos.

**Los servicios cron en Railway**, mismo repo, cambia el **Config file path**:

| Servicio | Config file path | Cuándo corre | Qué hace |
|---|---|---|---|
| copia de fotos | `railway.cron-evidence-backup.json` | `0 */6 * * *` | copia lo que falte |
| chequeo de fotos | `railway.cron-evidence-check.json` | `0 8 * * *` | avisa si falta algo o si se perdió una foto |

Ninguno de los dos usa `pg_dump`, así que no dependen de `nixpacks.toml` como los de la
base.

**Confirmar que quedó andando**, después del primer deploy:

```bash
python manage.py backup_evidence --check-only
```

Y el arnés completo, que sube una foto sintética, la copia, la borra del principal y la
recupera comparando los bytes:

```bash
python smoke_tests/evidence_backup.py
```

### 7.5 — Lo que este respaldo NO resuelve

- **Las 6 horas de ventana.** Una foto subida y borrada por error entre dos corridas no
  tiene copia. Se achica bajando el `cronSchedule`.
- **Perder la cuenta de Cloudflare.** Las fotos y su copia viven en la misma cuenta. El
  destino es configurable (`R2_EVIDENCE_BACKUP_ENDPOINT_URL`), así que mudar la copia a
  otra cuenta o a otro proveedor S3-compatible es cambiar tres variables, sin tocar
  código.
- **Que el respaldo crezca para siempre.** No tiene poda, a propósito: podar es borrar,
  y borrar es lo que esto evita. A 500 KB por foto, 10.000 remitos con 2 fotos son ~10
  GB — dentro de lo razonable para R2, pero conviene mirarlo alguna vez.
- **Un borrado con la credencial del respaldo.** El token del respaldo puede borrar su
  propio bucket. La protección es que ese token solo vive en los dos crons, no en la
  API pública.
