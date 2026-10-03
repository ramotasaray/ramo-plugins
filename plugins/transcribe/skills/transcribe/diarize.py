#!/usr/bin/env python3
"""Diariza un audio con pyannote y fusiona el resultado con una transcripción de mlx_whisper.

Uso:
    diarize.py AUDIO --whisper-json TRANSCRIPCION.json [-o SALIDA.md] [--speakers N]

Requiere el venv en ~/.local/share/summarize-call/pyannote-env y un token de Hugging Face.

NOTA DE IMPLEMENTACIÓN (2026-09-08) — no volver a diagnosticar esto desde cero:
    El decodificador propio de pyannote (torchcodec) NO carga en esta máquina. torchcodec
    soporta FFmpeg 4-8 y el Homebrew de acá va en FFmpeg 9 (libavutil.61), así que el dlopen
    de libtorchcodec_core*.dylib falla siempre. torchaudio 2.11 delega en torchcodec, o sea
    que tampoco sirve.
    Solución: nunca pasarle una ruta al pipeline. Se decodifica con el binario `ffmpeg`
    (que sí funciona con FFmpeg 9) a WAV 16 kHz mono PCM, se lee con el módulo `wave` de la
    stdlib y se le entrega a pyannote el dict {'waveform': tensor, 'sample_rate': int}.
    Cero dependencias nuevas y cero acoplamiento a la versión de FFmpeg.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
import wave
from pathlib import Path

# El import de pyannote.audio emite un UserWarning largo sobre torchcodec. Es esperado:
# no usamos su decodificador. Silenciarlo para que no tape los mensajes reales.
# El mensaje arranca con un salto de línea, de ahí el (?s) para que `.` cace el \n.
warnings.filterwarnings("ignore", message=r"(?s).*torchcodec.*")


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def find_token() -> str | None:
    """Busca el token de Hugging Face en orden de preferencia.

    Existe porque los shells no interactivos no leen ~/.zshrc: sin esta cascada el script
    falla cuando lo lanza un agente aunque el token esté configurado.
    """
    # 1. Variables de entorno (lo normal si alguien hizo `source ~/.zshrc`).
    for var in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val.strip()

    # 2. Token guardado por `hf auth login` (~/.cache/huggingface/token).
    try:
        from huggingface_hub import get_token

        val = get_token()
        if val:
            return val.strip()
    except Exception:
        pass

    # 3. Último recurso: leerlo de los rc del shell.
    pattern = re.compile(
        r"""^\s*export\s+(?:HF_TOKEN|HUGGING_FACE_HUB_TOKEN)\s*=\s*['"]?([^'"\s#]+)""",
        re.MULTILINE,
    )
    for rc in ("~/.zshrc", "~/.zshenv", "~/.bashrc", "~/.profile"):
        path = Path(rc).expanduser()
        try:
            m = pattern.search(path.read_text())
        except OSError:
            continue
        if m:
            return m.group(1)
    return None


def to_wav16k(src: Path) -> Path:
    """Decodifica cualquier formato a WAV 16 kHz mono PCM con el binario ffmpeg.

    Siempre convierte, incluso si la entrada ya es .wav: puede venir en 48 kHz estéreo.
    """
    tmp = Path(tempfile.mkdtemp()) / "audio16k.wav"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not tmp.exists():
        raise RuntimeError(f"ffmpeg no pudo decodificar {src}:\n{proc.stderr.strip()}")
    return tmp


def load_waveform(wav: Path):
    """Lee un WAV PCM 16-bit con la stdlib y lo devuelve como tensor (canal, tiempo)."""
    import numpy as np
    import torch

    with wave.open(str(wav), "rb") as w:
        if w.getsampwidth() != 2:
            raise RuntimeError(f"se esperaba PCM 16-bit, vino {w.getsampwidth() * 8}-bit")
        channels = w.getnchannels()
        sample_rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32).reshape(-1, channels).T
    audio /= 32768.0
    return torch.from_numpy(np.ascontiguousarray(audio)), sample_rate


