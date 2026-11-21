#!/usr/bin/env python3
"""Decide si un correo de seguimiento todavia hace falta, mirando el hilo de Gmail.

Pregunta unica: despues de la fecha de corte, aparecio algun mensaje nuevo en el hilo?
Si aparecio, el seguimiento sobra y NO hay que mandarlo.

    python3 gate.py --thread 1993f0abc... --desde 2026-09-11T08:00:00
    python3 gate.py --thread 1993f0abc... --desde 1757600000000     # epoch en ms
    python3 gate.py --thread ... --desde ... --esperar-de marta@empresa.com

DOS FUENTES, que se pueden COMBINAR:

    --thread <id>   mira ESE hilo. Para un recordatorio dentro de una
                    conversacion que ya existe.
    --de <quien>    busca en toda la bandeja si llego algo de ese remitente
                    despues del corte. Se repite: --de a@x.com --de b@y.com.

    python3 gate.py --de marta@empresa.com --desde 2026-09-21T08:00:00
    python3 gate.py --thread 1a0eef... --de sam@x.com --de andrea@y.com --desde ...

Con las dos, cancela si CUALQUIERA encuentra algo despues del corte: un mensaje
nuevo en el hilo, o un correo de alguna de esas personas fuera del hilo (un
correo nuevo, otra direccion, una respuesta que mando otra persona).

Cuando usar cual: el primer toque sale a alguien a quien nunca se le escribio,
asi que no hay hilo y va solo con --de. Los toques siguientes caen en el hilo
que abrio el primero: --thread, y ademas --de por cada persona que podria
contestar por fuera.

**Con --de, poner el correo de la persona, no el dominio.** Un dominio atrapa
tambien los newsletters de la empresa, y un newsletter semanal cancelaria el
seguimiento para siempre, en silencio. Solo, sin --thread, el dominio se acepta
para mirar a mano; combinado con --thread es error.

--ignorar-ids <archivo> descarta mensajes por su id de Gmail (uno por linea).
Sirve para que un envio de la propia agenda no cancele el siguiente toque del
mismo hilo. Si el archivo no existe, no se ignora nada: eso cancela de mas,
nunca manda de mas.

Codigos de salida, pensados para que el shell decida con un simple `if`:

    0  no hay respuesta  -> MANDAR
    1  hay respuesta     -> NO mandar
    2  error             -> NO mandar (fail-closed)

Fail-closed a proposito: si la consulta a Gmail falla, no se manda. Mandarle
"no tuve noticias" a alguien que si contesto no se deshace; un recordatorio que
no salio queda en el log y se manda a mano.

En el hilo cuenta CUALQUIER mensaje nuevo, venga de quien venga, incluido el usuario:
si ya volvio a escribir a mano, el recordatorio sobra. Lo unico que no cuenta
son los ids de --ignorar-ids. --esperar-de <email> lo vuelve estricto y solo
cuenta, en el hilo, mensajes de ese remitente (no afecta a --de).

NO filtra autorespuestas de vacaciones a proposito. Un "estoy fuera hasta el 20"
tambien es motivo para no insistir.

Este archivo es independiente de agendar.py de proposito: si algun dia el agendado
se va a la nube, el gate se muda tal cual.
"""

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import time

MANDAR = 0
NO_MANDAR = 1
ERROR = 2

# Reintentos ante fallas de gws (sin red, DNS, token). El 2026-10-06 el envio
# disparo en un despertar corto de la Mac, sin internet, y el gate se rindio al
# primer intento. Ahora espera y prueba de nuevo: 3 intentos en total.
ESPERAS = (60, 180)


