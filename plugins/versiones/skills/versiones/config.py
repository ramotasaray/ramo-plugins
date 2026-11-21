#!/usr/bin/env python3
"""Ajustes y carpeta de datos del usuario de /versiones.

Todo lo personal (nombre, correos, zona horaria, rutas, integraciones) vive en
config.json, en la carpeta de datos del usuario, nunca en el codigo: el plugin lo
comparten varias personas y su carpeta se reemplaza entera al actualizarse.

Carpeta de datos: ~/.claude/versiones-datos, o la que diga la variable de entorno
VERSIONES_DATOS. Ahi viven drafts/, agenda/, registro.jsonl, artifact.txt,
config.json, gws-estado.json y, opcional, preferencias.md.

    python3 config.py --mostrar         carpeta, ajustes, si gws esta listo (prueba gws)
    python3 config.py --crear --nombre Marta --correo marta@empresa.com --envio-email si
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import unicodedata

CARPETA_DEFECTO = "~/.claude/versiones-datos"
GWS_RESPALDO = "/opt/homebrew/bin/gws"   # Homebrew en Mac con Apple Silicon
DIAS = ["domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]

# Cada clave es opcional. Lo que falta en config.json toma este valor.
DEFECTOS = {
    "nombre": None,               # como llamar al usuario; None = "el usuario"
    "correos_propios": [],        # sus direcciones: quedan fuera de "responder a todos"
    "zona_horaria": None,         # IANA; None = la del sistema
    "gws": None,                  # ruta al binario; None = PATH y despues GWS_RESPALDO
    "launchd_prefijo": "com.versiones",
    "envio_email": True,          # False: el correo termina en "Copiar", sin agendar
    "dias_envio": ["lunes", "martes", "miercoles", "jueves", "viernes"],
    "ventana_despierta": None,    # {"desde": "06:00", "hasta": "09:00"} si la Mac se despierta sola
    "reglas_gmail": None,         # ruta a un .md con reglas propias para armar correos
    "extras": {},                 # integraciones personales, ver SKILL.md
}


def carpeta():
    return os.path.abspath(os.path.expanduser(os.environ.get("VERSIONES_DATOS") or CARPETA_DEFECTO))


def ruta(*partes):
    return os.path.join(carpeta(), *partes)


def asegurar():
    """Crea la carpeta de datos y sus subcarpetas si faltan. Devuelve la ruta."""
    base = carpeta()
    for sub in ("drafts", "agenda"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return base


def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def dias_numeros(dias):
    """Nombres de dia -> numeros de Date.getDay() de JavaScript (0 = domingo).
    Acepta numeros 0-6 tal cual y nombres con o sin tilde, en cualquier caja."""
    out = []
    for d in dias or []:
        if isinstance(d, int) and 0 <= d <= 6:
            n = d
        elif isinstance(d, str) and _sin_tildes(d.strip().lower()) in DIAS:
            n = DIAS.index(_sin_tildes(d.strip().lower()))
        else:
            raise ValueError("dias_envio: no entiendo %r (usar lunes, martes... o 0-6)" % (d,))
        if n not in out:
            out.append(n)
    return sorted(out)


def _minutos(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def ventana_minutos(v):
    """{"desde": "06:00", "hasta": "09:00"} -> [360, 540], o None."""
    if not v:
        return None
    return [_minutos(v["desde"]), _minutos(v["hasta"])]


def zona_sistema():
    try:
        destino = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in destino:
            return destino.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return None


def cargar():
    """config.json mezclado con DEFECTOS. Un valor con tipo equivocado vuelve al defecto
    y deja un aviso en "_avisos", para que un error de tipeo no rompa la skill."""
    cfg = dict(DEFECTOS)
    cfg["_avisos"] = []
    cfg["_existe"] = False
    p = ruta("config.json")
    if os.path.exists(p):
        cfg["_existe"] = True
        try:
            with open(p, encoding="utf-8") as f:
                propio = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            cfg["_avisos"].append("config.json no se pudo leer (%s): uso los defectos" % e)
            propio = {}
        for k, v in (propio if isinstance(propio, dict) else {}).items():
            defecto = DEFECTOS.get(k)
            if k in DEFECTOS and defecto is not None and v is not None \
                    and not isinstance(v, type(defecto)):
                cfg["_avisos"].append("config.json: %s deberia ser %s, uso el defecto"
                                      % (k, type(defecto).__name__))
                continue
            cfg[k] = v
    try:
        cfg["_dias"] = dias_numeros(cfg["dias_envio"])
    except ValueError as e:
        cfg["_avisos"].append(str(e) + ": uso los defectos")
        cfg["_dias"] = dias_numeros(DEFECTOS["dias_envio"])
    try:
        cfg["_ventana"] = ventana_minutos(cfg["ventana_despierta"])
    except (KeyError, ValueError, TypeError):
        cfg["_avisos"].append("ventana_despierta: va como {\"desde\": \"06:00\", \"hasta\": \"09:00\"}")
        cfg["_ventana"] = None
    cfg["correos_propios"] = [c.strip().lower() for c in cfg["correos_propios"] if isinstance(c, str)]
    return cfg


def nombre(cfg):
    return cfg.get("nombre") or "el usuario"


def gws_binario(cfg):
    """Ruta al binario gws, o None si no esta."""
    for cand in (cfg.get("gws"), shutil.which("gws"), GWS_RESPALDO):
        if cand:
            cand = os.path.expanduser(cand)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def label(cfg, ident):
    """Label de launchd de un envio. Un usuario que ya tenia envios con otro prefijo
    lo pone en launchd_prefijo y sus envios viejos siguen reconociendose."""
    return (cfg.get("launchd_prefijo") or DEFECTOS["launchd_prefijo"]).rstrip(".") + "." + ident


def probar_gws(cfg, timeout=30):
    """Lectura sin efectos (el perfil de Gmail) para saber si gws esta autenticado.
    Guarda el resultado en gws-estado.json: build.py lo lee para no ofrecer envio
    programado cuando gws no puede mandar."""
    gws = gws_binario(cfg)
    if not gws:
        estado = {"listo": False, "motivo": "no encuentro el binario gws"}
    else:
        try:
            r = subprocess.run([gws, "gmail", "users", "getProfile", "--params", '{"userId":"me"}'],
                               capture_output=True, text=True, timeout=timeout)
            salida = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 and "emailAddress" in salida:
                estado = {"listo": True, "motivo": "autenticado", "gws": gws}
            else:
                estado = {"listo": False, "gws": gws,
                          "motivo": "gws no esta autenticado o fallo: " + salida.strip()[:160]}
        except (OSError, subprocess.TimeoutExpired) as e:
            estado = {"listo": False, "gws": gws, "motivo": "gws no respondio (%s)" % e}
    estado["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    asegurar()
    with open(ruta("gws-estado.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    return estado


def envio_activo(cfg):
    """El envio de correo se ofrece solo si el usuario lo quiere, gws existe y la
    ultima prueba de --mostrar no dijo que esta caido. Sin prueba guardada, cuenta
    solo que exista el binario (build.py no llama a la red)."""
    if not cfg.get("envio_email") or not gws_binario(cfg):
        return False
    try:
        with open(ruta("gws-estado.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("listo", True))
    except (OSError, json.JSONDecodeError):
        return True


def ajustes_pagina(cfg):
    """Lo que la pagina necesita saber del usuario. build.py lo copia en cada borrador."""
    return {"diasEnvio": cfg["_dias"], "envioEmail": envio_activo(cfg), "ventanaDespierta": cfg["_ventana"]}


def crear(nombre_usuario, correo, envio_email):
    p = ruta("config.json")
    if os.path.exists(p):
        raise SystemExit("ya existe " + p + ": editalo a mano, no lo piso")
    asegurar()
    cfg = {"nombre": nombre_usuario, "correos_propios": [correo] if correo else [],
           "envio_email": envio_email}
    zona = zona_sistema()
    if zona:
        cfg["zona_horaria"] = zona
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return p


def mostrar():
    asegurar()
    cfg = cargar()
    print("DATOS     " + carpeta())
    if not cfg["_existe"]:
        print("PRIMERA VEZ  no hay config.json. Preguntale al usuario su nombre, su correo y si "
              "quiere envio programado de correos, y corre config.py --crear.")
    print("nombre    " + nombre(cfg))
    print("correos   " + (", ".join(cfg["correos_propios"]) or "(ninguno)"))
    zona = cfg.get("zona_horaria") or zona_sistema() or "?"
    print("zona      " + zona + ("" if cfg.get("zona_horaria") else "   (la del sistema)"))
    if cfg.get("zona_horaria") and zona_sistema() and cfg["zona_horaria"] != zona_sistema():
        print("AVISO  la zona de config.json no es la del sistema (" + zona_sistema() + "). "
              "launchd agenda en la hora del sistema.")
    print("dias      " + ", ".join(DIAS[n] for n in cfg["_dias"]) + "   (horario sugerido)")
    print("launchd   " + label(cfg, "<id>"))
    if cfg.get("envio_email"):
        est = probar_gws(cfg)
        if est["listo"]:
            print("envio     ACTIVO  (gws en " + est["gws"] + ", autenticado)")
        else:
            print("envio     APAGADO  " + est["motivo"] + ". El correo termina en Copiar; "
                  "decile al usuario por que.")
    else:
        print("envio     APAGADO  (envio_email: false). El correo termina en Copiar.")
    if cfg.get("reglas_gmail"):
        print("reglas    " + os.path.expanduser(cfg["reglas_gmail"]) + "   (leerlo antes de armar un .eml)")
    pref = ruta("preferencias.md")
    print("prefs     " + (pref + "   (leerlo entero antes de escribir)" if os.path.exists(pref)
                          else "(no hay preferencias.md)"))
    if cfg.get("extras"):
        print("extras    " + json.dumps(cfg["extras"], ensure_ascii=False))
    for a in cfg["_avisos"]:
        print("AVISO  " + a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mostrar", action="store_true", help="imprime carpeta, ajustes y estado de gws")
    ap.add_argument("--crear", action="store_true", help="crea config.json la primera vez")
    ap.add_argument("--nombre", help="con --crear: como llamar al usuario")
    ap.add_argument("--correo", help="con --crear: su correo")
    ap.add_argument("--envio-email", dest="envio_email", choices=["si", "no"], default="si",
                    help="con --crear: si quiere envio programado de correos")
    a = ap.parse_args()
    if a.crear:
        print("CREADO  " + crear(a.nombre, a.correo, a.envio_email == "si"))
        mostrar()
    elif a.mostrar:
        mostrar()
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