def diarize(wav: Path, token: str, speakers: int | None,
            min_speakers: int | None, max_speakers: int | None):
    import torch
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1", token=token
    )
    if torch.backends.mps.is_available():
        # Algunos ops de pyannote todavía no tienen kernel MPS; si falla, CPU.
        try:
            pipeline.to(torch.device("mps"))
        except Exception:
            pass

    kwargs = {}
    if speakers:
        kwargs["num_speakers"] = speakers
    else:
        if min_speakers:
            kwargs["min_speakers"] = min_speakers
        if max_speakers:
            kwargs["max_speakers"] = max_speakers

    # Audio en memoria, no una ruta: evita el decodificador roto (ver nota del encabezado).
    waveform, sample_rate = load_waveform(wav)
    output = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **kwargs)

    # pyannote 4.x devuelve un DiarizeOutput; 3.x devolvía la Annotation directo.
    # `exclusive_speaker_diarization` resuelve los solapamientos asignando un solo
    # hablante por instante, que es lo que necesita el merge con whisper.
    annotation = getattr(output, "exclusive_speaker_diarization", None)
    if annotation is None:
        annotation = getattr(output, "speaker_diarization", output)

    turns = [
        {"start": seg.start, "end": seg.end, "speaker": spk}
        for seg, _, spk in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t["start"])
    return turns


def speaker_for(seg_start: float, seg_end: float, turns: list[dict]) -> str:
    """El hablante que más se solapa con el segmento de whisper.

    Sin solapamiento cae al turno más cercano en el tiempo. Pasa en frases cortas
    ("Sí", "Gracias") y en los cierres, donde whisper oye voz y pyannote no marcó turno.
    Etiquetarlas con el vecino es mejor que un `SPEAKER_?`, que además parte el párrafo.
    """
    best, best_overlap = None, 0.0
    for t in turns:
        overlap = min(seg_end, t["end"]) - max(seg_start, t["start"])
        if overlap > best_overlap:
            best, best_overlap = t["speaker"], overlap
    if best is not None:
        return best

    nearest, nearest_gap = "SPEAKER_?", float("inf")
    for t in turns:
        gap = max(t["start"] - seg_end, seg_start - t["end"], 0.0)
        if gap < nearest_gap:
            nearest, nearest_gap = t["speaker"], gap
    return nearest


def merge(segments: list[dict], turns: list[dict]) -> list[dict]:
    """Etiqueta cada segmento de whisper y colapsa los consecutivos del mismo hablante."""
    merged: list[dict] = []
    for seg in segments:
        spk = speaker_for(seg["start"], seg["end"], turns)
        text = seg["text"].strip()
        if not text:
            continue
        if merged and merged[-1]["speaker"] == spk:
            merged[-1]["text"] += " " + text
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(
                {"speaker": spk, "start": seg["start"], "end": seg["end"], "text": text}
            )
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("--whisper-json", type=Path,
                    help="JSON de mlx_whisper. Sin esto solo se emiten los turnos, sin texto.")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--speakers", type=int, help="Número exacto de hablantes, si se conoce.")
    ap.add_argument("--min-speakers", type=int)
    ap.add_argument("--max-speakers", type=int)
    args = ap.parse_args()

    token = find_token()
    if not token:
        print("ERROR: no se encontró el token de Hugging Face (HF_TOKEN ni ~/.zshrc ni "
              "`hf auth login`). Ver el paso 5 del SKILL.md.", file=sys.stderr)
        return 1
    if not args.audio.exists():
        print(f"ERROR: no existe {args.audio}", file=sys.stderr)
        return 1

    wav = to_wav16k(args.audio)
    try:
        turns = diarize(wav, token, args.speakers, args.min_speakers, args.max_speakers)
    finally:
        wav.unlink(missing_ok=True)
        wav.parent.rmdir()

    n = len({t["speaker"] for t in turns})
    print(f"{len(turns)} turnos, {n} hablantes detectados", file=sys.stderr)

    if args.whisper_json:
        data = json.loads(args.whisper_json.read_text())
        rows = merge(data["segments"], turns)
        lines = [f"[{hms(r['start'])}] **{r['speaker']}**: {r['text']}" for r in rows]
    else:
        lines = [f"[{hms(t['start'])} → {hms(t['end'])}] **{t['speaker']}**" for t in turns]

    out = "\n\n".join(lines) + "\n"
    if args.output:
        args.output.write_text(out)
        print(f"Escrito: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
