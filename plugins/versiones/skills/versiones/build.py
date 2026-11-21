#!/usr/bin/env python3
"""Inyecta un draft.json en template.html y escribe el HTML listo para publicar.

    python3 build.py draft.json [-o salida.html]

El agente nunca lee ni edita template.html. Solo escribe draft.json y corre esto.
Imprime un resumen (palabras por version y por seccion, avisos) para que el agente
sepa como quedo sin abrir el HTML.

El draft.json acepta dos formas:

  un mensaje     {..., "secciones": [...]}
  hilo           {..., "mensajes": [{"id": "...", "titulo": "...", "secciones": [...]}, ...]}

La forma de un mensaje se normaliza a un hilo de uno solo y conserva sus rutas
viejas en la base de datos, para no romper borradores ya publicados.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
from contrato import KEYS, SOLO, Bad, hashear, palabras, validar  # noqa: E402


def preparar(path):
    """Carga un draft.json, lo valida y le calcula h, rev y revHora.

    Devuelve (d, avisos, huella, rev_path). Levanta Bad si el contrato no cierra,
    y las excepciones de json/os si el archivo no se puede leer."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    avisos = validar(d)
    for msg in d["mensajes"]:
        for s in msg["secciones"]:
            s["h"] = hashear(s)
            s["opcional"] = bool(s.get("opcional", False))

    # rev: cambia si y solo si cambio el texto de alguna seccion. Cuando cambia, la
    # pagina descarta notaGeneral, listo y envio en la primera lectura. Sale del
    # contenido y no del reloj, asi que reconstruir un draft intacto da el mismo rev.
    # revHora es solo la etiqueta del encabezado y no invalida nada.
    huella = hashlib.sha256(
        "|".join(s["h"] for msg in d["mensajes"] for s in msg["secciones"])
        .encode("utf-8")).hexdigest()[:12]
    rev_path = os.path.join(os.path.dirname(os.path.abspath(path)), "rev.txt")
    rev = None
    if os.path.exists(rev_path):
        with open(rev_path, encoding="utf-8") as f:
            lineas = [x.strip() for x in f.read().splitlines() if x.strip()]
        if len(lineas) == 2 and lineas[1] == huella:
            rev = lineas[0]
        elif len(lineas) == 1:
            avisos.append("rev.txt de una version anterior: este borrador arranca con rev "
                          "nuevo y pierde notaGeneral, listo y envio en su primera lectura. "
                          "Pasa una sola vez, por borrador.")
    d["rev"] = rev or huella
    d["revHora"] = datetime.datetime.now().strftime("%H:%M")
    d.setdefault("marcadores", {})
    d.setdefault("adjuntos", [])
    d.setdefault("destino", {})
    d.setdefault("cwd", os.getcwd())
    return d, avisos, huella, rev_path


def partir(tpl):
    """Separa el CSS y el JS del template en dos archivos publicables aparte.

    El HTML principal queda en unos 3 KB mas el draft. Eso es el punto: el
    `read` del artifact devuelve inline lo que pesa menos de 25 KB, y arriba de
    ese techo obliga a leer la pagina entera desde un archivo local. Ese era el
    peaje de ~40.000 tokens por republicacion que esta funcion existe para matar.

    El draft.json YA NO va inline: sale como d/<draftId>.json y la cascara lo pide
    por fetch. Asi el HTML principal queda fijo en ~3 KB en vez de crecer con el
    texto. Lo que lo hace distinto entre publicaciones es __DEFECTO__, el borrador
    que abre por omision, asi que el harness no la rechaza por contenido repetido.

    Salen TRES archivos y no dos. El bootstrap tambien se va a boot.js: es lo que
    pide el borrador por fetch y pinta la fila de tabs, y adentro del HTML pesaba
    4 KB que se pagaban en cada `read`. En la cascara queda solo su etiqueta con
    data-defecto, que es lo unico que cambia entre publicaciones.

    El <script> de la interfaz se BORRA del HTML en vez de quedar como
    <script src="app.js">: app.js lo inyecta boot.js recien cuando el fetch del
    borrador volvio. Si quedara estatico correria antes y no encontraria nada.
    """
    m = re.search(r"[ \t]*<style>\n(.*?)\n</style>", tpl, re.S)
    if not m:
        raise Bad("template.html: no encuentro el bloque <style>...</style>.")
    css = m.group(1)
    tpl = tpl[:m.start()] + '<link rel="stylesheet" href="app.css">' + tpl[m.end():]

    m = re.search(r"[ \t]*<script id=\"boot\"[^>]*>\n(.*?)\n</script>", tpl, re.S)
    if not m:
        raise Bad("template.html: no encuentro el bloque <script id=\"boot\">...</script>.")
    boot = m.group(1)
    tpl = tpl[:m.start()] + \
        '<script id="boot" data-defecto="__DEFECTO__" src="boot.js"></script>' + tpl[m.end():]

    m = re.search(r"[ \t]*<script>\n(.*?)\n</script>", tpl, re.S)
    if not m:
        raise Bad("template.html: no encuentro el bloque <script>...</script> de la interfaz.")
    js = m.group(1)
    tpl = tpl[:m.start()] + '<!-- app.js lo inyecta boot.js -->' + tpl[m.end():]
    return tpl, css, js, boot