def correr(cmd, timeout):
    """subprocess.run con reintentos. Devuelve el ultimo resultado o relanza
    el ultimo TimeoutExpired. Nunca convierte una falla en 'no hay respuesta':
    si los 3 intentos fallan, el que llama sigue en fail-closed."""
    for i in range(len(ESPERAS) + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return r
            err = "gws salio con %d" % r.returncode
        except subprocess.TimeoutExpired:
            if i == len(ESPERAS):
                raise
            err = "gws no contesto en %ds" % timeout
            r = None
        if i < len(ESPERAS):
            print("-- intento %d fallo (%s); reintento en %ds" % (i + 1, err, ESPERAS[i]),
                  file=sys.stderr, flush=True)
            time.sleep(ESPERAS[i])
    return r


def corte_ms(texto):
    """ISO local (o epoch en ms) -> epoch en milisegundos."""
    t = texto.strip()
    if re.fullmatch(r"\d{11,}", t):        # ya viene en ms
        return int(t)
    if re.fullmatch(r"\d{9,10}", t):       # venia en segundos
        return int(t) * 1000
    return int(datetime.datetime.fromisoformat(t).timestamp() * 1000)


def traer_hilo(gws, thread, timeout):
    params = json.dumps({"userId": "me", "id": thread,
                         "format": "metadata", "metadataHeaders": ["From", "Subject"]})
    r = correr([gws, "gmail", "users", "threads", "get", "--params", params], timeout)
    if r.returncode != 0:
        raise RuntimeError("gws salio con %d: %s" % (r.returncode,
                                                     (r.stderr or r.stdout).strip()[:400]))
    return _json(r.stdout)


def _json(salida):
    """gws puede anteponer lineas de aviso: quedarse del primer '{' en adelante."""
    salida = (salida or "").strip()
    if not salida:
        raise RuntimeError("gws no devolvio nada")
    i = salida.find("{")
    if i < 0:
        raise RuntimeError("la salida de gws no es JSON: " + salida[:200])
    return json.loads(salida[i:])


def buscar_de(gws, quien, corte, timeout, ignorar=frozenset()):
    """Mensajes de `quien` posteriores al corte. Devuelve [(epoch_ms, From, Subject)].

    Dos llamadas y no una: Gmail interpreta `after:` por dia en varios casos, asi
    que la busqueda trae de mas y despues se confirma cada candidato con su
    internalDate exacto. Con maxResults 10 el costo maximo son 11 llamadas."""
    desde_s = int(corte // 1000)
    q = "from:%s after:%d" % (quien, desde_s)
    params = json.dumps({"userId": "me", "q": q, "maxResults": 10})
    r = correr([gws, "gmail", "users", "messages", "list", "--params", params], timeout)
    if r.returncode != 0:
        raise RuntimeError("gws salio con %d: %s" % (r.returncode,
                                                     (r.stderr or r.stdout).strip()[:400]))
    d = _json(r.stdout)
    ids = [m.get("id") for m in (d.get("messages") or [])
           if m.get("id") and m.get("id") not in ignorar]
    if not ids:
        return []
    nuevos = []
    for mid in ids:
        pm = json.dumps({"userId": "me", "id": mid, "format": "metadata",
                         "metadataHeaders": ["From", "Subject"]})
        rr = correr([gws, "gmail", "users", "messages", "get", "--params", pm], timeout)
        if rr.returncode != 0:
            raise RuntimeError("gws salio con %d al leer %s" % (rr.returncode, mid))
        m = _json(rr.stdout)
        try:
            cuando = int(m.get("internalDate", 0))
        except (TypeError, ValueError):
            continue
        if cuando > corte:
            nuevos.append((cuando, cabecera(m, "From"), cabecera(m, "Subject")))
    nuevos.sort()
    return nuevos


def cabecera(msg, nombre):
    for h in (msg.get("payload") or {}).get("headers") or []:
        if h.get("name", "").lower() == nombre.lower():
            return h.get("value", "")
    return ""


def leer_ignorar(ruta):
    """Ids de Gmail a descartar, uno por linea. Archivo ausente = ninguno."""
    if not ruta:
        return frozenset()
    try:
        with open(ruta, encoding="utf-8") as f:
            return frozenset(l.strip() for l in f
                             if l.strip() and not l.lstrip().startswith("#"))
    except FileNotFoundError:
        return frozenset()


def fecha(ms):
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M")


def mirar_hilo(gws, thread, corte, esperar_de, ignorar, timeout):
    """Devuelve (nuevos, total, ignorados). nuevos = [(epoch_ms, From)]."""
    hilo = traer_hilo(gws, thread, timeout)
    mensajes = hilo.get("messages")
    if not isinstance(mensajes, list) or not mensajes:
        raise RuntimeError("el hilo %s no trajo mensajes" % thread)
    nuevos, ignorados = [], 0
    for m in mensajes:
        try:
            cuando = int(m.get("internalDate", 0))
        except (TypeError, ValueError):
            continue
        if cuando <= corte:
            continue
        if m.get("id") in ignorar:
            ignorados += 1
            continue
        de = cabecera(m, "From")
        if esperar_de and esperar_de.lower() not in de.lower():
            continue
        nuevos.append((cuando, de))
    nuevos.sort()
    return nuevos, len(mensajes), ignorados


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thread", help="threadId de Gmail: mira ese hilo")
    ap.add_argument("--de", dest="de", action="append", default=[],
                    help="busca en la bandeja correo de esta persona despues del corte. "
                         "Se repite. Combinable con --thread")
    ap.add_argument("--desde", required=True,
                    help="fecha de corte: ISO local (2026-09-11T08:00:00) o epoch en ms")
    ap.add_argument("--esperar-de", dest="esperar_de",
                    help="modo estricto del hilo: solo cuenta mensajes de este remitente")
    ap.add_argument("--ignorar-ids", dest="ignorar_ids",
                    help="archivo con ids de Gmail a descartar, uno por linea "
                         "(los envios de la propia agenda)")
    ap.add_argument("--gws", help="ruta al binario gws (por si el PATH viene pelado)")
    ap.add_argument("--timeout", type=int, default=60, help="segundos de espera a gws")
    a = ap.parse_args()

    if not a.thread and not a.de:
        print("ERROR: pasa --thread <id>, uno o mas --de <correo>, o los dos.",
              file=sys.stderr)
        return ERROR
    if a.esperar_de and not a.thread:
        print("ERROR: --esperar-de es del hilo. En modo --de, el remitente "
              "ya es el filtro.", file=sys.stderr)
        return ERROR
    if a.thread:
        dominios = [q for q in a.de if "@" not in q]
        if dominios:
            print("ERROR: con --thread, --de va con el correo de la persona, no un "
                  "dominio (%s): un newsletter cancelaria el envio." % ", ".join(dominios),
                  file=sys.stderr)
            return ERROR

    gws = a.gws or shutil.which("gws") or "/opt/homebrew/bin/gws"

    try:
        corte = corte_ms(a.desde)
    except ValueError:
        print("ERROR: --desde debe ser ISO local o epoch en ms, no " + a.desde, file=sys.stderr)
        return ERROR

    try:
        ignorar = leer_ignorar(a.ignorar_ids)
    except Exception as e:                                  # noqa: BLE001
        print("ERROR leyendo %s: %s\nNo se manda (fail-closed)." % (a.ignorar_ids, e),
              file=sys.stderr)
        return ERROR

    corte_txt = fecha(corte)
    partes = []

    # Primero el hilo: es una sola llamada y es donde suele estar la respuesta.
    if a.thread:
        try:
            nuevos, total, ignorados = mirar_hilo(gws, a.thread, corte, a.esperar_de,
                                                  ignorar, a.timeout)
        except subprocess.TimeoutExpired:
            print("ERROR: gws no contesto en %ds. No se manda (fail-closed)." % a.timeout,
                  file=sys.stderr)
            return ERROR
        except Exception as e:                              # noqa: BLE001
            print("ERROR consultando el hilo: %s\nNo se manda (fail-closed)." % e,
                  file=sys.stderr)
            return ERROR
        nota = "" if not ignorados else " (%d envio(s) de la agenda ignorado(s))" % ignorados
        if nuevos:
            print("HAY RESPUESTA  %d mensaje(s) en el hilo despues del %s%s. Ultimo: %s de %s"
                  % (len(nuevos), corte_txt, nota, fecha(nuevos[-1][0]),
                     nuevos[-1][1] or "(sin From)"))
            return NO_MANDAR
        partes.append("%d mensaje(s) en el hilo, ninguno despues del %s%s%s"
                      % (total, corte_txt,
                         "" if not a.esperar_de else " de " + a.esperar_de, nota))

    for quien in a.de:
        try:
            nuevos = buscar_de(gws, quien, corte, a.timeout, ignorar)
        except subprocess.TimeoutExpired:
            print("ERROR: gws no contesto en %ds. No se manda (fail-closed)." % a.timeout,
                  file=sys.stderr)
            return ERROR
        except Exception as e:                              # noqa: BLE001
            print("ERROR buscando correo de %s: %s\nNo se manda (fail-closed)." % (quien, e),
                  file=sys.stderr)
            return ERROR
        if nuevos:
            print("HAY RESPUESTA  %d mensaje(s) de %s despues del %s. Ultimo: %s  %s"
                  % (len(nuevos), quien, corte_txt, fecha(nuevos[-1][0]),
                     (nuevos[-1][2] or "(sin asunto)")[:60]))
            return NO_MANDAR
        partes.append("nada de %s despues del %s" % (quien, corte_txt))

    print("NO HAY RESPUESTA  " + "; ".join(partes) + ". Se manda.")
    return MANDAR


if __name__ == "__main__":
    sys.exit(main())
