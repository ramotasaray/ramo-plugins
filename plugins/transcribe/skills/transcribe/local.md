# Transcribe — Camino B, local con mlx_whisper

> Se llega acá desde `SKILL.md`, solo en los casos de su tabla "Elegir motor". Gratis,
> offline, el audio nunca sale de la máquina. Más lento y menos preciso en audio con ruido.

### B.0 — verificar instalación

```bash
command -v mlx_whisper || echo "MISSING"
```

Si falta, instalar (aislado, porque el python3 default de Homebrew puede ir adelantado de los wheels de MLX):

```bash
uv tool install mlx-whisper --python 3.12
```

`ffmpeg` también es requisito (ya está en `/opt/homebrew/bin/ffmpeg`).

### B.1 — inspeccionar el archivo

```bash
ffprobe -v error -show_entries format=duration,size -of default=nw=1 "ARCHIVO"
```

No hace falta convertir nada: mlx_whisper acepta directo `.m4a`, `.mp3`, `.wav`, `.aiff`, `.mp4`, `.mov`, `.opus`, etc. (le pasa el archivo a ffmpeg internamente).

Si el archivo dura más de ~45 min, avisarle al usuario el tiempo estimado antes de arrancar (≈1 min de cómputo por cada 15 min de audio).

### B.2 — elegir el idioma

Esta es la decisión que más afecta el resultado.

| Caso | Flag |
|---|---|
| Todo en español | `--language es` |
| Todo en inglés | `--language en` |
| Spanglish / no sé qué es | **omitir el flag** |

Whisper detecta el idioma una sola vez (primeros 30 s) y lo aplica a todo el archivo: no hay detección por segmento. Consecuencias prácticas:

- **Forzar el idioma correcto siempre gana** cuando el audio es monolingüe. Evita que un tramo de silencio o de ruido haga que el modelo se desvíe.
- **Para spanglish, omitir `--language`** y dejar que detecte. El modelo transcribe las palabras en inglés dentro de una frase en español razonablemente bien; lo que no hace es cambiar de "modo" a mitad del archivo.
- Si el audio arranca en un idioma y a los 10 minutos cambia por completo al otro, ningún flag lo resuelve: **cortar el archivo** en los puntos de cambio con `ffmpeg -ss X -to Y` y transcribir cada parte con su idioma.

**Nunca usar `--task translate`** salvo que el usuario pida explícitamente la traducción al inglés. El default (`transcribe`) mantiene el idioma original.

### B.3 — transcribir

Comando base:

```bash
mlx_whisper "ARCHIVO" \
  --model mlx-community/whisper-large-v3-turbo \
  --output-dir "DIRECTORIO_DEL_ARCHIVO" \
  --output-format txt \
  --condition-on-previous-text False \
  --verbose False
```

Notas sobre los flags:

- `--condition-on-previous-text False` — **ponerlo siempre**. Sin esto, whisper entra en bucles de alucinación en tramos de silencio o música y repite la misma frase decenas de veces. Es el problema #1 en audios largos.
- `--output-format` — `txt` para leer, `srt`/`vtt` para subtítulos, `json` si hay que procesar los timestamps, `all` para todos.
- `--word-timestamps True` — solo si hace falta precisión palabra por palabra (es más lento).
- `--initial-prompt "..."` — pasarle nombres propios, marcas o jerga que aparezcan en el audio (ej. `--initial-prompt "Cal.com, referido.pro, AEO, Ramo"`). Mejora bastante la ortografía de términos raros.

El output queda como `ARCHIVO.txt` en `--output-dir`.

### B.4 — entregar

1. Leer el `.txt` generado.
2. Revisarlo por señales de alucinación: la misma frase repetida 3+ veces seguidas, o un bloque de texto que no pega con el resto. Si aparece, re-correr ese tramo cortado con `ffmpeg -ss`.
3. Decirle al usuario dónde quedó el archivo y pegarle el texto en el chat si es corto (menos de ~40 líneas). Si es largo, resumir de qué se trata y darle el path.
4. Preguntar si quiere algo más con el contenido (resumen, extraer acciones, un post) en vez de asumirlo.