def dentro(ruta, base):
    """True si `ruta` esta adentro de `base` (o es `base`)."""
    ruta = os.path.abspath(ruta)
    base = os.path.abspath(base)
    return ruta == base or ruta.startswith(base + os.sep)


def main():
    ap = argparse.ArgumentParser(description="Arma el HTML de la herramienta de versiones.")
    ap.add_argument("draft", help="ruta al draft.json")
    ap.add_argument("-o", "--out", help="ruta del HTML de salida "
                                        "(default: versiones.html junto al draft)")
    args = ap.parse_args()

    aqui = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(aqui, "template.html")
    # Los borradores viven en la carpeta de datos del usuario, no en la del plugin:
    # la del plugin se reemplaza entera en cada actualizacion.
    config.asegurar()
    cfg = config.cargar()
    DRAFTS = config.ruta("drafts")
    draft_abs = os.path.abspath(args.draft)
    if not os.path.exists(tpl_path):
        print("ERROR: no encuentro template.html junto a build.py (" + tpl_path + ")", file=sys.stderr)
        return 2

    try:
        d, avisos, huella, rev_path = preparar(args.draft)
    except FileNotFoundError:
        print("ERROR: no existe " + args.draft, file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print("ERROR: el draft.json no es JSON valido: " + str(e), file=sys.stderr)
        return 2
    except Bad as e:
        print("ERROR de contrato en el draft.json:\n  " + str(e), file=sys.stderr)
        return 1


    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    for marca in ("__DEFECTO__",):
        if marca not in tpl:
            print("ERROR: template.html no tiene el marcador " + marca, file=sys.stderr)
            return 2

    try:
        tpl, css, js, boot = partir(tpl)
    except Bad as e:
        print("ERROR: " + str(e), file=sys.stderr)
        return 2

    # La cascara ya no lleva el draft adentro. Lo unico que la distingue entre
    # publicaciones es cual borrador abre por omision.
    # El <title> es fijo ("Versiones"): es el nombre del artifact en las sesiones y no
    # debe cambiar con cada borrador.
    html = tpl.replace("__DEFECTO__", d["draftId"])

    # ---- la fuente es permanente, la salida es efimera ----
    # El draft.json vive en drafts/<draftId>/ y sobrevive a la sesion. Lo construido
    # va al scratchpad, que es lo unico que la tool Artifact deja publicar.
    if not dentro(draft_abs, DRAFTS):
        avisos.append("el draft.json no esta en " + DRAFTS + "/<draftId>/. Si se cierra la sesion "
                      "la pagina no se puede reconstruir: los picks siguen en la base, pero el "
                      "texto se pierde y hay que reescribirlo. Movelo ahi antes de seguir.")

    out = args.out or os.path.join(os.path.dirname(draft_abs), "versiones.html")
    outdir = os.path.dirname(os.path.abspath(out))
    if dentro(outdir, DRAFTS):
        print("ERROR: no se construye adentro de " + DRAFTS + ".\n"
              "  Ahi vive el draft.json, que es la fuente y no se publica: la tool Artifact solo\n"
              "  acepta archivos bajo el working directory o el scratchpad de la sesion.\n"
              "  Corre:  python3 " + os.path.abspath(__file__) + " " + args.draft +
              " --out <scratchpad>/versiones/versiones.html", file=sys.stderr)
        return 2

    os.makedirs(outdir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    for nombre, contenido in (("app.css", css), ("app.js", js), ("boot.js", boot)):
        with open(os.path.join(outdir, nombre), "w", encoding="utf-8") as f:
            f.write(contenido)

    # ---- d/: un archivo por borrador, mas el indice de la fila de tabs ----
    # Salen TODOS los de drafts/, no solo el que se esta construyendo: cada tab
    # apunta a un d/<id>.json y ninguno puede faltar. Uno que no valide queda
    # fuera de la fila en vez de romper el build.
    ddir = os.path.join(outdir, "d")
    os.makedirs(ddir, exist_ok=True)
    todos, fuera = [d], []
    if os.path.isdir(DRAFTS):
        for sub_dir in sorted(os.listdir(DRAFTS)):
            otro = os.path.join(DRAFTS, sub_dir, "draft.json")
            if not os.path.exists(otro) or os.path.abspath(otro) == draft_abs:
                continue
            try:
                od, _, _, _ = preparar(otro)
                todos.append(od)
            except Exception as e:
                fuera.append(sub_dir + " (" + str(e)[:70] + ")")
    # Los ajustes del usuario (dias del horario sugerido, si se ofrece agendar el
    # correo) viajan dentro de cada borrador: app.js queda igual para todos.
    ajustes = config.ajustes_pagina(cfg)
    for od in todos:
        od["ajustes"] = ajustes
        with open(os.path.join(ddir, od["draftId"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(od, f, ensure_ascii=False, separators=(",", ":"))
    indice = {"drafts": [{"id": od["draftId"], "tab": od["tab"],
                          "titulo": od["titulo"], "canal": od["canal"]} for od in todos]}
    with open(os.path.join(ddir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False)
    if fuera:
        avisos.append("estos borradores quedaron fuera de la fila de tabs porque no "
                      "validaron: " + "; ".join(fuera))

    if dentro(draft_abs, DRAFTS):
        with open(rev_path, "w", encoding="utf-8") as f:
            f.write(d["rev"] + "\n" + huella + "\n")

    # ---- resumen para el agente ----
    mk = d["marcadores"]
    kb = len(html.encode("utf-8")) / 1024.0
    print("OK  " + out + "   " + ("%.1f" % kb) + " KB  (+ app.css, app.js y d/ en el mismo "
          "directorio)")
    print("    tabs (" + str(len(todos)) + "): " + ", ".join(od["tab"] for od in todos))
    if kb > 22:
        print("AVISO  la cascara pasa de 22 KB, y deberia rondar los 3. Arriba de 25 KB el "
              "`read` del artifact deja de venir inline y vuelve el peaje de tokens. "
              "Algo se colo adentro del HTML: revisa template.html.")
    if not ajustes["envioEmail"] and any(m["canal"] == "email" for m in d["mensajes"]):
        print("    envio de correo APAGADO: el correo termina en Copiar (config.py --mostrar dice por que)")
    print("    tab  " + d["tab"])
    print("    draftId  " + d["draftId"] + "   rev " + d["rev"] + "   canal " + d["canal"] +
          ("   HILO de " + str(len(d["mensajes"])) + " mensajes" if d["hilo"] else ""))
    for msg in d["mensajes"]:
        tot = dict((k, sum(palabras(s["opts"][k]["text"], mk) for s in msg["secciones"])) for k in KEYS)
        rec = sum(0 if s["recomendada"] == "quitar" else palabras(s["opts"][s["recomendada"]]["text"], mk)
                  for s in msg["secciones"])
        if d["hilo"]:
            print("    [" + msg["id"] + "] tab:" + msg["tab"] + "   " + msg["titulo"])
        print("    palabras completa " + str(tot["completa"]) +
              " | ajustada " + str(tot["ajustada"]) +
              " | minima " + str(tot["minima"]) +
              " | recomendado " + str(rec))
        print("    secciones (" + str(len(msg["secciones"])) + "):")
        for i, s in enumerate(msg["secciones"]):
            w = "/".join(str(palabras(s["opts"][k]["text"], mk)) for k in KEYS)
            print("      " + str(i + 1).rjust(2) + ". " + s["id"].ljust(18) +
                  w.rjust(12) + "   rec:" + s["recomendada"] +
                  ("   opcional" if s["opcional"] else ""))
        if msg["adjuntos"]:
            print("    adjuntos: " + ", ".join(a["nombre"] for a in msg["adjuntos"]) +
                  "   (la pagina solo los lista)")
    print("    rutas en la base:")
    for msg in d["mensajes"]:
        base = "drafts/" + d["draftId"] if msg["id"] == SOLO \
            else "drafts/" + d["draftId"] + "/mensajes/" + msg["id"]
        print("      " + base + "   +  " + base + "/secciones/<id>")
    for a in avisos:
        print("AVISO  " + a)
    print("    publicar con:")
    archivos = ['"app.css":"app.css"', '"app.js":"app.js"', '"boot.js":"boot.js"',
                '"d/index.json":"d/index.json"']
    for od in todos:
        n = "d/" + od["draftId"] + ".json"
        archivos.append('"' + n + '":"' + n + '"')
    print('      root:"' + outdir + '"  files:{' + ",".join(archivos) + '}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
