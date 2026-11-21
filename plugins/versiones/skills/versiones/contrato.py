#!/usr/bin/env python3
"""El contrato del draft.json: valida sus campos y calcula huellas y palabras.

Lo usa build.py. Vive aparte para que build.py quede en armar y escribir la pagina.
Un error de contrato levanta Bad con el campo exacto, para que el agente lo arregle
sin abrir el codigo.
"""

import datetime
import hashlib
import json
import re

KEYS = ("completa", "ajustada", "minima")
CANALES = ("email", "whatsapp", "teams", "dm", "formulario")
SEG = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")
MARCADOR = re.compile(r"\{([A-Z0-9_]+)\}")

JOB_MAX_PALABRAS = 10
TAB_MAX_DRAFT = 14       # etiqueta del borrador en la fila de tabs
TAB_MAX_MSG = 12         # etiqueta del mensaje dentro de un hilo
SOLO = "__solo"          # id del mensaje unico: marca las rutas viejas de la base


class Bad(Exception):
    pass


def seg(valor, campo):
    """Valida un id contra la gramatica de segmentos de la base de datos."""
    if not isinstance(valor, str) or not SEG.match(valor) or valor in (".", ".."):
        raise Bad(
            campo + ": debe ser texto de 1 a 200 caracteres, solo letras, digitos "
            "y _ - . ~ : @ +  (es un segmento de ruta de la base de datos). "
            "Recibido: " + repr(valor)
        )
    return valor


def texto(valor, campo):
    if not isinstance(valor, str) or not valor.strip():
        raise Bad(campo + ": falta o esta vacio.")
    return valor


def etiqueta(valor, campo, tope):
    """La etiqueta corta de un tab. Nada que ver con 'titulo', que es largo a proposito."""
    if not isinstance(valor, str) or not valor.strip():
        raise Bad(campo + ": falta. Es la etiqueta del tab, hasta " + str(tope) +
                  " caracteres, y se lee al lado de las otras. El 'titulo' largo se queda "
                  "como esta: alimenta el encabezado y el nombre del artifact.")
    v = " ".join(valor.split())
    if len(v) > tope:
        raise Bad(campo + ": tiene " + str(len(v)) + " caracteres y el tope es " + str(tope) +
                  ". Recibido: " + repr(v) + ". No lo cortes con puntos suspensivos: elegi "
                  "una o dos palabras que lo distingan de los otros tabs.")
    return v


ISO_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
MOTIVO_MAX = 80


def sugerido(valor, campo, avisos):
    """El horario recomendado para mandar el mensaje. Opcional.

    Devuelve el objeto limpio, o None si no viene o ya paso. Que ya haya pasado es
    un aviso y no un error: reconstruir un borrador viejo no puede romperse."""
    if valor is None:
        return None
    if not isinstance(valor, dict):
        raise Bad(campo + ": debe ser un objeto {cuando, motivo}.")
    cuando = valor.get("cuando")
    motivo = valor.get("motivo", "")
    if not isinstance(motivo, str):
        raise Bad(campo + ".motivo: debe ser texto.")
    motivo = " ".join(motivo.split())
    if len(motivo) > MOTIVO_MAX:
        avisos.append(campo + ".motivo: tiene " + str(len(motivo)) + " caracteres (techo " +
                      str(MOTIVO_MAX) + "). Se lee en una linea bajo la hora: cortalo.")
    if cuando == "ahora":
        return {"cuando": "ahora", "motivo": motivo}
    if not isinstance(cuando, str) or not ISO_LOCAL.match(cuando):
        raise Bad(campo + ".cuando: \"ahora\" o fecha y hora local sin zona, formato "
                  "AAAA-MM-DDTHH:MM. Recibido: " + repr(cuando))
    try:
        d = datetime.datetime.fromisoformat(cuando)
    except ValueError:
        raise Bad(campo + ".cuando: no es una fecha real. Recibido: " + repr(cuando))
    if d <= datetime.datetime.now():
        avisos.append(campo + ": " + cuando + " ya paso. La pagina no muestra la fila "
                      "Recomendado. Si todavia hay un buen horario, actualizalo.")
        return None
    return {"cuando": d.strftime("%Y-%m-%dT%H:%M:00"), "motivo": motivo}


