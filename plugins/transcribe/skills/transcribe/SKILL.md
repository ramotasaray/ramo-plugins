---
name: transcribe
allowed-tools:
  - Bash(yt-dlp *)
  - Bash(python3 ${CLAUDE_SKILL_DIR}/*)
  - Bash(python3 */transcribe/*)
  - Bash(mlx_whisper *)
  - Bash(ffprobe *)
  - Bash(ffmpeg *)
  - Bash(command -v *)
  - Bash(~/.local/share/summarize-call/pyannote-env/bin/python *)
  - Read
description: >-
  Transcribe audio o video a texto, con separación de hablantes. Default: ElevenLabs Scribe v2 (rápido y preciso). Alternativa local con mlx_whisper para audio que no puede salir de la máquina o cuando el usuario pide "transcribilo local". Acepta archivos y URLs (YouTube y demás, usando los subtítulos del sitio cuando alcanzan). Ruta por defecto para CUALQUIER pedido de transcripción, en español o inglés: "/transcribe", "transcribime esto", "pasá esto a texto", "quién dice qué", "transcribe this audio", un archivo de audio o video pegado, o una URL de video de la que se quiere el texto.
---

# Transcribe

Dos motores. **Scribe es el default.** El local queda como alternativa, no como respaldo automático.

## Elegir motor

| Situación | Motor |
|---|---|
| Cualquier pedido normal | **Scribe** (Camino A) |
| el usuario dice "local", "offline", "sin subirlo" | Local (Camino B) |
| El audio no puede salir de la máquina (médico, legal, cliente bajo NDA) | Local (Camino B) |
| No hay internet | Local (Camino B) |
| Scribe devuelve error de key o de cuota | Local (Camino B), avisando por qué se cambió |

**Nunca caer al local en silencio.** Si Scribe falla, decir qué falló antes de correr el local: el resultado va a ser peor y el usuario tiene que saberlo.

Medido sobre el mismo audio real (consulta médica, 13 min, español de Costa Rica, 2026-09-21):

| | Local (whisper + pyannote) | Scribe v2 |
|---|---|---|
| Tiempo total con hablantes | 2 min 14 s | **34 s** |
| Costo | $0 | ~$0,09 |
| Calidad del texto | se degrada con ruido: inventa palabras y entra en bucles | limpia, puntuada |
| Corte de turnos | mete dos voces en el mismo turno | correcto |

En ese audio el local escribió "botitas" por "gotitas", "la hemoglobina que se le llama en el anemia está en el 2.4" por "la hemoglobina, que es el examen de la anemia, sale doce punto cuatro", y desde el minuto 11 repitió "¿Pero qué?" en bucle. Por eso Scribe es el default: no es solo velocidad.

## Cuándo NO usar este skill

- **Cuando importa lo que se VE** (una demo de producto, un tutorial con pantalla, alguien señalando un gráfico, "¿qué muestra en el minuto 12?") → `watch`. Ese skill extrae cuadros de imagen y los mira. Este solo produce texto.
- **Cuando piden una respuesta o un resumen de un video** ("¿qué dice de X?", "resumime este video", "de qué trata") → `watch`. Gemini mira el video y devuelve solo la respuesta, sin meter la transcripción entera a la conversación. Este skill es para cuando se quiere el texto literal, o separar hablantes.

Este skill es para: quiero el texto de esto. El "esto" puede ser un archivo local o una URL.

## Paso 1 (compartido) — si lo que te dieron es una URL

Aplica cuando el input empieza con `http`. Si es un archivo local, saltar directo al camino que elegiste.

Requiere `yt-dlp` (ya está en `/opt/homebrew/bin/yt-dlp`).

### Primero: preguntar qué subtítulos tiene, sin bajar nada

```bash
yt-dlp --list-subs "URL"
```

Sale una lista de idiomas disponibles. Los automáticos aparecen bajo un encabezado aparte que dice `automatic captions`; los escritos por una persona, bajo `Available subtitles`.

### Ruteo

| Qué hay | Qué hacer |
|---|---|
| Subtítulos de cualquier tipo, manuales o automáticos | Bajar el archivo de subtítulos y usarlo como transcripción. Segundos, cero cómputo. **No bajar el audio.** |
| Sin subtítulos en ningún idioma | Bajar solo el audio y seguir con el camino que elegiste. |
| el usuario pidió separar hablantes | Bajar el audio **siempre**, aunque haya subtítulos. Ningún subtítulo de YouTube trae hablantes, ni los automáticos ni los manuales. |

### Bajar subtítulos

```bash
yt-dlp --skip-download --write-subs --write-auto-subs \
  --sub-langs "es.*,en.*" --sub-format "vtt" \
  -o "~/Downloads/%(title)s.%(ext)s" "URL"
```

- `--skip-download` — no baja el video ni el audio, solo el archivo de texto.
- `--sub-langs "es.*,en.*"` — español e inglés y sus variantes (`es-419`, `en-US`). Ajustar si el video está en otro idioma.
- Sale un `.vtt`: texto con marcas de tiempo. Leerlo directo.

Los automáticos de YouTube vienen sin puntuación y sin mayúsculas, en una tira corrida. Eso es normal, no es un error de la descarga. Si el usuario necesita el texto limpio para leer, avisarle que se puede arreglar en un segundo paso, o rehacerlo con Whisper bajando el audio.

### Bajar solo el audio

```bash
yt-dlp -x --audio-format m4a -o "~/Downloads/%(title)s.%(ext)s" "URL"
```

`-x` extrae la pista de audio y descarta el video. Una hora de video pesa unos 30 MB así, contra unos 700 MB bajándolo entero.

**El archivo se queda en `~/Downloads/` con el título del video como nombre.** No borrarlo al terminar: si después el usuario pide separar hablantes, ya está bajado y no hay que repetir la descarga.

### Cuando la descarga falla

`yt-dlp` escribe el motivo en stderr. Los casos frecuentes, y qué decirle al usuario:

- **Pide login o es privado** → no hay vuelta sin las credenciales. Decirlo y parar, no reintentar.
- **Bloqueado por región** → igual, parar.
- **`Unable to extract` o similar** → suele ser que YouTube cambió algo y `yt-dlp` quedó viejo. Correr `brew upgrade yt-dlp` y reintentar una vez.

## Camino A — Scribe v2 (default)

El motor vive en `${CLAUDE_SKILL_DIR}/scribe.py`. Es stdlib pura, no hay que instalar nada. La key está en `~/.config/elevenlabs/config`.

### A.1 — transcribir

Sin separar hablantes:

```bash
python3 ${CLAUDE_SKILL_DIR}/scribe.py "ARCHIVO" \
  --language spa --format txt -o "ARCHIVO.txt"
```

Separando hablantes, que es lo normal cuando hay más de una persona:

```bash
python3 ${CLAUDE_SKILL_DIR}/scribe.py "ARCHIVO" \
  --diarize --language spa -o "ARCHIVO-hablantes.md"
```

Transcribir y separar pasan en la misma llamada. **No hay un paso de diarización aparte como en el camino local.**

### A.2 — los flags

| Flag | Cuándo |
|---|---|
| `--diarize` | Hay más de una persona. Sale un `.md` con turnos etiquetados. |
| `--speakers N` | Ver la regla de abajo. Implica `--diarize`. |
| `--language` | Código ISO-639-3: `spa`, `eng`. Omitir si es spanglish. |
| `--keyterms "a,b,c"` | Nombres propios y jerga que el modelo no va a adivinar. Cuesta 20% más. |
| `--format` | `md` (turnos, default), `txt` (texto corrido), `json` (respuesta cruda), `segments` (para el pipeline de `watch`). |

### A.3 — la regla de `--speakers`

**Pasarlo solo cuando el número es un hecho, no una corazonada. Si hay duda, omitirlo.**

Esto es al revés que en el camino local, donde forzar el número casi siempre ayuda. Medido sobre el mismo audio de 13 minutos (2026-09-21):

| | Turnos | Turno más largo | Resultado |
|---|---|---|---|
| Sin `--speakers` | 134 | 624 chars | parte a cada persona en dos etiquetas, pero corta bien |
| `--speakers 2` | 41 | **3.278 chars** | **desastre**: metió 5 minutos de diálogo en un solo turno |
| `--speakers 3` | 131 | 423 chars | **el mejor** |

Quedarse corto con el número es el peor error posible: Scribe fusiona personas y el turno deja de servir. Pasarse no hace daño, solo parte a alguien en dos etiquetas que después se fusionan leyendo.

Si el número se puede deducir del contenido: **una primera corrida sin el flag, leer quién es quién, y recién ahí volver a correr con el número exacto.** Son 34 segundos y nueve centavos, sale barato hacerlo dos veces.

### A.4 — ponerle nombre a los hablantes

La salida trae etiquetas anónimas (`speaker_0`, `speaker_1`). Leer los primeros turnos, deducir quién es quién por el contenido, y reemplazar. Si dos etiquetas son obviamente la misma persona, fusionarlas en el reemplazo.

**Confirmar el mapeo con el usuario antes de reescribir el archivo.**

### A.5 — entregar

El archivo queda junto al original, y se le pasa al usuario con `SendUserFile` o como link markdown. Nunca pegar la transcripción entera en el chat.

### A.6 — cuando falla

- **`Scribe rechazó la petición: HTTP 401`** → la key no sirve. Revisar `~/.config/elevenlabs/config`.
- **`HTTP 422`** → algún parámetro está mal armado, casi siempre el `language_code`. Usa ISO-639-3 (`spa`), no `es`.
- **`HTTP 429`** → cuota o límite de ritmo. El script reintenta solo. Si insiste, avisar y ofrecer el camino local.
- **Sin internet** → camino local, avisando.

Archivos de más de 40 MB: el script extrae audio mono 16 kHz antes de subir. Pasa solo, no hay que hacer nada.

## Camino B — local con mlx_whisper (alternativa)

Gratis, offline, el audio nunca sale de la máquina. Más lento y menos preciso en audio con ruido. **Usar solo en los casos de la tabla de arriba.**

**El camino local requiere instalación previa** (mlx_whisper, y pyannote con token de Hugging Face para hablantes). Si `command -v mlx_whisper` no encuentra nada, decirle al usuario que el camino local no está instalado en esta máquina y ofrecer Scribe; no instalar sin que lo pida.

**Antes de correr nada, leer `local.md` completo** (mismo folder): instalación, elección de idioma, comando, diarización con pyannote y los errores ya diagnosticados.

## Archivos de este skill

| Archivo | Qué es |
|---|---|
| `scribe.py` | Motor de Scribe. Lo usa este skill. |
| `local.md` | Camino B completo (mlx_whisper + pyannote). Se lee solo si toca el camino local. |
| `diarize.py` | Diarización local con pyannote. Solo Camino B. |

