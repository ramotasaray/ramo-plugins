---
name: versiones
description: >-
  Arma un mensaje transaccional (correo, WhatsApp, Teams, DM, formulario) en tres largos por
  sección y lo publica como página donde el usuario elige, edita, deja notas y decide cuándo
  mandarlo; las respuestas vuelven por la base de datos del artifact. Acepta hilos de varios
  mensajes. SOLO MANUAL: invocar con "/versiones" o pedido explícito ("armá las versiones",
  "dame el mensaje en tres largos"). NO autodisparar cuando el usuario pide redactar un correo.
  Única excepción: las integraciones que el config.json del usuario declare en
  extras.invocacion_automatica (una tarea programada u otra skill que la llama por nombre).
allowed-tools: Bash, Read, Write, Artifact, ArtifactData, ArtifactComments, Skill
---

# Versiones de mensaje

Convierte un mensaje transaccional en una página de una sola vista: cada sección aparece en
tres largos, el usuario elige, edita el texto a mano con markdown en vivo (en cada sección o en
el mensaje armado), pega dos secciones en un mismo párrafo, deja notas de qué rehacer y decide
ahí mismo cuándo se manda. Sus respuestas vuelven al agente por la base de datos del artifact.

## Nombres que usa este archivo

- `<skill>`: la carpeta de esta skill, ruta absoluta. Claude Code la anuncia al cargar la skill
  como "Base directory for this skill". Todos los scripts se llaman con esa ruta. Nunca escribas
  `~/.claude/skills/versiones`: en un plugin la carpeta vive en otro lado y cambia con cada
  actualización.
- `<datos>`: la carpeta de datos del usuario. La imprime `config.py --mostrar` en la línea
  `DATOS`. Por defecto `~/.claude/versiones-datos`; la variable de entorno `VERSIONES_DATOS` la
  cambia. Ahí viven los borradores, la agenda, el registro, el URL del artifact y los ajustes.
  Nada de eso va dentro de `<skill>`: esa carpeta se reemplaza entera al actualizar el plugin.
- `<nombre>`: cómo llamar al usuario. Sale de la línea `nombre` de `config.py --mostrar`.
- `<scratchpad>`: el scratchpad de la sesión.

## 0. Arranque: siempre, antes de cualquier otro paso

```bash
python3 <skill>/config.py --mostrar
```

Imprime la carpeta de datos, los ajustes del usuario y si el envío de correo está listo (prueba
`gws` con una lectura de Gmail que no cambia nada). Leé cada línea y actuá así:

- **`PRIMERA VEZ`** (no hay `config.json`): preguntale al usuario, en un solo mensaje, tres
  cosas: cómo lo llamás, su correo, y si quiere envío programado de correos (necesita `gws`, el
  CLI de Google Workspace, instalado y con su Gmail autenticado; si no lo tiene, la respuesta es
  no). Con las respuestas:
  ```bash
  python3 <skill>/config.py --crear --nombre "<nombre>" --correo <correo> --envio-email si
  ```
  (`--envio-email no` si dijo que no). No preguntes nada más: el resto de los ajustes tiene
  valores por defecto y se edita a mano en `<datos>/config.json` si hace falta (lista abajo).
- **`envio APAGADO`**: en esta sesión el correo termina en el botón "Copiar", igual que los
  otros canales, y no se agenda nada. Si el motivo es que `gws` falta o no está autenticado,
  decíselo al usuario en una línea con ese motivo, una sola vez por sesión.
- **`prefs <ruta>`**: leé ese `preferencias.md` entero antes de escribir el primer texto. Son
  las reglas de redacción propias del usuario. Mandan sobre las reglas de redacción por defecto
  de este archivo. No mandan sobre las reglas de seguridad del envío (pasos 6 a 9 de `ENVIO.md`).
- **`reglas <ruta>`**: un `.md` con reglas propias para armar correos. Leelo entero antes de
  armar el primer `.eml` (paso 9 de `ENVIO.md`), no antes.
- **`extras`**: integraciones personales. Ver "Quién puede invocarla".
- **`AVISO`**: un ajuste mal escrito volvió a su valor por defecto. Contáselo al usuario en una
  línea y seguí.

Ajustes de `<datos>/config.json`, todos opcionales:

