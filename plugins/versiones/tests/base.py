"""Base comun de las pruebas: cada prueba corre con una carpeta de datos temporal.

VERSIONES_DATOS apunta a un directorio temporal antes de importar cualquier script,
asi ninguna prueba lee ni escribe en la carpeta de datos real del usuario.
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

SKILL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "skills", "versiones"))
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)


class ConDatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="versiones-test-")
        self.datos = os.path.join(self.tmp, "datos")
        self._env_previo = os.environ.get("VERSIONES_DATOS")
        os.environ["VERSIONES_DATOS"] = self.datos

    def tearDown(self):
        if self._env_previo is None:
            os.environ.pop("VERSIONES_DATOS", None)
        else:
            os.environ["VERSIONES_DATOS"] = self._env_previo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escribir_config(self, cfg):
        os.makedirs(self.datos, exist_ok=True)
        with open(os.path.join(self.datos, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def modulo(self, nombre):
        """Importa (o recarga) un script de la skill con el VERSIONES_DATOS de esta prueba."""
        import config
        importlib.reload(config)
        if nombre == "config":
            return config
        mod = importlib.import_module(nombre)
        return importlib.reload(mod)
