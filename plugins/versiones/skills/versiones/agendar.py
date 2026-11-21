#!/usr/bin/env python3
"""Agenda el envio de un correo a una hora exacta, con launchd.

No es una tarea de Claude: es un temporizador del sistema. No gasta tokens ni
necesita que la sesion exista.

OJO CON LA MAC DORMIDA: launchd no despierta la maquina. Si a la hora programada
la Mac esta cerrada o apagada, el trabajo corre en cuanto despierta o arranca
(man launchd.plist, StartCalendarInterval). Para garantizar la hora exacta hace
falta 'sudo pmset schedule wake', que pide la contrasena del usuario.

    python3 agendar.py crear --eml m.eml --cuando 2026-09-11T08:00:00 --titulo "Correo a Marta"
    python3 agendar.py crear ... --thread 1993f0a... --dry     # dry: escribe el log, no envia
    python3 agendar.py crear ... --thread 1993f0a... --mandar-igual   # apaga el gate

CON --thread, EL GATE VIENE ENCENDIDO: a la hora, gate.py mira el hilo y si alguien
escribio despues de la fecha de corte (--desde, por defecto el momento de agendar), el
correo NO sale y queda como cancelado-por-respuesta. --mandar-igual lo apaga.

SIN HILO TAMBIEN HAY GATE: --gate-de <correo de la persona> enciende el gate en modo
busqueda. Es para el PRIMER contacto, donde el hilo todavia no existe: a la hora,
gate.py pregunta si llego algo de esa persona despues del corte y si llego, no manda.
    python3 agendar.py crear ... --gate-de marta@empresa.com
Poner el correo de la persona, no el dominio: un newsletter de la empresa cancelaria
el envio en silencio, y para siempre. Un dominio da error.

LOS DOS SE COMBINAN: --thread mas uno o mas --gate-de. Cancela si alguien escribe en
el hilo O si alguna de esas personas manda correo por fuera (un correo nuevo, otra
direccion, una respuesta que mando un colega). Es lo que va en un toque 2 o 3:
    python3 agendar.py crear ... --thread 1a0eef... --gate-de sam@x.com --gate-de andrea@y.com

LA LISTA DE PERSONAS SE ARMA SOLA. Con el gate encendido, crear suma a --gate-de los
To y Cc del .eml y, si hay --thread, todos los que aparecen en el hilo (From, To, Cc).
Quedan fuera el remitente del .eml (el usuario) y las casillas noreply. Si leer el hilo
falla, avisa y sigue con lo que tiene. --gate-de agrega a mano a quien no aparece en
ninguno de los dos lados: un invitado de la entrevista, un colega del destinatario.

LOS ENVIOS DE LA AGENDA NO CANCELAN EL TOQUE SIGUIENTE. Cada envio deja su id de Gmail
en agenda/<id>/GMAIL_ID. A la hora, el gate recibe la lista de todos (`enviados`) y
los descarta. Un mensaje que el usuario escribe a mano en el hilo si cancela.
    python3 agendar.py enviados      # ids de Gmail de todo lo que mando la agenda
    python3 agendar.py listar
    python3 agendar.py cancelar <id>
    python3 agendar.py estado <id>

El envio usa gws (CLI de Google Workspace), con la ruta de config.json o del PATH:
    gws gmail users messages send --params '{"userId":"me"}' [--json threadId] --upload ./mensaje.eml
con el .eml dentro del directorio de trabajo, que es lo que --upload exige.

DONDE VIVE CADA COSA. agenda/ esta en la carpeta de datos del usuario (config.py), y el
label de launchd es <launchd_prefijo>.<id>. crear copia gate.py, config.py y este archivo
adentro de agenda/<id>/: la carpeta del plugin cambia de ruta en cada actualizacion, y un
envio agendado antes tiene que encontrar sus scripts igual a la hora de salir.
"""

import argparse
import datetime
import email.parser
import email.utils
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402

CFG = config.cargar()
AGENDA = config.ruta("agenda")
PLISTS = os.path.expanduser("~/Library/LaunchAgents")
UID = os.getuid()
GATE = os.path.join(AQUI, "gate.py")
YO = os.path.abspath(__file__)
NOMBRE = config.nombre(CFG)