| Clave | Qué hace | Por defecto |
|---|---|---|
| `nombre` | cómo llamar al usuario | "el usuario" |
| `correos_propios` | sus direcciones: quedan fuera de "responder a todos" | ninguna |
| `zona_horaria` | zona IANA del usuario, la de `envioSugerido` | la del sistema |
| `gws` | ruta al binario `gws` | PATH, después `/opt/homebrew/bin/gws` |
| `launchd_prefijo` | prefijo del label de launchd de cada envío | `com.versiones` |
| `envio_email` | `false`: el correo termina en Copiar, sin agendar | `true` |
| `dias_envio` | días que ofrece la hoja de horarios ("lunes", ... o 0-6, 0 = domingo) | lunes a viernes |
| `ventana_despierta` | `{"desde": "06:00", "hasta": "09:00"}` si la Mac se despierta sola a diario; fuera de esa ventana la página avisa | sin aviso |
| `reglas_gmail` | ruta a un `.md` con reglas propias para armar correos | ninguna |
| `extras` | integraciones personales (`invocacion_automatica`) | ninguna |

## Quién puede invocarla

Solo el usuario, a mano. **Excepciones: solo las que liste `extras.invocacion_automatica` en su
`config.json`, y ninguna más.** Cada entrada nombra quién la invoca (una tarea programada, otra
skill), qué archivo de instrucciones sigue y en qué momentos. Fuera de esas entradas, cualquier
pedido de redactar un correo se escribe libre, sin esta skill.

Las excepciones son seguras porque la página **no manda nada sola**. Publica el borrador y
espera. El correo sale cuando el usuario aprueba ese texto exacto, y ni un minuto antes.

## Regla que manda sobre todas las demás

**La columna `completa` se escribe corta desde el arranque**, en modo transaccional (abajo): lo
más corto que resuelva, sin relleno. No inflar para después desinflar. Antes de construir,
releé cada sección de `completa` y sacale toda oración que no cambie lo que el lector hace.
`ajustada` y `minima` son recortes de eso.

## Modo transaccional: reglas de redacción por defecto

Aplican a las tres columnas, salvo que `preferencias.md` diga otra cosa.

- El mensaje es lo más corto que resuelva. Cada oración cambia lo que el lector hace o sale.
- El pedido va primero. Con gente conocida, después del saludo ("Hola Marta!").
- Fuera las instrucciones de cómo responder y los pasos siguientes obvios. Las preguntas se
  quedan.
- Razones: una línea como máximo.
- Plazos, montos y conteos en dígitos: "10 días", "$1-3", "3 opciones".
- A un tercero se le propone, no se le ordena: "podemos", "ojalá", "¿le parece?".
- No repetir fechas ni datos que el lector ya conoce.
- **Sin raya (em dash, "—") dentro de una oración** en el texto que sale a nombre del usuario:
  delata texto de IA. Usar coma, dos puntos, paréntesis o punto y seguido.
- **Un párrafo va en una sola línea**, por largo que sea. El usuario copia y pega en campos de
  chat y formularios que respetan los saltos de línea: un salto en medio parte el mensaje.
  Saltos solo entre párrafos o ítems de lista.

## Arquitectura

```
<skill>/                  el código, igual para todos los usuarios. No guardes nada acá
  SKILL.md        esto: arrancar, armar, construir, publicar y esperar (pasos 0 a 5)
  ENVIO.md        pasos 6 a 9: leer la base, notas, ediciones y envío. Leelo recién cuando
                  llegue un aviso "[versiones]" o toque revisar la base, no antes
  template.html   la interfaz. NUNCA la leas ni la edites. No la necesitás para nada.
  config.py       carpeta de datos y ajustes del usuario (paso 0)
  build.py        inyecta el draft.json y parte la página en tres archivos publicables
  contrato.py     valida el draft.json (lo usa build.py)
  destinatarios.py  "responder a todos" de un hilo de Gmail, y --check antes de enviar
  agendar.py      programa el envío de un .eml con launchd (sin agente, sin tokens)
  gate.py         mira un hilo de Gmail y dice si el seguimiento todavía hace falta
  registro.py     guarda en registro.jsonl lo que el usuario eligió, editó y anotó. Se llama en
                  el paso 1a y en el paso 7 de ENVIO.md
  deriva.py       chequea que este archivo no nombre flags ni subcomandos que los CLIs no tienen.
                  Corrélo vos, sin pedirle nada al usuario, después de editar este archivo o un CLI

<datos>/                  del usuario, sobrevive a las actualizaciones
  config.json     sus ajustes (paso 0)
  preferencias.md opcional: sus reglas de redacción
  registro.jsonl  append-only. Nunca lo edites ni lo borres
  artifact.txt    el URL del artifact reutilizable
  gws-estado.json la última prueba de gws (la escribe el paso 0, la lee build.py)
  drafts/         un directorio por borrador: su draft.json, que es la fuente. Permanente.
                  TODOS los que estén acá salen como tabs en la página
  drafts/_cerrados/  los borradores que el usuario cerró con la ✕. No salen como tabs
  agenda/         un directorio por envío agendado (lo maneja agendar.py)
```