### B.5 (opcional) — separar hablantes (diarización)

Whisper **no** identifica quién habla: eso lo hace un modelo aparte. Acá se usa `pyannote/speaker-diarization-community-1` corriendo local.

El entorno ya está instalado en `~/.local/share/summarize-call/pyannote-env` (el nombre viene del skill `summarize-call`, ya archivado; no mover ni duplicar el entorno). Verificar:

```bash
~/.local/share/summarize-call/pyannote-env/bin/python -c "import pyannote.audio; print(pyannote.audio.__version__)"
```

**Requiere un token de Hugging Face.** Ya está configurado en esta máquina (`export HF_TOKEN` en `~/.zshrc`) y **`diarize.py` lo encuentra solo**: no hace falta `source ~/.zshrc` ni exportar nada antes de correrlo. El script busca, en orden: variables de entorno (`HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`, `HUGGINGFACE_TOKEN`) → el token de `hf auth login` (`~/.cache/huggingface/token`) → `~/.zshrc`, `~/.zshenv`, `~/.bashrc`, `~/.profile`.

En una máquina nueva, el setup es a mano (no lo puede hacer Claude: implica crear cuenta y aceptar términos):

1. Cuenta en huggingface.co y token de lectura en https://huggingface.co/settings/tokens
2. Aceptar las condiciones en https://huggingface.co/pyannote/speaker-diarization-community-1
3. `export HF_TOKEN="hf_..."` en `~/.zshrc`

Flujo completo, encadenado con B.3:

```bash
# 1. transcribir pidiendo JSON (necesario para el merge)
mlx_whisper "ARCHIVO" --model mlx-community/whisper-large-v3-turbo \
  --language es --output-dir DIR --output-format json \
  --condition-on-previous-text False --verbose False

# 2. diarizar y fusionar
~/.local/share/summarize-call/pyannote-env/bin/python \
  ${CLAUDE_SKILL_DIR}/diarize.py "ARCHIVO" \
  --whisper-json DIR/ARCHIVO.json \
  --speakers N \
  -o DIR/ARCHIVO-hablantes.md
```

`diarize.py` acepta cualquier formato que lea ffmpeg (`.m4a`, `.mp3`, `.mp4`, `.wav`…): convierte internamente.

Flags útiles:

- `--speakers N` — **usarlo siempre que se sepa cuántas personas hablan. Es el flag que más cambia el resultado.**
- `--min-speakers` / `--max-speakers` — cuando el número es aproximado.

Lo de `--speakers` está medido, no es teoría. Sobre 3 minutos de un acta con 5 personas (2026-07-30):

| | Sin forzar | `--speakers 5` |
|---|---|---|
| Hablantes detectados | 4 (de 5) | 5 |
| Presentaciones iniciales | 2 personas fusionadas en una | 5/5 correctas |
| Respuestas cortas ("Sí") | atribuidas mal | correctas |

Sin forzar, el modelo colapsa a dos personas en una y después arrastra ese error a todo el archivo. Cuando el número de hablantes se puede deducir del contenido (en actas y reuniones se presentan al inicio), **transcribir primero, leer quiénes son, y recién entonces diarizar con el número exacto.**

La salida son etiquetas anónimas (`SPEAKER_00`, `SPEAKER_01`). Para ponerles nombre: leer los primeros turnos, deducir quién es quién por el contenido, y hacer un reemplazo. Confirmar el mapeo con el usuario antes de reescribir el archivo.

**Expectativas realistas:** el error típico de diarización ronda 10-15% del tiempo de audio. Falla sobre todo en interrupciones, hablantes que se solapan y voces parecidas del mismo género. Sirve para navegar y citar, no como fuente de verdad legal sin revisar.

**No validar con audio de TTS.** Un clip generado con `say` no sirve como prueba: las voces sintéticas del mismo motor salen sin ruido de fondo ni variación de micrófono, y el modelo de embeddings las trata como la misma persona. Probar siempre con voces humanas reales.

### Por qué `diarize.py` no le pasa el archivo a pyannote

**Diagnosticado y resuelto el 2026-09-08. No volver a investigarlo desde cero.**