def label(ident):
    return config.label(CFG, ident)

SH = r"""#!/bin/zsh
# Generado por agendar.py. Se borra solo al terminar.
DIR="__DIR__"
LOG="$DIR/envio.log"
TITULO="__TITULO__"
LABEL="__LABEL__"
PLIST="__PLIST__"
GWS="__GWS__"
# launchd no hereda el entorno de la terminal: la carpeta de datos va fija.
export VERSIONES_DATOS="__DATOS__"

limpiar() {
  rm -f "$PLIST"
  /bin/launchctl bootout gui/__UID__/$LABEL 2>/dev/null
}
avisar() {
  osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null
}

cd "$DIR" || exit 1
echo "== $(date -Iseconds) disparo" >> "$LOG"
# Que la Mac no se duerma a mitad del envio (dispara en despertares cortos).
/usr/bin/caffeinate -i -w $$ &
PY="__PYTHON__"
[ -x "$PY" ] || PY="$(command -v python3)" || PY=/usr/bin/python3

# Gate de no-respuesta: si ya escribieron despues del corte, esto sobra.
if [ "__GATE__" = "1" ]; then
  echo "-- gate: __GATE_QUE__ desde __DESDE__" >> "$LOG"
  # Los envios de la propia agenda no son respuesta. Si la lista falla, queda
  # vacia: el gate los cuenta y cancela de mas, nunca manda de mas.
  "$PY" "__AGENDAR_PY__" enviados > "$DIR/ignorar.txt" 2>> "$LOG" || : > "$DIR/ignorar.txt"
  "$PY" "__GATE_PY__" __GATE_ARGS__ --desde "__DESDE__" \
    --ignorar-ids "$DIR/ignorar.txt" --gws "$GWS" __ESPERAR__ >> "$LOG" 2>&1
  G=$?
  if [ $G -eq 1 ]; then
    echo "cancelado-por-respuesta $(date -Iseconds)" > "$DIR/ESTADO"
    avisar "Correo cancelado: ya contestaron" "$TITULO"
    limpiar
    exit 0
  fi
  if [ $G -ne 0 ]; then
    echo "error-gate $(date -Iseconds)" > "$DIR/ESTADO"
    avisar "No pude revisar el hilo" "No salio: $TITULO. Mira envio.log"
    limpiar
    exit 0
  fi
fi

if [ "__DRY__" = "1" ]; then
  echo "DRY RUN: no se envia nada" >> "$LOG"
  CODE=0
else
  if [ -n "__THREAD__" ]; then
    "$GWS" gmail users messages send --params '{"userId":"me"}' \
      --json '{"threadId":"__THREAD__"}' --upload ./mensaje.eml > "$DIR/send.out" 2>&1
  else
    "$GWS" gmail users messages send --params '{"userId":"me"}' \
      --upload ./mensaje.eml > "$DIR/send.out" 2>&1
  fi
  CODE=$?
  cat "$DIR/send.out" >> "$LOG"
  # El id de Gmail de lo que salio: el gate del toque siguiente lo descarta.
  [ $CODE -eq 0 ] && "$PY" -c 'import json,sys
t=open(sys.argv[1]).read(); print(json.loads(t[t.index("{"):])["id"])' \
    "$DIR/send.out" > "$DIR/GMAIL_ID" 2>> "$LOG"
  rm -f "$DIR/send.out"
fi

echo "exit=$CODE" >> "$LOG"
if [ $CODE -eq 0 ]; then
  echo "enviado $(date -Iseconds)" > "$DIR/ESTADO"
  avisar "Correo enviado" "$TITULO"
else
  echo "error $(date -Iseconds)" > "$DIR/ESTADO"
  avisar "Fallo el envio programado" "No salio. Mira envio.log"
fi

limpiar
"""