**Vos solo escribís un `draft.json`.** No escribas HTML. No abras `template.html`. Cambiar la
prosa de un mensaje cuesta unos cientos de tokens; la interfaz ya está pagada.

## Flujo

### 1. Mirar qué hay antes de escribir nada

**No hay colisión que chequear.** Publicar un borrador nuevo no pisa a los otros: cada uno
vive en su propio `d/<draftId>.json` y aparece como un tab en la fila de arriba. Lo único que
cambia al publicar es cuál abre por omisión.

Si no existe `<datos>/artifact.txt`, todavía no hay página: saltá al paso 2.

Hacé estas tres cosas, en este orden:

**Si la herramienta `ArtifactData` o `ArtifactComments` no existe en la sesión** (pasa en la app de escritorio, visto el 2026-11-11): usar las del servidor `claude-artifacts`, cargándolas con `ToolSearch` (`select:mcp__claude-artifacts__db_get,mcp__claude-artifacts__db_list,mcp__claude-artifacts__db_query,mcp__claude-artifacts__db_write`). Equivalencias: `get` es `db_get`, `list` es `db_list`, `set`/`update`/`batch` van por `db_write`. Los nombres de parámetros pueden diferir: leer el esquema que devuelve `ToolSearch` antes de la primera llamada. `ArtifactComments` es `mcp__claude-artifacts__read_comments`. (untested)

**a) Archivar lo cerrado.** Leé el índice de la base (una sola llamada, a archivos):

```
ArtifactData action:"list" url:<URL> collection:"drafts" out_dir:"<scratchpad>/db"
```

Cada doc con `cerrado:true` está terminado: el usuario le dio al ✕ en su tab. Si su directorio
sigue en `<datos>/drafts/`, primero guardá su foto y después movelo a `<datos>/drafts/_cerrados/`
(`mv`, nunca borrar).

La foto: bajá sus secciones al mismo `<scratchpad>/db` (en un hilo, primero
`drafts/<draftId>/mensajes` y después `drafts/<draftId>/mensajes/<mid>/secciones` por cada
mensaje) y corré:

```bash
python3 <skill>/registro.py cierre <draftId> --db <scratchpad>/db
```

Si ya estaba registrado, el script lo dice y no duplica. Sin la foto, lo que el usuario eligió y
editó se pierde para la revisión de escritura. Así no se republica ni ocupa la fila de tabs.
**No lo reabras** salvo que el usuario lo pida por nombre: ahí lo devolvés a `<datos>/drafts/`.

**b) Sincronizar lo agendado.** Solo si el envío está activo (paso 0):

```bash
python3 <skill>/agendar.py listar
```

El temporizador corre sin sesión de Claude y no puede escribir en la base, así que la página
no se entera sola de lo que pasó. Vos sos el único que se lo puede contar:

- Si un envío dice `enviado` en `listar` y el doc de la base (el `draftId` está en
  `<datos>/agenda/<id>/envio.json`) sigue en `confirmado`, escribí `envio.estado:"enviado"` con
  `ArtifactData action:"update"`, reescribiendo el `envio` entero con ese único campo cambiado.
- Si alguno dice `cancelado-por-respuesta` o `error-gate`, **contáselo al usuario en una línea
  antes de seguir**.

**c) Envíos desfasados.** Si un mensaje de la base trae `envio.desfasado`, el usuario editó algo
después de que lo agendaras y el `.eml` en disco quedó viejo. Reagendalo antes de seguir con
lo nuevo: paso 9, en `ENVIO.md`.

### 2. Escribir el draft.json en su directorio permanente

El `draft.json` vive en la carpeta de datos, **no en el scratchpad**:

```bash
mkdir -p <datos>/drafts/<draftId>
```

