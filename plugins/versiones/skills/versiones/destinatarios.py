#!/usr/bin/env python3
"""Destinatarios de "responder a todos" para un hilo de Gmail.

Uso:
  destinatarios.py <threadId>                 imprime para/cc sugeridos (JSON)
  destinatarios.py --check <draft.json>       compara el destino del borrador con el hilo;
                                              sale con código 1 si falta alguien

Existe porque el 2026-10-08 un correo dentro de un hilo salió con los destinatarios
escritos a mano y dejó fuera a una clienta que estaba en copia en todos los mensajes
anteriores. Ver ENVIO.md, paso 9.

Los correos del propio usuario salen de correos_propios en config.json: con esa lista
vacía, sus direcciones aparecerían como destinatarios de su propio correo.
"""
import json, os, subprocess, sys
from email.utils import getaddresses

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402


def propios():
    return set(config.cargar()["correos_propios"])


def ultimo_mensaje(thread_id):
    gws = config.gws_binario(config.cargar())
    if not gws:
        sys.exit("no encuentro gws: sin él no se puede leer el hilo")
    out = subprocess.run(
        [gws, "gmail", "users", "threads", "get", "--params",
         json.dumps({"userId": "me", "id": thread_id, "format": "metadata",
                     "metadataHeaders": ["From", "To", "Cc"]})],
        capture_output=True, text=True).stdout
    d = json.loads(out[out.index("{"):])
    h = {x["name"].lower(): x["value"] for x in d["messages"][-1]["payload"]["headers"]}
    return h


def responder_a_todos(thread_id, h=None, yo=None):
    """h: encabezados del último mensaje (para probar sin red). yo: correos propios."""
    h = h if h is not None else ultimo_mensaje(thread_id)
    yo = propios() if yo is None else yo
    remitente = [a.lower() for _, a in getaddresses([h.get("from", "")])]
    to = [a.lower() for _, a in getaddresses([h.get("to", "")])]
    cc = [a.lower() for _, a in getaddresses([h.get("cc", "")])]
    if set(remitente) & yo:            # el último es del usuario: se repiten sus destinatarios
        para, copia = to, cc
    else:                              # el último es de otro: se le contesta a él, el resto en copia
        para, copia = remitente, to + cc
    para = [a for a in dict.fromkeys(para) if a and a not in yo]
    copia = [a for a in dict.fromkeys(copia) if a and a not in yo and a not in para]
    return para, copia


def direcciones(campo):
    if isinstance(campo, list):
        campo = ", ".join(campo)
    return {a.lower() for _, a in getaddresses([campo or ""]) if a}


def check(path):
    d = json.load(open(path))
    destinos = [m.get("destino", d.get("destino")) for m in d.get("mensajes", [])] or [d.get("destino")]
    falla = False
    for dest in destinos:
        if not dest or not dest.get("threadId"):
            continue
        para, copia = responder_a_todos(dest["threadId"])
        tiene = direcciones(dest.get("para")) | direcciones(dest.get("cc"))
        faltan = [a for a in para + copia if a not in tiene]
        if faltan:
            falla = True
            print(f"FALTAN en el hilo {dest['threadId']}: {', '.join(faltan)}")
            print("  Si es a propósito, que el usuario lo diga en el chat. Si no, agregalos a destino.cc.")
        else:
            print(f"OK hilo {dest['threadId']}: estan todos los del ultimo mensaje")
    sys.exit(1 if falla else 0)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        check(sys.argv[2])
    elif len(sys.argv) == 2:
        para, copia = responder_a_todos(sys.argv[1])
        print(json.dumps({"para": ", ".join(para), "cc": ", ".join(copia)}, ensure_ascii=False))
    else:
        print(__doc__)
        sys.exit(2)