def despierta(cuando):
    """La Mac va a estar despierta a esa hora? Lee 'pmset -g sched', que no pide sudo.

    Devuelve (True, motivo) si algo la despierta antes, (False, "") si no, y
    (None, "") si no se pudo saber. Mira dos listas distintas de pmset: los
    despertares que se repiten todos los dias y los programados una sola vez.
    """
    try:
        r = subprocess.run(["/usr/bin/pmset", "-g", "sched"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None, ""
    except Exception:                                       # noqa: BLE001
        return None, ""

    def hhmm(txt):
        m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)?", txt.strip(), re.I)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        ap = (m.group(3) or "").upper()
        if ap == "PM" and h != 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        return h * 60 + mi

    minuto = cuando.hour * 60 + cuando.minute
    finde = cuando.weekday() >= 5

    for linea in r.stdout.splitlines():
        t = linea.strip()
        # Repetido: "wakepoweron at 7:55AM every day"
        m = re.match(r"(wake\w*|poweron)\s+at\s+(\d{1,2}:\d{2}\s*[AP]?M?)\s+(.*)$", t, re.I)
        if m and "wake" in m.group(1).lower():
            hm = hhmm(m.group(2))
            dias = m.group(3).strip().lower()
            aplica = (dias.startswith("every day")
                      or (dias.startswith("weekdays") and not finde)
                      or (dias.startswith("weekends") and finde))
            if hm is not None and aplica and hm <= minuto:
                return True, "pmset la despierta a las %02d:%02d %s" % (hm // 60, hm % 60, dias)
            continue
        # Puntual: "[0]  wake at 09/15/2026 06:25:00". Los de 'com.apple' son del
        # sistema: van y vienen solos, no se puede contar con ellos.
        m = re.search(r"wake\w*\s+at\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})", t, re.I)
        if m and "by 'com.apple" not in t:
            try:
                d = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%m/%d/%Y %H:%M:%S")
            except ValueError:
                continue
            if d <= cuando and (cuando - d).total_seconds() < 6 * 3600:
                return True, "hay un despertar programado para " + d.strftime("%d/%m %H:%M")
    return False, ""


NO_PERSONA = re.compile(r"no-?reply|mailer-daemon|notifications?@|calendar-notification", re.I)


def correos(valores):
    return [d.lower() for _, d in email.utils.getaddresses([v for v in valores if v])
            if "@" in d]


def personas_auto(eml, thread, gws):
    """Quien podria contestar: To y Cc del .eml, mas todos los del hilo.
    Devuelve (lista, aviso). Sin el remitente del .eml ni casillas noreply."""
    with open(eml, "rb") as f:
        h = email.parser.BytesHeaderParser().parse(f)
    yo = set(correos(h.get_all("From") or []))
    lista = correos((h.get_all("To") or []) + (h.get_all("Cc") or []))
    aviso = ""
    if thread:
        params = json.dumps({"userId": "me", "id": thread, "format": "metadata",
                             "metadataHeaders": ["From", "To", "Cc"]})
        try:
            r = subprocess.run([gws, "gmail", "users", "threads", "get", "--params", params],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip()[:200])
            t = r.stdout
            hilo = json.loads(t[t.index("{"):])
            for m in hilo.get("messages") or []:
                lista += correos(x.get("value", "") for x in
                                 (m.get("payload") or {}).get("headers") or []
                                 if x.get("name", "").lower() in ("from", "to", "cc"))
        except Exception as e:                              # noqa: BLE001
            aviso = "no pude leer los participantes del hilo (%s)" % e
    vistos, fuera = [], yo
    for c in lista:
        if c not in fuera and c not in vistos and not NO_PERSONA.search(c):
            vistos.append(c)
    return vistos, aviso


def slug(t):
    return re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()[:40] or "envio"


def rutas(ident):
    dirs = os.path.join(AGENDA, ident)
    return dirs, os.path.join(PLISTS, label(ident) + ".plist")


def crear(a):
    if not os.path.exists(a.eml):
        print("ERROR: no existe " + a.eml, file=sys.stderr); return 2
    try:
        cuando = datetime.datetime.fromisoformat(a.cuando)
    except ValueError:
        print("ERROR: --cuando debe ser ISO local, ej 2026-09-11T08:00:00", file=sys.stderr); return 2
    ahora = datetime.datetime.now()
    if cuando <= ahora:
        print("ERROR: esa hora ya paso (" + cuando.isoformat() + " <= " + ahora.isoformat() + ")",
              file=sys.stderr); return 2
    dominios = [q for q in a.gate_de if "@" not in q]
    if dominios:
        print("ERROR: --gate-de va con el correo de la persona, no un dominio (%s): "
              "un newsletter cancelaria el envio." % ", ".join(dominios),
              file=sys.stderr); return 2
    # Con hilo mira ese hilo; sin hilo, con --gate-de, busca correo de esa persona.
    gate = bool(a.thread or a.gate_de) and not a.mandar_igual
    if a.esperar_de and not (a.thread and gate):
        print("ERROR: --esperar-de necesita --thread y sin --mandar-igual", file=sys.stderr); return 2
    desde = a.desde or ahora.isoformat(timespec="seconds")
    if gate and not os.path.exists(GATE):
        print("ERROR: falta " + GATE, file=sys.stderr); return 2

    gws = config.gws_binario(CFG)
    if not gws:
        print("ERROR: no encuentro gws (ni en config.json, ni en el PATH, ni en "
              + config.GWS_RESPALDO + "). Sin gws no hay envio programado.", file=sys.stderr)
        return 2
    if gate:
        auto, aviso = personas_auto(a.eml, a.thread, gws)
        if aviso:
            print("AVISO  " + aviso + ". El gate sigue con los destinatarios del .eml"
                  " y los --gate-de.")
        a.gate_de = list(dict.fromkeys([q.lower() for q in a.gate_de] + auto))

    hay, motivo = despierta(cuando)
    if hay:
        print("DESPERTAR  ok: " + motivo + ", asi que sale a la hora exacta.")
    else:
        antes = cuando - datetime.timedelta(minutes=5)
        print("AVISO  a esa hora la Mac puede estar dormida"
              + ("." if hay is False else " (no se pudo leer pmset).")
              + " launchd NO la despierta: si esta\n"
              "       cerrada, el correo sale recien cuando " + NOMBRE + " la abra. Para clavar la hora,\n"
              "       que " + NOMBRE + " corra esto (pide su contrasena):\n\n"
              '       sudo pmset schedule wake "' + antes.strftime("%m/%d/%y %H:%M:%S") + '"\n')

    ident = cuando.strftime("%Y%m%d-%H%M") + "-" + slug(a.titulo)
    dirs, plist = rutas(ident)
    os.makedirs(dirs, exist_ok=True)
    shutil.copy2(a.eml, os.path.join(dirs, "mensaje.eml"))
    for script in ("gate.py", "config.py", "agendar.py"):
        shutil.copy2(os.path.join(AQUI, script), os.path.join(dirs, script))

    sh = os.path.join(dirs, "enviar.sh")
    cuerpo = (SH.replace("__DIR__", dirs).replace("__TITULO__", a.titulo.replace('"', "'"))
                .replace("__LABEL__", label(ident)).replace("__PLIST__", plist)
                .replace("__DATOS__", config.carpeta())
                .replace("__GWS__", gws).replace("__THREAD__", a.thread or "")
                .replace("__DRY__", "1" if a.dry else "0").replace("__UID__", str(UID))
                .replace("__GATE__", "1" if gate else "0").replace("__GATE_PY__", os.path.join(dirs, "gate.py"))
                .replace("__AGENDAR_PY__", os.path.join(dirs, "agendar.py"))
                .replace("__GATE_ARGS__", " ".join(
                    ([('--thread "%s"' % a.thread)] if a.thread else [])
                    + ['--de "%s"' % q for q in a.gate_de]))
                .replace("__GATE_QUE__", " y ".join(
                    (["mirando el hilo " + a.thread] if a.thread else [])
                    + (["buscando correo de " + ", ".join(a.gate_de)] if a.gate_de else [])))
                .replace("__PYTHON__", sys.executable or "/usr/bin/python3")
                .replace("__DESDE__", desde)
                .replace("__ESPERAR__", ('--esperar-de "%s"' % a.esperar_de) if a.esperar_de else ""))
    with open(sh, "w", encoding="utf-8") as f:
        f.write(cuerpo)
    os.chmod(sh, 0o755)

    with open(os.path.join(dirs, "envio.json"), "w", encoding="utf-8") as f:
        json.dump({"id": ident, "titulo": a.titulo, "cuando": cuando.isoformat(),
                   "thread": a.thread, "dry": bool(a.dry), "draftId": a.draft or "",
                   "gate": gate, "gateDe": a.gate_de, "desde": desde if gate else "",
                   "esperarDe": a.esperar_de or "",
                   "creado": ahora.isoformat()}, f, ensure_ascii=False, indent=2)

    with open(plist, "wb") as f:
        plistlib.dump({
            "Label": label(ident),
            "ProgramArguments": ["/bin/zsh", sh],
            "StartCalendarInterval": {"Month": cuando.month, "Day": cuando.day,
                                      "Hour": cuando.hour, "Minute": cuando.minute},
            "StandardErrorPath": os.path.join(dirs, "launchd.err"),
            "RunAtLoad": False,
        }, f)

    subprocess.run(["/bin/launchctl", "bootout", "gui/%d/%s" % (UID, label(ident))],
                   capture_output=True)
    r = subprocess.run(["/bin/launchctl", "bootstrap", "gui/%d" % UID, plist],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ERROR al cargar en launchd: " + (r.stderr or r.stdout).strip(), file=sys.stderr)
        return 1

    print("AGENDADO  " + ident)
    print("    cuando   " + cuando.strftime("%A %d/%m/%Y %H:%M") + ("   (DRY RUN)" if a.dry else ""))
    print("    eml      " + os.path.join(dirs, "mensaje.eml"))
    print("    log      " + os.path.join(dirs, "envio.log"))
    if gate and a.thread:
        print("    gate     solo sale si NADIE escribe en el hilo despues del "
              + desde + ("" if not a.esperar_de else "   (solo cuenta " + a.esperar_de + ")"))
        print("             (los envios de la propia agenda no cuentan)")
    if gate and a.gate_de:
        print("    gate     solo sale si " + ", ".join(a.gate_de)
              + " NO escribe" + (" por fuera" if a.thread else "") + " despues del " + desde)
    elif a.thread or a.gate_de:
        print("    gate     APAGADO: sale igual aunque contesten (--mandar-igual)")
    print("    cancelar python3 agendar.py cancelar " + ident)
    return 0


def ids_enviados():
    """Ids de Gmail de todo lo que mando enviar.sh. Lee agenda/<id>/GMAIL_ID; si no
    esta (envios agendados antes de que existiera), saca el id de la respuesta de
    gws en envio.log. Solo cuenta logs de un disparo de launchd: un envio manual
    desde la sesion no es de la agenda y si tiene que frenar un toque."""
    ids = set()
    if not os.path.isdir(AGENDA):
        return ids
    dec = json.JSONDecoder()
    for ident in sorted(os.listdir(AGENDA)):
        d = os.path.join(AGENDA, ident)
        g = os.path.join(d, "GMAIL_ID")
        if os.path.exists(g):
            v = open(g, encoding="utf-8").read().strip()
            if v:
                ids.add(v)
                continue
        log = os.path.join(d, "envio.log")
        if not os.path.exists(log):
            continue
        t = open(log, encoding="utf-8", errors="replace").read()
        if " disparo" not in t:
            continue
        i = t.find("{")
        while i >= 0:
            try:
                obj, fin = dec.raw_decode(t, i)
            except ValueError:
                i = t.find("{", i + 1)
                continue
            if isinstance(obj, dict) and obj.get("id") and "SENT" in (obj.get("labelIds") or []):
                ids.add(obj["id"])
            i = t.find("{", fin)
    return ids


def enviados(a):
    for v in sorted(ids_enviados()):
        print(v)
    return 0


def listar(a):
    if not os.path.isdir(AGENDA):
        print("No hay nada agendado."); return 0
    filas = []
    for ident in sorted(os.listdir(AGENDA)):
        d = os.path.join(AGENDA, ident)
        meta = os.path.join(d, "envio.json")
        if not os.path.exists(meta):
            continue
        with open(meta, encoding="utf-8") as f:
            m = json.load(f)
        est = "pendiente" + (" (con gate)" if m.get("gate") else "")
        pe = os.path.join(d, "ESTADO")
        if os.path.exists(pe):
            crudo = open(pe, encoding="utf-8").read().strip().split()
            est = crudo[0] if crudo else "?"
            if len(crudo) > 1 and "T" in crudo[1]:
                est += " " + crudo[1][5:16].replace("T", " ")
        elif not os.path.exists(rutas(ident)[1]):
            est = "sin plist (cancelado?)"
        filas.append((ident, m.get("cuando", "?"), est, m.get("titulo", "")))
    if not filas:
        print("No hay nada agendado."); return 0
    print("id".ljust(34) + "cuando".ljust(21) + "estado".ljust(38) + "titulo")
    for f in filas:
        print(f[0].ljust(34) + f[1].ljust(21) + f[2][:36].ljust(38) + f[3])
    return 0


def cancelar(a):
    dirs, plist = rutas(a.id)
    if not os.path.isdir(dirs):
        print("ERROR: no existe el envio " + a.id, file=sys.stderr); return 2
    subprocess.run(["/bin/launchctl", "bootout", "gui/%d/%s" % (UID, label(a.id))],
                   capture_output=True)
    if os.path.exists(plist):
        os.remove(plist)
    with open(os.path.join(dirs, "ESTADO"), "w", encoding="utf-8") as f:
        f.write("cancelado " + datetime.datetime.now().isoformat())
    print("CANCELADO  " + a.id + "   (el .eml queda en " + dirs + ")")
    return 0


def estado(a):
    dirs, plist = rutas(a.id)
    if not os.path.isdir(dirs):
        print("ERROR: no existe el envio " + a.id, file=sys.stderr); return 2
    for nombre in ("envio.json", "ESTADO", "envio.log", "launchd.err"):
        ruta = os.path.join(dirs, nombre)
        if os.path.exists(ruta):
            print("--- " + nombre + " ---")
            print(open(ruta, encoding="utf-8").read().strip() or "(vacio)")
    r = subprocess.run(["/bin/launchctl", "print", "gui/%d/%s" % (UID, label(a.id))],
                       capture_output=True, text=True)
    print("--- launchd ---")
    print("cargado" if r.returncode == 0 else "no cargado (ya corrio o se cancelo)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crear", help="agenda un .eml a una hora exacta")
    c.add_argument("--eml", required=True)
    c.add_argument("--cuando", required=True, help="ISO local, ej 2026-09-11T08:00:00")
    c.add_argument("--titulo", required=True, help="para el log y la notificacion")
    c.add_argument("--thread", help="threadId de Gmail, para que hile del lado del usuario")
    c.add_argument("--draft", help="draftId del borrador de /versiones, para rastrearlo")
    c.add_argument("--gate-de", dest="gate_de", action="append", default=[],
                   help="correo de una persona que podria contestar (nunca un dominio). "
                        "Se repite. Solo: gate de primer contacto. Con --thread: "
                        "ademas del hilo, mira si escribio por fuera")
    c.add_argument("--mandar-igual", dest="mandar_igual", action="store_true",
                   help="apaga el gate: manda aunque hayan contestado el hilo")
    c.add_argument("--esperar-de", dest="esperar_de",
                   help="gate estricto: solo cancela si escribe ESTE remitente")
    c.add_argument("--desde", help="fecha de corte del gate (ISO local). Por defecto, ahora")
    c.add_argument("--dry", action="store_true", help="no envia: solo deja el log")
    c.set_defaults(fn=crear)

    l = sub.add_parser("listar", help="que hay agendado"); l.set_defaults(fn=listar)
    x = sub.add_parser("cancelar", help="baja un envio agendado")
    x.add_argument("id"); x.set_defaults(fn=cancelar)
    v = sub.add_parser("enviados", help="ids de Gmail de lo que mando la agenda")
    v.set_defaults(fn=enviados)
    e = sub.add_parser("estado", help="log y estado de un envio")
    e.add_argument("id"); e.set_defaults(fn=estado)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