El scratchpad muere con la sesión, y el texto de las variantes es lo único caro de esta
herramienta. Con el `draft.json` guardado, devolver un borrador a pantalla cuesta un `build.py`
y un publish. Sin él, hay que reescribir el mensaje entero. Los picks del usuario nunca corren
riesgo: viven en la base, indexados por `draftId`, y sobreviven a cualquier republicación.

Inventá las secciones por mensaje: cantidad y nombres dependen del contenido. No hay
plantillas por canal.

**Un mensaje suelto:**

```json
{
  "draftId": "2026-09-04-marta-seguimiento",
  "titulo": "Seguimiento a Marta",
  "tab": "Marta",
  "canal": "email",
  "cwd": "<carpeta donde están los adjuntos>",
  "destino": { "para": "marta@empresa.com", "asunto": "Re: ..." },
  "marcadores": { "LINK": { "valor": "https://...", "vista": "[link al estudio]" } },
  "adjuntos": [ { "nombre": "estudio.pdf", "peso": "1,2 MB", "nota": "va como link" } ],
  "secciones": [
    {
      "id": "apertura",
      "nombre": "Apertura",
      "job": "Abre sin pedir nada todavía.",
      "opcional": false,
      "recomendada": "ajustada",
      "opts": {
        "completa": { "text": "...", "note": "qué gana y qué cuesta esta variante" },
        "ajustada": { "text": "...", "note": "..." },
        "minima":   { "text": "...", "note": "..." }
      }
    }
  ]
}
```

**Un hilo de varios mensajes:** lo mismo, pero `secciones` se reemplaza por `mensajes`. Cada
mensaje tiene sus propias secciones, y puede pisar `canal`, `destino` y `adjuntos` del nivel
de arriba:

```json
{
  "draftId": "2026-09-10-empresa-permiso",
  "titulo": "Permiso para usar la cita",
  "tab": "Empresa cita",
  "canal": "email",
  "mensajes": [
    { "id": "m1", "titulo": "Correo 1 · el pedido", "tab": "El pedido",
      "destino": { "para": "...", "asunto": "..." },
      "secciones": [ ... ] },
    { "id": "m2", "titulo": "Correo 2 · el recordatorio", "tab": "Recordá", "secciones": [ ... ] }
  ]
}
```

Reglas del contrato:

- `draftId`, `mensajes[].id` y `secciones[].id` son segmentos de ruta de base de datos: letras,
  dígitos y `_ - . ~ : @ +`. Sin espacios ni acentos.
- **`tab` y `titulo` son dos campos distintos y los dos son obligatorios.** El `titulo` es largo
  a propósito: alimenta el encabezado de la página (el nombre del artifact es fijo, "Versiones"). El `tab` es la
  etiqueta que se lee en una fila junto a las otras, así que es corto y `build.py` falla si se
  pasa: **14 caracteres** el del borrador, **12** el de cada mensaje de un hilo (un mensaje
  suelto hereda el del borrador y no lleva el suyo). No lo armes cortando el `titulo` con
  puntos suspensivos: elegí una o dos palabras que lo distingan de los otros tabs abiertos.
  Un tab que dice "In 200 words or fewer, describe…" no identifica nada.
- `canal`: `email`, `whatsapp`, `teams`, `dm` o `formulario`.
- `job` explica **por qué existe** la sección, no qué dice. Se lee al lado del nombre, en una
  línea: **máximo 10 palabras, sin verbo auxiliar.** "Abre sin pedir nada todavía." sirve;
  "Esta sección sirve para poder abrir la conversación" no sirve. `build.py` avisa si te pasás.
- `note` por variante es **el tradeoff**, no un resumen del texto. "Pierde el remate, sigue
  diciendo lo esencial" sirve; "versión más corta" no sirve.
- `opcional: true` agrega una cuarta tarjeta "Quitar".
- `recomendada` es el estado inicial de la página. Marcá una por sección. Por defecto recomendá
  `ajustada` en todos los canales. `completa` nunca es la recomendada por defecto: solo cuando
  `ajustada` pierde un dato que el lector necesita para actuar.