El decodificador de audio propio de pyannote (`torchcodec`) **no carga en esta máquina y no va a cargar.** Está instalado, pero sus dylibs no abren: `libtorchcodec_core8.dylib` pide `@rpath/libavutil.60.dylib` (FFmpeg 8) y el Homebrew de acá va en FFmpeg 9 (`libavutil.61`). torchcodec solo soporta FFmpeg 4–8. `torchaudio` 2.11 tampoco sirve de alternativa: delega en torchcodec y falla igual.

Síntoma: `RuntimeError: torchcodec is not available. Cannot read audio file.`

**El arreglo:** nunca pasarle una ruta al pipeline. `diarize.py` decodifica con el binario `ffmpeg` (que sí funciona con FFmpeg 9) a WAV 16 kHz mono PCM, lo lee con el módulo `wave` de la stdlib y le entrega a pyannote el dict `{'waveform': tensor, 'sample_rate': int}`. Es la vía que recomienda el propio mensaje de error de pyannote. Cero dependencias nuevas y queda desacoplado de la versión de FFmpeg.

**Lo que NO hay que hacer:**

- Degradar el `ffmpeg` del sistema. mlx_whisper usa el 9 y funciona bien.
- Instalar `ffmpeg@7` con `DYLD_FALLBACK_LIBRARY_PATH`. Funcionaría, pero es una fórmula keg-only entera y un wrapper de entorno para nada: el waveform en memoria ya resuelve el problema.
- Fijar versiones viejas de `torch`/`torchcodec`. Rompe pyannote y no arregla la incompatibilidad de FFmpeg.

Al importar `pyannote.audio` todavía sale un `UserWarning` largo sobre torchcodec. Es esperado y está silenciado en el script; si aparece en algún otro lado, es ruido, no una falla.

El venv se creó con `uv` y **no tiene `pip` en `bin/`**. Para instalarle algo: `uv pip install --python ~/.local/share/summarize-call/pyannote-env/bin/python PAQUETE`.

Rendimiento medido (MacBook Air M2, audio real de 26 min en español, 3 hablantes, 2026-09-08):

| Etapa | Tiempo |
|---|---|
| Transcripción (whisper turbo) | 1 min 30 s |
| Diarización | 2 min 33 s |

O sea ~10x tiempo real: la diarización tarda cerca del doble que la transcripción, no mucho más. La nota vieja de "aproximadamente lo mismo que dura el audio" era de cuando corría en CPU pura; con MPS activo es bastante más rápido. Para un audio de una hora, contar unos 10 minutos entre las dos etapas.

### Modelos locales

`large-v3-turbo` es el default correcto: ~1.6 GB, la mejor calidad multilingüe disponible por su costo de cómputo. Alternativas solo si hay razón:

| Modelo | Cuándo |
|---|---|
| `mlx-community/whisper-large-v3-turbo` | **Default.** Todo. |
| `mlx-community/whisper-large-v3-mlx` | Audio muy difícil (ruido fuerte, acentos marcados, code-switching pesado). ~3 GB, ~3x más lento, algo mejor en multilingüe. |
| `mlx-community/whisper-medium-mlx` | Nunca en esta máquina. Turbo es mejor y más rápido. |

**Revisado el 2026-08-20 contra el estado del arte.** Sigue siendo la elección correcta para esta máquina: Parakeet (NVIDIA) corre ~4x más rápido en MLX, pero la versión porteada es solo inglés y las variantes multilingües no están en MLX con paridad. Para la mezcla español/inglés de Ramo, Whisper gana. No cambiar el default sin re-verificar que exista un port MLX multilingüe estable.

Los modelos se cachean en `~/.cache/huggingface/`. La primera corrida de un modelo nuevo baja los pesos (2-3 min); después arranca en ~1.5 s.

### Rendimiento del camino local

Medido en el MacBook Air M2 / 16 GB de referencia con `large-v3-turbo`:

- 10 min de audio → **40 s**
- 1 h de audio → **~4 min**
- Uso de RAM: cómodo, no compite con el resto del sistema.
- La diarización de B.5 suma aparte, cerca del doble de lo que tardó la transcripción. Tabla medida en ese paso.
