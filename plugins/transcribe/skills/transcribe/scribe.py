#!/usr/bin/env python3
"""Transcribe con ElevenLabs Scribe v2. Solo stdlib.

Motor compartido: lo usa el skill `transcribe` y el backend `elevenlabs`
de la skill `watch`. Scribe transcribe y separa hablantes en la misma
llamada, asi que no hay un paso de diarizacion aparte.

Uso:
    scribe.py ARCHIVO [--diarize] [--speakers N] [--language es]
              [--keyterms "Nombre,Marca"] [--format md|txt|json|segments]
              [-o SALIDA]
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"

# El endpoint acepta archivos grandes, pero subir 700 MB por una red
# domestica tarda mas que transcribirlos. Arriba de esto extraemos audio
# mono 16 kHz antes de subir: mismo resultado, una fraccion del peso.
SHRINK_ABOVE_BYTES = 40 * 1024 * 1024

MAX_ATTEMPTS = 4
RETRY_BASE_DELAY = 2.0

CONFIG_PATHS = [
    Path.home() / ".config" / "elevenlabs" / "config",
    Path.home() / ".config" / "watch" / ".env",
]


def load_api_key() -> str | None:
    value = os.environ.get("ELEVENLABS_API_KEY")
    if value and value.strip():
        return value.strip()
    for path in CONFIG_PATHS:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() != "ELEVENLABS_API_KEY":
                    continue
                val = val.strip()
                if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                    val = val[1:-1]
                if val:
                    return val
        except OSError:
            continue
    return None


def shrink_audio(src: Path, out_path: Path) -> Path:
    """Audio mono 16 kHz 64 kbps: ~480 kB por minuto, sin perdida util."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("falta ffmpeg. Instalar con: brew install ffmpeg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src.resolve()),
        "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        str(out_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise SystemExit(f"ffmpeg fallo al extraer audio: {result.stderr.strip()}")
    return out_path


def _build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----ScribeBoundary{uuid.uuid4().hex}"
    eol = b"\r\n"
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f"--{boundary}".encode()); buf.write(eol)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode()); buf.write(eol)
        buf.write(eol)
        buf.write(str(value).encode()); buf.write(eol)
    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    buf.write(f"--{boundary}".encode()); buf.write(eol)
    buf.write(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode())
    buf.write(eol)
    buf.write(f"Content-Type: {mimetype}".encode()); buf.write(eol)
    buf.write(eol)
    buf.write(file_path.read_bytes())
    buf.write(eol)
    buf.write(f"--{boundary}--".encode()); buf.write(eol)
    return buf.getvalue(), boundary


def _post(api_key: str, audio_path: Path, fields: dict[str, str]) -> dict:
    body, boundary = _build_multipart(fields, audio_path)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "transcribe-skill/1.0 (+claude-code; python-urllib)",
    }
    context = ssl.create_default_context()
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        request = Request(ENDPOINT, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=900, context=context) as response:
                payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = f" - {exc.read().decode('utf-8', errors='replace')[:400]}"
            except Exception:
                pass
            last = f"HTTP {exc.code}{detail}"
            # 4xx que no sea 429: no lo arregla reintentar.
            if 400 <= exc.code < 500 and exc.code != 429:
                raise SystemExit(f"Scribe rechazo la peticion: {last}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        if attempt < MAX_ATTEMPTS - 1:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f"[scribe] {last} - reintento en {delay:.0f}s "
                  f"({attempt + 2}/{MAX_ATTEMPTS})", file=sys.stderr)
            time.sleep(delay)
    raise SystemExit(f"Scribe fallo tras {MAX_ATTEMPTS} intentos: {last}")


def transcribe(
    path: str | Path,
    api_key: str | None = None,
    diarize: bool = False,
    speakers: int | None = None,
    language: str | None = None,
    keyterms: list[str] | None = None,
    work_dir: Path | None = None,
) -> dict:
    """Devuelve la respuesta cruda de Scribe."""
    api_key = api_key or load_api_key()
    if not api_key:
        raise SystemExit(
            "No hay key de ElevenLabs. Ponerla en ~/.config/elevenlabs/config "
            "como ELEVENLABS_API_KEY=... o exportarla en el entorno."
        )

    src = Path(path).expanduser()
    if not src.exists():
        raise SystemExit(f"No existe el archivo: {src}")

    upload = src
    if src.stat().st_size > SHRINK_ABOVE_BYTES:
        target = (work_dir or Path(os.environ.get("TMPDIR", "/tmp"))) / f"scribe-{uuid.uuid4().hex}.mp3"
        size_mb = src.stat().st_size / (1024 * 1024)
        print(f"[scribe] {size_mb:.0f} MB - extrayendo audio mono antes de subir...",
              file=sys.stderr)
        upload = shrink_audio(src, target)

    fields: dict[str, str] = {"model_id": MODEL}
    if diarize:
        fields["diarize"] = "true"
        if speakers:
            fields["num_speakers"] = str(speakers)
    if language:
        fields["language_code"] = language
    if keyterms:
        fields["keyterms"] = json.dumps(keyterms, ensure_ascii=False)

    print(f"[scribe] subiendo {upload.stat().st_size / 1024:.0f} kB a Scribe v2...",
          file=sys.stderr)
    data = _post(api_key, upload, fields)

    if upload != src:
        upload.unlink(missing_ok=True)
    return data


