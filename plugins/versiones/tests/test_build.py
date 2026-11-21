"""build.py corre de punta a punta sobre un draft de ejemplo, en carpetas temporales."""
import json
import os
import subprocess
import sys

from base import SKILL, ConDatos

DRAFT = {
    "draftId": "prueba-ejemplo",
    "titulo": "Seguimiento a Marta",
    "tab": "Marta",
    "canal": "email",
    "destino": {"para": "marta@empresa.com", "asunto": "Re: propuesta"},
    "secciones": [{
        "id": "apertura", "nombre": "Apertura", "job": "Abre sin pedir nada todavía.",
        "recomendada": "ajustada",
        "opts": {
            "completa": {"text": "Hola Marta! Te escribo para retomar la propuesta del martes.",
                         "note": "da contexto"},
            "ajustada": {"text": "Hola Marta! Retomo la propuesta del martes.", "note": "directo"},
            "minima": {"text": "Hola Marta!", "note": "solo saludo"},
        },
    }],
}


class TestBuild(ConDatos):
    def correr(self, draft_path, out):
        return subprocess.run([sys.executable, os.path.join(SKILL, "build.py"), draft_path, "--out", out],
                              capture_output=True, text=True, env=dict(os.environ))

    def preparar(self, cfg=None):
        if cfg is not None:
            self.escribir_config(cfg)
        ddir = os.path.join(self.datos, "drafts", DRAFT["draftId"])
        os.makedirs(ddir)
        path = os.path.join(ddir, "draft.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DRAFT, f, ensure_ascii=False)
        return path, os.path.join(self.tmp, "out", "versiones.html")

    def test_produce_los_archivos_y_los_ajustes(self):
        path, out = self.preparar({"dias_envio": ["lunes", "sábado"], "envio_email": False})
        r = self.correr(path, out)
        self.assertEqual(r.returncode, 0, r.stderr)
        outdir = os.path.dirname(out)
        for f in ("versiones.html", "app.css", "app.js", "boot.js", "d/index.json",
                  "d/prueba-ejemplo.json"):
            self.assertTrue(os.path.exists(os.path.join(outdir, f)), f)
        with open(os.path.join(outdir, "d", "prueba-ejemplo.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["ajustes"]["diasEnvio"], [1, 6])
        self.assertFalse(d["ajustes"]["envioEmail"])
        self.assertIn("APAGADO", r.stdout)
        with open(out, encoding="utf-8") as f:
            self.assertIn('data-defecto="prueba-ejemplo"', f.read())
        # rev.txt queda junto al draft, en la carpeta de datos
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(path), "rev.txt")))

    def test_la_pagina_lee_los_ajustes(self):
        path, out = self.preparar()
        self.assertEqual(self.correr(path, out).returncode, 0)
        with open(os.path.join(os.path.dirname(out), "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("AJUSTES.diasEnvio", js)
        self.assertIn("AJUSTES.envioEmail === false", js)

    def test_no_construye_dentro_de_drafts(self):
        path, _ = self.preparar()
        r = self.correr(path, os.path.join(self.datos, "drafts", "x", "versiones.html"))
        self.assertEqual(r.returncode, 2)

    def test_avisa_si_el_draft_no_esta_en_la_carpeta_de_datos(self):
        suelto = os.path.join(self.tmp, "suelto.json")
        with open(suelto, "w", encoding="utf-8") as f:
            json.dump(DRAFT, f, ensure_ascii=False)
        r = self.correr(suelto, os.path.join(self.tmp, "out", "versiones.html"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no esta en " + os.path.join(self.datos, "drafts"), r.stdout)

    def test_error_de_contrato(self):
        malo = dict(DRAFT, tab="Un tab demasiado largo")
        p = os.path.join(self.tmp, "malo.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(malo, f)
        r = self.correr(p, os.path.join(self.tmp, "out", "versiones.html"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tab", r.stderr)


class TestDeriva(ConDatos):
    def test_skill_md_no_nombra_flags_inexistentes(self):
        r = subprocess.run([sys.executable, os.path.join(SKILL, "deriva.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