- **Si recomendás un horario de envío, escribilo en `envioSugerido`, no en el texto ni en el
  chat:** `"envioSugerido": {"cuando": "2026-10-26T08:00", "motivo": "lunes temprano, antes de su standup"}`.
  `cuando` es hora local del usuario (su `zona_horaria`), sin zona, o `"ahora"` si lo mejor es
  mandarlo ya. Elegí un día de su `dias_envio`. `motivo` es una línea (máximo 80 caracteres). Va en
  el nivel de arriba o, en un hilo, por mensaje (pisa al de arriba). El botón principal dice
  siempre "Aprobar" y abre la hoja "¿Cuándo lo mando?". La hoja muestra primero, resaltada, la
  fila "Recomendado · lunes 26 oct a las 08:00" con el `motivo`; un click la agenda a esa hora.
  Con `"ahora"` la fila es "Recomendado · Enviar ahora" y reemplaza a "Enviar ahora". Si la
  hora ya pasó, `build.py` avisa y la fila no aparece. Sin horario recomendado, no pongas el
  campo. Las otras filas de la hoja: "Enviar ahora" (`modo:"ahora"`), "Que Claude decida"
  (`modo:"claude"`: la hora la elegís vos con el contexto del caso, paso 9 de `ENVIO.md`),
  el atajo del próximo día de envío temprano y "Otro día y hora" (`modo:"programado"`). Con el
  envío apagado (paso 0) no hay hoja: el correo termina en "Copiar" y `envioSugerido` no se usa.
- **`destino` dentro de un hilo (`threadId`) no se escribe a mano.** Sacalo de
  `python3 <skill>/destinatarios.py <threadId>`, que devuelve el "responder a todos" del último
  mensaje. Sacar a alguien de la copia lo decide el usuario en el chat, nunca vos. El
  2026-10-08 un correo salió sin la clienta en copia por armarlo a mano.
- Los marcadores (`{LINK}`) sustituyen URLs largas: las tarjetas muestran `vista`, el texto
  final lleva `valor`. `marcadores`, `adjuntos` y `destino` son opcionales.
- **Markdown**: `**negrita**`, `*cursiva*`, `` `código` ``, `~~tachado~~`, `- viñeta` y
  `1. numerada` se escriben en el `text` y la página los muestra aplicados. Usalos solo si el
  mensaje los gana de verdad. Un correo transaccional rara vez necesita negrita.
- `build.py` valida todo esto y falla con el campo exacto. No adivines: corré y leé el error.

### 3. Construir

```bash
python3 <skill>/build.py \
  <datos>/drafts/<draftId>/draft.json \
  --out <scratchpad>/versiones/versiones.html
```

**La fuente es permanente, lo construido es efímero.** El `--out` va al scratchpad y es
obligatorio: la tool Artifact solo publica archivos que estén bajo el working directory o el
scratchpad de la sesión, así que adentro de `<datos>/drafts/` no se puede construir. `build.py`
lo impide y te imprime la línea correcta.

Escribe esto en el directorio del `--out`, y lo crea si no existe:

| Archivo | Qué es |
|---|---|
| `versiones.html` | la cáscara. ~3 KB y no crece con el texto |
| `boot.js` | pide el borrador por `fetch` y pinta la fila de tabs |
| `app.css`, `app.js` | la interfaz |
| `d/<draftId>.json` | **uno por cada borrador de `<datos>/drafts/`**, no solo el que construiste. Lleva adentro los ajustes del usuario que la página usa (días de envío, si se ofrece agendar el correo) |
| `d/index.json` | el índice de la fila de tabs |

Salen todos los borradores y no solo el tuyo porque cada tab apunta a un `d/<id>.json` y ninguno
puede faltar. Uno que no valide queda fuera de la fila y te lo avisa, en vez de romper el build.

**Para probarlo local hay que servirlo por HTTP** (`python3 -m http.server <puerto> --directory
<dir>`). Abrir el HTML con `file://` no funciona: el navegador bloquea el `fetch` del borrador.

Imprime la ruta del HTML y su peso, palabras por versión y por sección, las rutas que va a usar
en la base, avisos (por ejemplo, si `minima` salió más larga que `ajustada`, o si un `job` es
largo) y la línea `root:` / `files:` lista para copiar al publicar. Con eso sabés cómo quedó sin
abrir el HTML.

**Devolver un borrador a pantalla** (quedó de otra sesión, u otro proyecto lo pisó): el mismo
comando, sin nada extra.

El `rev` de la publicación sale del texto de las secciones, no del reloj. Reconstruir un
borrador que no tocaste da el mismo `rev`, y la página conserva `notaGeneral`, `listo` y `envio`.
Si reescribiste una sección (pasos 7 u 8 de `ENVIO.md`), el `rev` cambia solo: ahí la página descarta lo viejo y
muestra tu corrección, que es exactamente lo que querés. **No hay ningún flag que acordarse.**