def turns(data: dict) -> list[dict]:
    """Agrupa las palabras en turnos por hablante."""
    out: list[dict] = []
    cur: dict | None = None
    for w in data.get("words") or []:
        if w.get("type") != "word":
            if cur:
                cur["text"] += w.get("text", "")
            continue
        speaker = w.get("speaker_id") or "speaker_0"
        if cur and cur["speaker"] == speaker:
            cur["text"] += w.get("text", "")
            cur["end"] = w.get("end", cur["end"])
        else:
            if cur:
                out.append(cur)
            cur = {
                "speaker": speaker,
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
                "text": w.get("text", ""),
            }
    if cur:
        out.append(cur)
    for t in out:
        t["text"] = t["text"].strip()
    return [t for t in out if t["text"]]


SEGMENT_MAX_SECONDS = 20.0


def segments(data: dict, max_seconds: float = SEGMENT_MAX_SECONDS) -> list[dict]:
    """Formato {start, end, text} que espera el pipeline de `watch`.

    Sin diarizacion, Scribe no marca cambios de hablante y todo el audio
    seria un solo bloque, inservible para alinear con los cuadros de video.
    Por eso se corta cada `max_seconds`, siempre en fin de oracion para no
    partir frases al medio.
    """
    out: list[dict] = []
    for t in turns(data):
        if t["end"] - t["start"] <= max_seconds:
            out.append({"start": round(t["start"], 2),
                        "end": round(t["end"], 2),
                        "text": t["text"]})
            continue
        # Turno largo: repartir las palabras en tramos cortados en punto final.
        words = [w for w in (data.get("words") or [])
                 if w.get("type") == "word"
                 and t["start"] <= w.get("start", 0.0) <= t["end"]]
        buf: list[str] = []
        seg_start = t["start"]
        last_end = t["start"]
        for w in words:
            buf.append(w.get("text", ""))
            last_end = w.get("end", last_end)
            ends_sentence = w.get("text", "").rstrip().endswith((".", "?", "!", "\u2026"))
            if last_end - seg_start >= max_seconds and ends_sentence:
                out.append({"start": round(seg_start, 2),
                            "end": round(last_end, 2),
                            "text": " ".join(buf).strip()})
                buf, seg_start = [], last_end
        if buf:
            out.append({"start": round(seg_start, 2),
                        "end": round(last_end, 2),
                        "text": " ".join(buf).strip()})
    return [s for s in out if s["text"]]


def _stamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def render(data: dict, fmt: str, title: str = "") -> str:
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    if fmt == "segments":
        return json.dumps(segments(data), ensure_ascii=False, indent=2)
    if fmt == "txt":
        return (data.get("text") or "").strip() + "\n"
    lines = []
    if title:
        lines.append(f"# {title}\n")
    for t in turns(data):
        lines.append(f"[{_stamp(t['start'])}] **{t['speaker']}**: {t['text']}\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribir con ElevenLabs Scribe v2")
    ap.add_argument("archivo")
    ap.add_argument("--diarize", action="store_true", help="separar hablantes")
    ap.add_argument("--speakers", type=int, help="cuantas personas hablan (mejora mucho la separacion)")
    ap.add_argument("--language", help="codigo ISO-639 del idioma, ej. spa o eng")
    ap.add_argument("--keyterms", help="nombres propios y jerga, separados por coma (+20%% de costo)")
    ap.add_argument("--format", default="md", choices=["md", "txt", "json", "segments"])
    ap.add_argument("-o", "--output", help="archivo de salida (default: stdout)")
    args = ap.parse_args()

    keyterms = [k.strip() for k in args.keyterms.split(",") if k.strip()] if args.keyterms else None
    data = transcribe(
        args.archivo,
        diarize=args.diarize or bool(args.speakers),
        speakers=args.speakers,
        language=args.language,
        keyterms=keyterms,
    )
    text = render(data, args.format, title=Path(args.archivo).stem if args.format == "md" else "")

    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        print(f"[scribe] escrito: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