def palabras(t, marcadores=None):
    """Cuenta sobre el texto FINAL: cada marcador vale lo que va a salir en el mensaje.
    Misma definicion que usa la pagina, para que los numeros no se contradigan.
    Las marcas de markdown no cuentan como texto."""
    def sub(m):
        mk = (marcadores or {}).get(m.group(1))
        return mk["valor"] if mk else " "
    plano = MARCADOR.sub(sub, t)
    plano = re.sub(r"(\*\*|__|~~|[*_`])", "", plano)
    plano = re.sub(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", " ", plano, flags=re.M)
    return len([w for w in plano.split() if w])


def normalizar(d):
    """Lleva cualquiera de las dos formas a la forma de hilo. Devuelve la lista de mensajes."""
    tiene_msgs = isinstance(d.get("mensajes"), list) and d.get("mensajes")
    tiene_secs = isinstance(d.get("secciones"), list) and d.get("secciones")

    if tiene_msgs and tiene_secs:
        raise Bad("El draft.json trae 'mensajes' y 'secciones' a la vez. "
                  "Usa 'secciones' para un mensaje suelto, o 'mensajes' para un hilo.")
    if not tiene_msgs and not tiene_secs:
        raise Bad("Falta 'secciones' (un mensaje) o 'mensajes' (un hilo).")

    if tiene_secs:
        d["mensajes"] = [{
            "id": SOLO,
            "titulo": d["titulo"],
            "secciones": d.pop("secciones"),
        }]
        d["hilo"] = False
    else:
        d["hilo"] = len(d["mensajes"]) > 1
    return d["mensajes"]


def validar(d):
    avisos = []
    if not isinstance(d, dict):
        raise Bad("El draft.json debe ser un objeto JSON.")

    seg(d.get("draftId"), "draftId")
    texto(d.get("titulo"), "titulo")
    d["tab"] = etiqueta(d.get("tab"), "tab", TAB_MAX_DRAFT)

    canal = d.get("canal")
    if canal not in CANALES:
        raise Bad("canal: debe ser uno de " + ", ".join(CANALES) + ". Recibido: " + repr(canal))

    marcadores = d.get("marcadores") or {}
    if not isinstance(marcadores, dict):
        raise Bad("marcadores: debe ser un objeto {NOMBRE: {valor, vista}}.")
    for nombre, m in marcadores.items():
        if not re.match(r"^[A-Z0-9_]+$", nombre):
            raise Bad("marcadores." + nombre + ": el nombre va en MAYUSCULAS, digitos y _.")
        if not isinstance(m, dict) or not texto(m.get("valor"), "marcadores." + nombre + ".valor"):
            raise Bad("marcadores." + nombre + ": necesita 'valor'.")

    mensajes = normalizar(d)
    usados = set()
    vistos_msg = set()

    for mi, msg in enumerate(mensajes):
        dm = "mensajes[" + str(mi) + "]"
        if not isinstance(msg, dict):
            raise Bad(dm + ": debe ser un objeto.")
        mid = msg.get("id")
        if mid != SOLO:
            seg(mid, dm + ".id")
        if mid in vistos_msg:
            raise Bad(dm + ".id: '" + str(mid) + "' esta repetido. Los ids son unicos.")
        vistos_msg.add(mid)
        texto(msg.get("titulo"), dm + ".titulo")
        # Un mensaje suelto no dibuja la fila de tabs del hilo: hereda la del borrador.
        msg["tab"] = d["tab"] if mid == SOLO \
            else etiqueta(msg.get("tab"), dm + ".tab", TAB_MAX_MSG)

        mcanal = msg.get("canal", canal)
        if mcanal not in CANALES:
            raise Bad(dm + ".canal: debe ser uno de " + ", ".join(CANALES) +
                      ". Recibido: " + repr(mcanal))
        msg["canal"] = mcanal
        msg["destino"] = msg.get("destino", d.get("destino") or {})
        msg["envioSugerido"] = sugerido(msg.get("envioSugerido", d.get("envioSugerido")),
                                        dm + ".envioSugerido" if "envioSugerido" in msg
                                        else "envioSugerido", avisos)
        msg["adjuntos"] = msg.get("adjuntos", d.get("adjuntos") or [])
        if not isinstance(msg["adjuntos"], list):
            raise Bad(dm + ".adjuntos: debe ser una lista.")
        for i, a in enumerate(msg["adjuntos"]):
            if not isinstance(a, dict) or not a.get("nombre"):
                raise Bad(dm + ".adjuntos[" + str(i) + "]: necesita al menos 'nombre'.")

        secciones = msg.get("secciones")
        if not isinstance(secciones, list) or not secciones:
            raise Bad(dm + ".secciones: debe ser una lista con al menos una seccion.")

        vistos = set()
        for i, s in enumerate(secciones):
            donde = dm + ".secciones[" + str(i) + "]"
            if not isinstance(s, dict):
                raise Bad(donde + ": debe ser un objeto.")
            sid = seg(s.get("id"), donde + ".id")
            if sid in vistos:
                raise Bad(donde + ".id: '" + sid + "' esta repetido dentro del mensaje.")
            vistos.add(sid)

            texto(s.get("nombre"), donde + ".nombre")
            job = texto(s.get("job"), donde + ".job (para que existe la seccion, no que dice)")
            nj = len(job.split())
            if nj > JOB_MAX_PALABRAS:
                avisos.append(sid + ": el 'job' tiene " + str(nj) + " palabras (techo " +
                              str(JOB_MAX_PALABRAS) + "). Se lee al lado del nombre de la "
                              "seccion: cortalo a una frase sin verbo auxiliar.")

            opcional = bool(s.get("opcional", False))
            opts = s.get("opts")
            if not isinstance(opts, dict):
                raise Bad(donde + ".opts: debe ser un objeto con las tres variantes.")
            sobran = set(opts) - set(KEYS)
            if sobran:
                raise Bad(donde + ".opts: claves no validas " + repr(sorted(sobran)) +
                          ". Solo " + ", ".join(KEYS) + ".")
            for k in KEYS:
                if k not in opts or not isinstance(opts[k], dict):
                    raise Bad(donde + ".opts." + k + ": falta. Las tres variantes son obligatorias.")
                texto(opts[k].get("text"), donde + ".opts." + k + ".text")
                texto(opts[k].get("note"), donde + ".opts." + k +
                      ".note (el tradeoff de esta variante, no un resumen del texto)")
                for nombre in MARCADOR.findall(opts[k]["text"]):
                    usados.add(nombre)

            rec = s.get("recomendada")
            validas = list(KEYS) + (["quitar"] if opcional else [])
            if rec not in validas:
                raise Bad(donde + ".recomendada: debe ser una de " + ", ".join(validas) +
                          ". Recibido: " + repr(rec))

            w = dict((k, palabras(opts[k]["text"], marcadores)) for k in KEYS)
            if w["ajustada"] > w["completa"]:
                avisos.append(sid + ": 'ajustada' (" + str(w["ajustada"]) + " pal.) es mas larga que "
                              "'completa' (" + str(w["completa"]) + "). Las columnas van de mas a menos.")
            if w["minima"] > w["ajustada"]:
                avisos.append(sid + ": 'minima' (" + str(w["minima"]) + " pal.) es mas larga que "
                              "'ajustada' (" + str(w["ajustada"]) + "). Las columnas van de mas a menos.")
            if w["completa"] == w["minima"]:
                avisos.append(sid + ": las tres variantes miden lo mismo. Si no hay recorte real, "
                              "la seccion no necesita tres tarjetas.")

    faltan = usados - set(marcadores)
    if faltan:
        raise Bad("Los textos usan marcadores sin definir en 'marcadores': " +
                  ", ".join("{" + f + "}" for f in sorted(faltan)))
    sin_usar = set(marcadores) - usados
    for f in sorted(sin_usar):
        avisos.append("marcador {" + f + "} definido pero nunca usado en un texto.")

    return avisos


def hashear(s):
    """Huella de los TEXTOS de una seccion. Si cambia, la edicion guardada quedo vieja.

    Deliberadamente no incluye 'note' ni 'job': retocar el tradeoff no invalida
    una edicion del usuario sobre el texto."""
    crudo = json.dumps(dict((k, s["opts"][k]["text"]) for k in KEYS),
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:12]