### 4. Publicar

**Primera vez** (no existe `<datos>/artifact.txt`):

```
Artifact file_path:"<dir>/versiones.html" capabilities:{"db":{},"comments":{}} icon:"scissors"
        root:"<dir>" files:{...la línea que imprimió build.py...}
        description:"..."
```

Guardá el URL devuelto en `<datos>/artifact.txt`.

**Después** (existe `<datos>/artifact.txt`), el artifact se sobrescribe:

```
Artifact action:"list" scope:"files" url:<URL>   ← obligatorio, una vez por sesión
Artifact file_path:"<dir>/versiones.html" url:<URL>
        root:"<dir>" files:{...la línea que imprimió build.py...}
```

`build.py` te imprime la línea `root:` / `files:` exacta: copiala. El listado de archivos es lo que
habilita la publicación: desde setiembre 2026 el harness rechaza pisar un archivo publicado que
esta sesión no leyó ni listó. Listarlos cuesta unas pocas líneas; leerlos, miles de tokens.
Si el rechazo igual llega, listá de nuevo y reintentá una sola vez; si vuelve a fallar, avisale al usuario con el error. Nunca uses `overwrite_unread`. Omití `capabilities` e
`icon` en las republicaciones: se arrastran solos.

**Por qué la página va partida en archivos.** El `read` del artifact devuelve la página inline
solo si pesa menos de 25 KB. Arriba de ese techo la guarda en un archivo local, obliga a leerla
entera y encima hay que repetir el `read`: eran unos 40.000 tokens por republicación, todos en
ceremonia (medido el 2026-09-15, con la página en 76 KB). Con el CSS, el JS, el bootstrap y el
texto de cada borrador afuera, la cáscara queda en ~3 KB fijos y el `read` cuesta unos cientos
de tokens en vez de miles.

- **La cáscara no lleva el borrador adentro.** Lo único que la distingue entre publicaciones es
  el atributo `data-defecto`, que dice cuál abre por omisión. Eso alcanza para que el harness no
  rechace la publicación por contenido repetido.
- Si `build.py` avisa que la cáscara pasa de 22 KB, algo se coló adentro del HTML. No es el
  draft: revisá `template.html`.
- `files` se puede omitir al republicar (lo que no mandás se conserva), pero mandalos siempre:
  si algún día cambia `template.html`, sin eso el estilo viejo se queda pegado.
- **No uses `force`**: eso necesita que el usuario lo pida explícitamente.

**El link abierto de cero abre el borrador por omisión**, o sea el último que construiste.
Pegarle `?d=<draftId>` al URL de claude.ai **no sirve**: la página vive adentro de un iframe de
otro dominio y el query de afuera no le llega (medido el 2026-09-17). Adentro sí funciona: los
tabs son links relativos y navegan el iframe con su `?d=`.

**Si el usuario ya tiene la página abierta, publicar NO lo cambia de tab** (desde el
2026-10-13). Cada publicación recarga la página que tiene abierta; la página recuerda en qué
borrador y a qué altura estaba, y vuelve ahí. El borrador nuevo aparece en la fila de tabs con
un punto de "nuevo" hasta que lo abra.

Consecuencia para vos: **construí último el borrador del que le vas a hablar**, y en la línea
del paso 5 decile el nombre del tab ("está en el tab *Marta*, el del punto"). Si ya tenía la
página abierta, va a seguir en el borrador donde estaba y tiene que tocar ese tab.

### 5. Pasarle el link al usuario y quedarte esperando

Una línea: qué mirar y qué hacer. Que abra el panel lateral y deje libre la casilla del chat.

**La página te avisa sola.** Cuando el usuario aprieta "Pedir cambios", elige una fila en la hoja
de "Aprobar" o aprieta "Actualizar el envío" de uno ya agendado, la página manda un comentario a esta sesión con `sendToClaude`
(capability `comments`). Te llega como un turno nuevo, marcado como comentario de artifact
enviado a Claude, con un texto de una línea así:

```
[versiones] cambios · draft=<draftId> · msg=<mid> · <tab>
[versiones] envio ahora|programado|claude · draft=<draftId> · ...
[versiones] reagendar · draft=<draftId> · ...
```

**El aviso le llega a TODAS las sesiones que publicaron la página**, no solo a la tuya (lo dice
el contrato de `comments`: notifica a las sesiones que miran el artifact). Varias sesiones con
borradores distintos reciben el mismo timbre. Por eso, antes de hacer nada:

1. Leé el `draft=<draftId>` del aviso.
2. **Si ese `draftId` es tuyo, atendelo.** Es tuyo si en esta sesión corriste `build.py` con
   `<datos>/drafts/<draftId>/draft.json` como borrador principal, o si el usuario te pidió en
   esta sesión que te encargues de ese borrador por nombre o por tab.
3. **Si no es tuyo, ignoralo entero.** No leas la base, no respondas el hilo, no lo resuelvas y
   no escribas nada en el chat. Terminá el turno sin texto. Otra sesión es la dueña y lo atiende.
4. **Excepción, una sola:** si el usuario te escribe en el chat que revises un borrador que no es
   tuyo ("revisá Marta", "la otra sesión se cerró"), pasa a ser tuyo y lo atendés desde ahí.

Sin esta regla, el pedido de cambios de un borrador lo agarraba la sesión que estuviera libre,
aunque tuviera abierto otro borrador y no supiera nada del que le tocaba.

**Cuando tu borrador terminó** (enviado, o el usuario lo cerró con la ✕), dejá de mirar la
página: `ArtifactComments action:"watch" url:<URL> on:false`. La plataforma publica una respuesta
automática en el hilo a nombre de cada sesión que mira la página, antes de que esa sesión lea
esta regla (visto el 2026-10-14: una sesión ajena contestó "voy a enviar" un borrador que no
era suyo). Esa respuesta no se puede frenar desde acá; lo único que la evita es no estar mirando.

**Borradores de prueba:** un `draftId` que empieza con `prueba-` no toca el timbre. La página
dice "aviso omitido (prueba)" y ninguna sesión recibe nada. Usá ese prefijo para cualquier
borrador que armes para probar la página, para que ninguna sesión mande un envío de prueba.

El texto es solo el timbre. **No es la decisión:** la decisión está en la base. Al recibirlo,
leé `<skill>/ENVIO.md` si no lo tenés en contexto y seguí desde el paso 6 con ese `draftId`.
Cuando terminaste, respondé en el hilo del aviso con una línea de qué hiciste
(`ArtifactComments action:"reply"`) y cerralo (`action:"resolve"`). En el chat, una sola línea.

**Cuándo hace falta la espera de respaldo.** El aviso solo despierta a esta sesión si el
resultado del publish dice que las respuestas automáticas a comentarios quedaron armadas
("auto-replies armed"). Si lo dice, **no armes loop**. Si no lo dice, o dice que solo está
"arming", armá la espera de respaldo, con la ruta absoluta de `ENVIO.md` escrita en el prompt:

```
Skill loop  args: "30m Revisá la base de /versiones: leé <skill>/ENVIO.md solo si no lo tenés en contexto, y seguí su paso 6 para <draftId>"
```

El prompt del loop NO es `/versiones revisar`: ese relanzaba la skill entera en cada vuelta.
Si no hay nada nuevo, la vuelta termina sin decir nada. Cortá el loop cuando el borrador se cierre o a las 8 vueltas (4 horas), lo que pase primero, y avisale al usuario que dejaste de revisar.

Decile al usuario en una línea: que la página te avisa sola, y que si el cartel de arriba a la
derecha no dice **"Claude avisado"** después de apretar un botón, te escriba **"revisá"**.

**Verificado el 2026-09-28** con un click real en "Pedir cambios": el aviso llegó a la sesión
en segundos. La primera vez, el navegador le pide permiso para comentar.

## Qué NO hace

- **La página nunca envía por sí misma.** Corre en claude.ai, no tiene `gws`. Lo que hace es
  dejar escrito cuándo querés que salga. El que manda es este lado.
- **Gmail no tiene envío programado por API.** El botón de la interfaz no existe como campo en
  `messages.send`. Por eso el agendado va por launchd, y solo en Mac.
- **Los adjuntos no entran a la herramienta.** Solo se listan.
- No decide si el mensaje debe existir ni a quién va.
- No decide la voz: decide el largo. Es para modo transaccional. Si el usuario tiene una skill
  de voz propia y el texto es de autor o persuasivo, primero esa skill.
- No borra nada ni guarda historial de enviados.
- Si `db` no está disponible en la cuenta, la página igual funciona: guarda en el navegador y
  el usuario pega el resultado en el chat con el botón Copiar. Avisale que las notas no van a
  volver.
