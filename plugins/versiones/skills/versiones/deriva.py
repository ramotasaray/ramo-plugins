#!/usr/bin/env python3
"""Chequea que SKILL.md no nombre flags ni subcomandos que los CLIs no tienen.

Falla en UNA SOLA direccion, a proposito. Un flag que el CLI declara y SKILL.md no
nombra esta bien: el paso 9 dice explicitamente que los flags de `agendar.py crear`
no se copien de vuelta al documento. Lo que rompe es al reves: que SKILL.md afirme
algo que el comando no hace.

Uso:  python3 <carpeta de la skill>/deriva.py
Sale 0 si no hay deriva, 1 nombrando cada flag o subcomando inventado.
"""
import ast
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CLIS = ("build.py", "agendar.py", "config.py")
BUILTIN = {"-h", "--help"}

RE_FLAG = re.compile(r"(?<![\w-])(--?[A-Za-z][\w-]*)")
RE_SPAN = re.compile(r"`([^`]+)`")
RE_TITULO = re.compile(r"#{1,6} ")


def declara(ruta):
    """Lee del fuente los add_argument/add_parser de argparse, subparsers incluidos."""
    flags, subs = set(), set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        textos = [a.value for a in nodo.args
                  if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if nodo.func.attr == "add_parser" and textos:
            subs.add(textos[0])
        elif nodo.func.attr == "add_argument":
            flags.update(t for t in textos if t.startswith("-"))
    return flags | BUILTIN, subs


def nombrado(chunk):
    """Cual de nuestros CLIs invoca este pedazo de texto, si invoca alguno."""
    for cli in CLIS:
        if cli in chunk:
            return cli
    return None


def ajeno(chunk):
    """True si el pedazo es un comando de otro programa (mkdir, http.server, gws...)."""
    tokens = chunk.split()
    return bool(tokens) and not tokens[0].startswith("-")


def invoca(chunk, cli, span):
    """True si el pedazo CORRE el CLI, en vez de solo nombrarlo.

    Sin esto, el arbol de archivos del paso Arquitectura ("build.py  inyecta el
    draft.json") pasa por una invocacion y su glosa por un subcomando.
    """
    return "python3" in chunk or (span and chunk.strip().startswith(cli))


def revisar():
    declarado = {cli: declara(AQUI / cli) for cli in CLIS}
    todos = set().union(*(f for f, _ in declarado.values()))
    fallas = []
    ultimo = None          # ultimo CLI nuestro nombrado en esta seccion
    dentro = False         # dentro de un bloque ```
    pendiente, inicio = "", None
    prosa, prosa_inicio = "", None

    def cotejar(chunk, linea, cli, span=False):
        """Los flags y subcomandos del chunk contra lo que el CLI declara."""
        flags, subs = declarado[cli] if cli else (todos, set())
        donde = cli
        for flag in RE_FLAG.findall(chunk):
            if flag not in flags:
                fallas.append((linea, donde, "flag", flag))
        if cli and invoca(chunk, cli, span):
            for token in re.findall(rf"{re.escape(cli)}\s+([a-z][\w-]*)", chunk):
                if token not in subs:
                    fallas.append((linea, cli, "subcomando", token))

    for n, linea in enumerate("\n".join((AQUI / f).read_text(encoding="utf-8") for f in ("SKILL.md", "ENVIO.md")).splitlines(), 1):
        if linea.lstrip().startswith("```"):
            dentro = not dentro
            continue
        if dentro:
            pendiente += " " + linea
            if inicio is None:
                inicio = n
            if linea.rstrip().endswith("\\"):
                continue
            chunk, ln = pendiente, inicio
            pendiente, inicio = "", None
            cli = nombrado(chunk)
            if cli:
                ultimo = cli
                cotejar(chunk, ln, cli)
            continue
        if not prosa and RE_TITULO.match(linea):
            ultimo = None
            continue
        prosa += (" " if prosa else "") + linea
        if prosa_inicio is None:
            prosa_inicio = n
        if prosa.count("`") % 2:
            continue           # el span de backticks sigue en la linea de abajo
        chunk, ln = prosa, prosa_inicio
        prosa, prosa_inicio = "", None
        for span in RE_SPAN.findall(chunk):
            cli = nombrado(span)
            if cli:
                ultimo = cli
                cotejar(span, ln, cli, span=True)
            elif not ajeno(span):
                cotejar(span, ln, ultimo)
        cotejar(RE_SPAN.sub(" ", chunk), ln, ultimo)
    return fallas


if __name__ == "__main__":
    fallas = revisar()
    if not fallas:
        print("SKILL.md no nombra ningun flag ni subcomando que los CLIs no tengan.")
        sys.exit(0)
    print("Deriva entre SKILL.md y los CLIs:", file=sys.stderr)
    for linea, cli, clase, token in fallas:
        sujeto = f"{cli} no tiene" if cli else "ningun CLI de la skill tiene"
        print(f"  SKILL.md:{linea}  {sujeto} el {clase} {token}", file=sys.stderr)
    print("\nArreglar el documento, no el CLI: el documento es el que afirma de mas.",
          file=sys.stderr)
    sys.exit(1)
