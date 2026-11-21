# Versiones · leer, atender y enviar

Esto se lee recién cuando llega un aviso `[versiones]`, cuando el usuario dice "revisá", o en
una vuelta del loop de respaldo. El armado, la construcción y la publicación viven en `SKILL.md`.
`<skill>`, `<datos>` y `<nombre>` significan lo mismo que en `SKILL.md` ("Nombres que usa este
archivo"); si no corriste el paso 0 de `SKILL.md` en esta sesión, corrélo antes de seguir.
`<URL>` es el de `<datos>/artifact.txt`.

### 6. Leer lo que eligió

En cada vuelta de la espera, o cuando el usuario diga "revisá":

```
ArtifactData action:"get" url:<URL> collection:"drafts" doc_id:"<draftId>"
ArtifactData action:"list" url:<URL> collection:"drafts/<draftId>/secciones"
```

Para un **hilo**, `drafts/<draftId>` es el índice (`mensajes: [{id, titulo}]`) y cada mensaje
vive un nivel más abajo:

```
ArtifactData action:"list" url:<URL> collection:"drafts/<draftId>/mensajes"
ArtifactData action:"list" url:<URL> collection:"drafts/<draftId>/mensajes/<mid>/secciones"
```

- doc del mensaje → `{ titulo, canal, notaGeneral, listo, notas, envio, rev, ts }`
- doc de sección → `{ pick, textoEditado, editadoDe, ediciones, nota, unida, h, rev, ts }`
  `ediciones` guarda un ajuste por versión (`{ completa: "...", corta: "..." }`). La página
  siempre escribe `textoEditado`/`editadoDe` como el ajuste de la versión elegida, así que el
  texto final se arma solo con ese par. Docs anteriores al 2026-10-22 no traen `ediciones`.
  El usuario edita en la tarjeta de la sección o directo en "Lo que sale": las dos van al mismo par.
  `unida: true` = el usuario pegó esta sección a la anterior en el mismo párrafo (borró el espacio
  entre las dos en "Lo que sale"). Docs anteriores al 2026-10-23 no traen `unida`: vale false.

Una sección sin documento quedó en su `recomendada`, sin editar y sin nota.

**Armar el texto final**, en el orden del `draft.json`:

```
si pick == "quitar"            → saltar la sección
si textoEditado y editadoDe == pick → usar textoEditado
si no                          → usar opts[pick].text
sustituir cada {MARCADOR} por su "valor"
unir las secciones con "\n\n"
  excepto: si la sección tiene unida == true y hay una anterior que sale → pegarla con " "
  (la página no deja pegar una lista: si la última línea de la anterior o la primera de esta
  es un ítem de lista, va con "\n\n" aunque unida sea true)
```

`editadoDe` importa: si el usuario editó la variante `ajustada` y después se pasó a `minima`, la
edición no aplica. Usar `textoEditado` sin ese chequeo mete texto que él ya descartó. Nunca
armes el texto desde `ediciones`: ahí también quedan ajustes de versiones que no eligió.

**Esta lectura vence al terminar el turno.** El usuario sigue tocando la página mientras vos
trabajás. Los picks que acabás de leer sirven para contarle qué ve, para revisar sus ediciones
y para rehacer secciones. **No sirven para mandar.** El texto que sale lo ensambla la página
sola cuando él aprieta Enviar, y viene en `envio.textoFinal`: paso 9.

El texto vuelve **en markdown**. Para WhatsApp y compañía, pasalo a texto plano (o a la
sintaxis de ese canal). Para email, las marcas van a la rama `text/html` del `.eml`:
`**x**` → `<strong>`, `- x` → `<ul><li>`.

### 7. Las dos entradas del usuario NO son la misma cosa

| | Editar el texto | Dejar una nota |
|---|---|---|
| Qué es | cambió palabras a mano | te pide que rehagas la sección |
| Te da trabajo | No | Sí |
| Dónde vive | `textoEditado` | `nota` y `notaGeneral` |

`unida` no es ninguna de las dos: es la costura entre dos secciones. No te da trabajo, salvo el
chequeo del paso 8.

**Notas sin atender** = secciones con `nota` no vacía, más `notaGeneral` si tiene algo.

**La barra de abajo solo ofrece lo que vos podés ejecutar.** Fijos y siempre en el mismo lugar:
**"Volver a lo recomendado"** (a la izquierda; desaparece cuando el mensaje ya tiene `envio`, y
pide confirmación si hay texto editado a mano) y **"Copiar"**. En el medio hay **un solo botón
grande por vez**, elegido en este orden:

| # | Cuándo | Botón grande | Qué escribe |
|---|---|---|---|
| 1 | hay notas sin atender en el hilo | **Pedir cambios** | `listo:true` en todos los mensajes con nota, más el activo |
| 2 | es hilo y quedan mensajes | **Siguiente mensaje →** | nada |
| 3 | canal email, sin notas | **Aprobar** (abre la hoja de cuándo mandarlo) | escribe el `envio`. Paso 9 |
| 4 | cualquier otro canal, sin notas | **Copiar** | el `envio` del paso 9, siempre `modo:"ahora"` |

**"Pedir cambios" va por hilo. "Aprobar" va por mensaje.** Una nota es una sola conversación
con vos: un click la cierra en todos los mensajes que tengan nota, esté parado donde esté.
Apretarla seis veces sería absurdo. Un correo, en cambio, sale por su cuenta, con su hora y su
`threadId`, así que el botón de envío aparece en cada mensaje del hilo: secundario mientras
quede uno siguiente, grande en el último.

**En un canal que vos no mandás no hay ningún botón de envío ni hoja de horarios.** Ahí el
copiado ES la aprobación. Ver el paso 9.

**Escribir una nota baja `listo` a `false` otra vez**, aunque el mensaje ya tenga `envio` (un
`envio` solo se aprueba sin notas, así que toda nota que conviva con uno es posterior). Un
mensaje con nota y `listo:false` significa que el usuario todavía está escribiendo: esperá.

Si hay notas:

1. Guardá las notas antes de tocar nada. La lectura del paso 6 tiene que haber ido a archivos
   (`out_dir:"<scratchpad>/db"`); si no, repetila así. Después:
   ```bash
   python3 <skill>/registro.py nota <draftId> --db <scratchpad>/db
   ```
   Guarda cada nota junto al texto que la motivó. Si te lo salteás, la nota y ese texto se
   pierden: vos los vas a pisar en los pasos 2 y 3.
2. Rehacé **solo** esas secciones en el `draft.json` de `<datos>/drafts/<draftId>/`.
3. Borrá las notas que atendiste, en un solo batch:
   ```
   ArtifactData action:"batch" url:<URL> writes:[
     {"op":"update","collection":"drafts/<draftId>/secciones","doc_id":"apertura","data":{"nota":""}},
     {"op":"update","collection":"drafts","doc_id":"<draftId>","data":{"notaGeneral":""}}
   ]
   ```
   Si decidiste **no** hacer un cambio que él pidió, no borres esa nota: decíselo en el chat.
4. Reconstruí, republicá (paso 4 de `SKILL.md`) y volvé a esperar.

Cuando cambiás el texto de una sección, su huella `h` cambia y la página descarta sola la
edición vieja del usuario sobre ese texto. Las secciones que no tocaste conservan sus ediciones.

### 8. Chequear lo que el usuario editó a mano

Esto pasa en las vueltas de espera, con la lectura del paso 6, **antes** de que él apriete
Enviar. Después del Enviar ya no hay nada que revisar: sale el texto que él aprobó, tal cual.

Revisá **solo** los `textoEditado` y las costuras de las secciones con `unida: true` (que la
frase pegada lea bien: puntuación, mayúscula, que no se repita un saludo). Las variantes que
escribiste vos no se revisan. Buscá tipeos, tildes, concordancia, puntuación, palabras repetidas o
cortadas a la mitad.

| Qué encontraste | Qué hacés |
|---|---|
| Error menor: una palabra, una tilde, un plural, un espacio doble | Corregilo y seguí. No preguntes. |
| Cambio que toca una frase entera o mueve el sentido | Pará. No mandes. |

Menor significa que él no cambiaría de opinión si se lo mostraras. Si tenés que reordenar una
frase, partirla en dos o cambiar el verbo, ya no es menor.

**Cuando no es menor:**

1. Poné el texto corregido en la variante que él tiene elegida (`opts[pick].text` del
   `draft.json` de `<datos>/drafts/<draftId>/`), no en otra.
2. Reconstruí y republicá (paso 4 de `SKILL.md`). La huella `h` cambia, la página descarta sola su edición
   vieja y en la tarjeta ve el texto corregido.
3. Decíselo en el chat, una línea por cambio, con la forma `«lo que escribió» → «cómo queda»`.
   La comparación vive en el chat; la página solo muestra el resultado.
4. Volvé a esperar. Él aprueba desde la página, como siempre.

Las correcciones menores también se reportan, pero **al final y en una sola línea**: "corregí
dos tildes en la apertura". Nunca antes del entregable.

### 9. Enviar: el campo `envio`

Cuando el usuario aprueba el mensaje, el doc gana el campo `envio`. En email lo escribe el botón
**Aprobar**, que abre la hoja "¿Cuándo lo mando?": Recomendado (la hora de `envioSugerido`,
si hay), Enviar ahora (`modo:"ahora"`), Que Claude decida (`modo:"claude"`) o un día y hora que
él elige (`modo:"programado"`). En cualquier otro canal lo escribe el botón **Copiar**, siempre
con `modo:"ahora"`, porque ahí no hay nada que agendar.

```json
"envio": { "modo": "ahora" | "programado" | "claude", "cuando": "2026-09-11T08:00:00",
           "origen": "sugerido",    // opcional: aprobó la hora de envioSugerido sin tocarla
           "etiqueta": "mañana a las 08:00", "estado": "pedido", "canal": "email",
           "textoFinal": "el mensaje entero, ya ensamblado", "ts": "...",
           "actualizadoTs": "...",  // opcional: el usuario apretó "Actualizar el envío"
           "desfasado": true }      // opcional: hay que reagendar. Ver abajo.
```

**El texto que sale es `envio.textoFinal`, no uno que armes vos.** Al aprobar, la
página ensambla el mensaje con lo que el usuario tiene elegido en ese instante (las mismas letras que
él está leyendo en "Lo que sale") y lo guarda entero dentro de `envio`. Ese campo es la foto de
lo que aprobó.

```
si envio.textoFinal existe → ES el mensaje. Mandá esos bytes.
                             No releas secciones. No lo rearmes. No lo mejores.
si no existe               → recién ahí armalo vos, con el plan B de abajo.
```

Lo único que le hacés a esos bytes es cambiar de formato: markdown a la rama `text/html` del
`.eml`, o a texto plano para WhatsApp. Los `{MARCADOR}` ya vienen sustituidos por su `valor`.

**El usuario puede seguir editando después de aprobar.** La página no bloquea nada, a propósito. En
email, un cambio posterior NO entra solo al envío: aparece un botón **"Actualizar el envío"** al
lado del chip y el texto llega recién cuando él lo aprieta. (En los demás canales ese botón no
existe: el chip se pone ámbar y él copia de nuevo, lo que reescribe `textoFinal` solo.) Mientras el botón esté ahí, `textoFinal`
sigue siendo la foto vieja y así tiene que quedar. Vos nunca lo recalculás.

**`"desfasado": true` es una orden para vos.** Aparece cuando él actualizó un envío que ya
estaba `confirmado`, o sea uno que ya tiene su `.eml` copiado en `<datos>/agenda/<ident>/mensaje.eml`.
Ese archivo es lo que va a salir y la página no lo puede tocar. Entonces:

```
desfasado:true  →  1. python3 <skill>/agendar.py cancelar <ident>
                   2. rearmá el .eml con el textoFinal nuevo
                   3. agendar.py crear ... para la misma hora
                   4. borrale el campo: escribí envio sin "desfasado" en el doc del mensaje
```

Si no lo hacés, sale el texto viejo y el usuario cree que salió el nuevo. En la página él ve el chip
en ámbar, "falta reagendar", así que ya sabe que falta algo y te lo va a cobrar.

**Plan B, solo si `textoFinal` no vino** (un borrador publicado antes de setiembre 2026, o la
base de datos caída): releé `secciones` **en este mismo turno**, armá el texto con el paso 6 y
mandá eso.

```
ArtifactData action:"list" url:<URL> collection:"drafts/<draftId>/secciones"
(hilo) ArtifactData action:"list" url:<URL> collection:"drafts/<draftId>/mensajes/<mid>/secciones"
```

**Prohibido armar el mensaje con picks leídos en un turno anterior.** Aunque los hayas leído
hace un minuto. Aunque el usuario no haya dicho que cambió nada. Entre tu última lectura y el botón
Enviar es justo donde él termina de decidir.

Por qué existen las dos reglas: el 2026-09-16 salió un correo con la variante `ajustada` de una
sección porque el usuario la cambió a `minima` 23 segundos después de la única lectura del agente.

**Ese botón es la confirmación.** El usuario eligió destinatario y hora con el mensaje delante. No le
vuelvas a preguntar en el chat si lo mandás: anula el propósito de la herramienta. Preguntá
solo si algo no cierra (falta el destinatario, el texto quedó con una nota sin atender, el
`{MARCADOR}` no tiene valor real, una edición suya necesita una corrección que no es menor
según el paso 8).

Qué hacer según `modo`:

**`ahora`** → mandalo en esta misma vuelta.

- **email** → armá el `.eml` de cero, con los adjuntos ("Armar el .eml", abajo), y mandalo
  con `gws`. Si `config.py --mostrar` mostró una línea `reglas`, leé ese archivo entero antes de
  armarlo: sus reglas suman a las de abajo y, si chocan, mandan las suyas.
  **Antes de armarlo, si hay `threadId`:** `python3 <skill>/destinatarios.py
  --check <draft.json>`. Si sale con código 1 (falta alguien del último mensaje del hilo), no
  mandes: decile al usuario quién falta y esperá su respuesta. Este chequeo vale aunque el usuario
  ya haya apretado Enviar, porque los destinatarios no se ven en la página con el mismo peso que
  el texto.
  **Guardá el `threadId` del enviado.** La respuesta de `gws` lo trae: anotalo en el doc del
  mensaje (`"envio": {..., "threadId": "..."}`) y usalo en el mensaje siguiente del mismo hilo.
  Sin `threadId` el correo 2 no puede hilar del lado del usuario ni tener gate.
- **email con el envío apagado** (paso 0 de `SKILL.md`) → no puede pasar desde la página: ahí el
  correo termina en "Copiar" y se trata como "el resto". Si igual llega un `envio` de email de un
  borrador viejo, no mandes nada: decile al usuario que el envío está apagado y por qué.
- **el resto** → no hay nada que mandar, y tampoco nada que copiar. Ese `envio` lo escribió el
  botón **Copiar**: el usuario ya tiene el texto en el portapapeles y lo está pegando él. No le
  corras `pbcopy` ni le repitas el texto en el chat. Lo tuyo es solo lo que dependa del
  mensaje: seguir el hilo, y cerrar el ciclo con `estado:"enviado"` si corresponde.

**`claude`** → el usuario aprobó el texto y te dejó a vos el cuándo. Decidilo con lo que sabés
del caso: zona horaria y horario laboral del destinatario, si es un seguimiento, si conviene
esperar una respuesta pendiente. La hora que escribís es la local del usuario (`zona` en
`config.py --mostrar`), en uno de sus días de envío. Si su config trae `ventana_despierta`, las
horas dentro de esa ventana no necesitan la Mac despierta; fuera de ella, `agendar.py` avisa.

- Si lo correcto es ya, seguí como `ahora`.
- Si no, seguí como `programado` con la hora que elegiste.
- En los dos casos, al cerrar el ciclo **reescribí `modo`, `cuando` y `etiqueta`** con lo que
  hiciste, así el chip de la página dice la hora real y no "Claude decide cuándo".
- Decile al usuario en el chat, en una línea, qué hiciste y por qué esa hora: "Agendado para el
  martes 27 a las 8:00, porque el lunes es feriado allá." No le pidas confirmación: elegir "Que
  Claude decida" ya lo es.

**`programado`** → no lo mandes vos ni te quedes esperando la hora. La página manda la hora en
`envio.cuando`. El temporizador es de launchd: no gasta tokens ni necesita que la sesión exista.
A la hora manda el `.eml` por `gws`, avisa por notificación y se borra solo.

```bash
python3 <skill>/agendar.py crear \
  --eml <ruta al .eml> --cuando "2026-09-11T08:00:00" \
  --titulo "Correo a Marta" [--thread <threadId>] [--draft <draftId>]
```

**Si tenés el `threadId`, pasalo.** Enciende el gate: a la hora, si ya contestaron, el correo no
sale. Decíselo al usuario en una línea al agendar.

**Quién frena el envío.** `crear` vigila solo a los To y Cc del `.eml` y a todos los que
aparecen en el hilo, también cuando escriben por fuera del hilo. No busques a nadie más. Única
excepción: si el seguimiento es después de una entrevista con más personas y ya sabés quiénes
fueron, sumá un `--gate-de` por cada una (el correo de la persona, nunca un dominio).

**Varios toques en el mismo hilo se agendan todos con `--thread`, sin `--esperar-de`.** Un
toque que salió de la agenda no cancela al siguiente. Uno que el usuario escribe a mano, sí.

**Todos los demás flags viven en `agendar.py crear --help`.** Leelo antes de agendar algo que no
sea ese caso simple. **No los copies de vuelta acá.** Ya pasó una vez: quedaron duplicados, el
CLI siguió creciendo, y este archivo terminó afirmando lo contrario de lo que el comando hace.

Dos salidas del comando piden que vos hagas algo:

- `AVISO a esa hora la Mac puede estar dormida` → pasale al usuario el `sudo pmset schedule wake`
  que imprime, tal cual, en un bloque bash de un solo comando, y decile en una línea qué pasa si
  no lo corre. Pide su contraseña: no lo corras vos. Con `DESPERTAR ok` no hay nada que hacer ni
  que decirle.
- Canal que no es email → solo puede venir de un borrador viejo: la página ya no ofrece
  agendar ahí. No hay nada que mandar solo. Decile que a esa hora se lo dejás copiado, y
  agendá el recordatorio como prefiera.

`agendar.py listar` muestra lo pendiente y lo resuelto, `cancelar <id>` lo baja, `estado <id>`
trae el log.

**Cerrá el ciclo escribiendo el estado de vuelta**, para que la página lo muestre:

```
ArtifactData action:"update" url:<URL>
  collection:"drafts[/<draftId>/mensajes]" doc_id:"<id>"
  data:{"envio":{...,"estado":"confirmado"|"enviado","agendaId":"<id de agendar.py>"}}
```

`confirmado` = quedó agendado. `enviado` = ya salió. La página cambia el cartel sola.

**El cierre en el chat es una línea, falle o no la herramienta de comentarios.** Formato: `Agendado <día> <hora> · <qué lo frena>` o `Enviado · <hora>`. Si la respuesta en el hilo de comentarios falla, esa misma línea va al chat, no una versión más larga. Segunda línea solo si el usuario tiene que decidir algo (un tipeo que cambia el sentido, un destinatario que falta). Fuera: destinatarios sin cambios, cronología, loops apagados, pasos siguientes. (2026-11-18: con `reply_comment` caído, el cierre salió en 8 líneas.)

Si el mensaje es de un hilo y quedan más, decile al usuario cuál sigue: la página ya le muestra el
botón "Siguiente mensaje".

### Armar el .eml

Reglas mínimas para que el correo llegue bien. Si el usuario tiene `reglas_gmail`, esas suman.

- **Siempre una rama `text/html`** además de la de texto plano, con cada párrafo en `<p>`. Si
  el mensaje pasa por la interfaz de Gmail, el texto plano se recodifica con saltos duros a los
  ~70 caracteres y el destinatario ve frases cortadas.
- **Adjuntos con nombre en ASCII puro**, sin tildes, paréntesis ni espacios, uno por archivo.
- Armado con la librería estándar:
  ```python
  from email.message import EmailMessage
  m = EmailMessage()
  m["From"], m["To"], m["Subject"] = "<correo del usuario>", "<para>", "<asunto>"
  m.set_content(texto, charset="utf-8")
  m.add_alternative(html, subtype="html", charset="utf-8")
  m.add_attachment(datos, maintype="application", subtype="pdf", filename="1-nombre-en-ascii.pdf")
  ```
- En un hilo: `In-Reply-To` y `References` con el `Message-ID` del último correo (sale de
  `gws gmail users threads get` con `format:"metadata"`), y el `threadId` en el JSON del cuerpo.
- **Enviar el archivo con la opción de subida de `gws`, no con el mensaje metido en el JSON del
  cuerpo** (arriba de ~10 MB revienta). La subida exige una ruta dentro del directorio de
  trabajo actual: copiá el `.eml` ahí, mandalo y borralo.
  ```bash
  <gws> gmail users messages send --params '{"userId":"me"}' [--json '{"threadId":"..."}'] --upload ./mensaje.eml
  ```
  `<gws>` es la ruta que mostró el paso 0 en la línea `envio`. Los parámetros de ruta y query
  (`userId`) van en el JSON de parámetros; el cuerpo del pedido, en el JSON del cuerpo.
