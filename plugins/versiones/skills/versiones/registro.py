#!/usr/bin/env python3
"""Registro de preferencias de escritura del usuario, sacado de /versiones.

Agrega líneas a registro.jsonl, en la carpeta de datos del usuario (ver config.py).
Es append-only: nunca se edita a mano ni se borra. Existe para que una revisión
periódica de escritura mida qué elige, edita y anota el usuario, y de ahí salgan
reglas para su preferencias.md.

Uso:
  registro.py nota   <draftId> --db <out_dir>   antes de rehacer secciones con nota (ENVIO.md paso 7)
  registro.py cierre <draftId> --db <out_dir>   al archivar un borrador cerrado (SKILL.md paso 1a)

<out_dir> es el mismo que se pasó a ArtifactData con out_dir: tiene que contener
drafts/<draftId>.json y drafts/<draftId>/secciones/*.json
(o, en un hilo, drafts/<draftId>/mensajes/*.json y drafts/<draftId>/mensajes/<mid>/secciones/*.json).
"""
import argparse, json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

BASE = config.carpeta()
REGISTRO = config.ruta("registro.jsonl")
LARGOS = ["minima", "ajustada", "completa"]


def cargar(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def draft_json(draft_id):
    for d in (os.path.join(BASE, "drafts", draft_id), os.path.join(BASE, "drafts", "_cerrados", draft_id)):
        j = cargar(os.path.join(d, "draft.json"))
        if j:
            return j
    sys.exit(f"no encuentro draft.json de {draft_id} en drafts/ ni en drafts/_cerrados/")


def mensajes(draft, db, draft_id):
    """Devuelve [(mid|None, secciones_del_draft, dir_secciones_db, doc_mensaje_db)]."""
    raiz = os.path.join(db, "drafts", draft_id)
    if "mensajes" in draft:
        out = []
        for m in draft["mensajes"]:
            out.append((m["id"], m.get("secciones", []),
                        os.path.join(raiz, "mensajes", m["id"], "secciones"),
                        cargar(os.path.join(raiz, "mensajes", m["id"] + ".json")) or {}))
        return out
    return [(None, draft.get("secciones", []), os.path.join(raiz, "secciones"),
             cargar(os.path.join(db, "drafts", draft_id + ".json")) or {})]


def texto_final(sec_db, pick, opts):
    ed = sec_db.get("textoEditado")
    if ed and sec_db.get("editadoDe", pick) == pick:
        return ed, True
    return opts.get(pick, {}).get("text", ""), False


def ya_registrado(draft_id, tipo):
    if not os.path.exists(REGISTRO):
        return False
    with open(REGISTRO) as f:
        for linea in f:
            try:
                r = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if r.get("tipo") == tipo and r.get("draftId") == draft_id:
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tipo", choices=["nota", "cierre"])
    ap.add_argument("draftId")
    ap.add_argument("--db", required=True)
    a = ap.parse_args()

    if a.tipo == "cierre" and ya_registrado(a.draftId, "cierre"):
        print(f"{a.draftId}: cierre ya registrado, no se duplica")
        return

    draft = draft_json(a.draftId)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {"tipo": a.tipo, "ts": ts, "draftId": a.draftId,
            "canal": draft.get("canal"), "titulo": draft.get("titulo")}
    filas = []

    for mid, secciones, dir_sec, doc_msg in mensajes(draft, a.db, a.draftId):
        extra = {"mensaje": mid} if mid else {}
        if a.tipo == "nota" and doc_msg.get("notaGeneral"):
            filas.append({**base, **extra, "seccion": None, "nota": doc_msg["notaGeneral"]})
        if a.tipo == "cierre":
            envio = doc_msg.get("envio") or {}
            filas.append({**base, **extra, "seccion": None, "cerradoSinEnviar": not envio,
                          "envioEstado": envio.get("estado"), "textoEnviado": envio.get("textoFinal")})
        for s in secciones:
            opts = s.get("opts", {})
            sec_db = cargar(os.path.join(dir_sec, s["id"] + ".json")) or {}
            pick = sec_db.get("pick") or s.get("recomendada")
            if a.tipo == "nota":
                if not sec_db.get("nota"):
                    continue
                final, editado = texto_final(sec_db, pick, opts)
                filas.append({**base, **extra, "seccion": s["id"], "nombre": s.get("nombre"),
                              "pick": pick, "textoIA": opts.get(pick, {}).get("text", ""),
                              "textoEditado": final if editado else None, "nota": sec_db["nota"]})
            else:
                final, editado = texto_final(sec_db, pick, opts)
                filas.append({**base, **extra, "seccion": s["id"], "nombre": s.get("nombre"),
                              "job": s.get("job"), "recomendada": s.get("recomendada"), "pick": pick,
                              "tocada": bool(sec_db), "editado": editado, "unida": bool(sec_db.get("unida")),
                              "largos": {k: len(opts[k]["text"]) for k in LARGOS if k in opts},
                              "textoIA": opts.get(pick, {}).get("text", ""), "textoFinal": final})

    with open(REGISTRO, "a") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{a.draftId}: {len(filas)} filas de {a.tipo} en registro.jsonl")


if __name__ == "__main__":
    main()
