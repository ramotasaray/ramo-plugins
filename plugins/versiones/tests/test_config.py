import json
import os
import stat

from base import ConDatos


class TestConfig(ConDatos):
    def test_carpeta_sale_de_VERSIONES_DATOS(self):
        config = self.modulo("config")
        self.assertEqual(config.carpeta(), self.datos)
        config.asegurar()
        self.assertTrue(os.path.isdir(os.path.join(self.datos, "drafts")))
        self.assertTrue(os.path.isdir(os.path.join(self.datos, "agenda")))

    def test_carpeta_por_defecto_sin_variable(self):
        config = self.modulo("config")
        os.environ.pop("VERSIONES_DATOS")
        self.assertEqual(config.carpeta(), os.path.expanduser("~/.claude/versiones-datos"))
        os.environ["VERSIONES_DATOS"] = self.datos   # tearDown no debe tocar la real

    def test_defectos_sin_config_json(self):
        config = self.modulo("config")
        cfg = config.cargar()
        self.assertFalse(cfg["_existe"])
        self.assertEqual(config.nombre(cfg), "el usuario")
        self.assertEqual(cfg["correos_propios"], [])
        self.assertEqual(cfg["launchd_prefijo"], "com.versiones")
        self.assertTrue(cfg["envio_email"])
        self.assertEqual(cfg["_dias"], [1, 2, 3, 4, 5])
        self.assertIsNone(cfg["_ventana"])
        self.assertEqual(cfg["_avisos"], [])

    def test_config_parcial_completa_con_defectos(self):
        self.escribir_config({"nombre": "Marta", "correos_propios": ["Marta@Empresa.com "]})
        config = self.modulo("config")
        cfg = config.cargar()
        self.assertTrue(cfg["_existe"])
        self.assertEqual(config.nombre(cfg), "Marta")
        self.assertEqual(cfg["correos_propios"], ["marta@empresa.com"])
        self.assertEqual(cfg["launchd_prefijo"], "com.versiones")
        self.assertEqual(cfg["_dias"], [1, 2, 3, 4, 5])

    def test_tipo_equivocado_vuelve_al_defecto_con_aviso(self):
        self.escribir_config({"correos_propios": "marta@empresa.com", "envio_email": "si"})
        config = self.modulo("config")
        cfg = config.cargar()
        self.assertEqual(cfg["correos_propios"], [])
        self.assertTrue(cfg["envio_email"])
        self.assertEqual(len(cfg["_avisos"]), 2)

    def test_config_json_roto_no_rompe(self):
        os.makedirs(self.datos)
        with open(os.path.join(self.datos, "config.json"), "w") as f:
            f.write("{no es json")
        cfg = self.modulo("config").cargar()
        self.assertEqual(cfg["launchd_prefijo"], "com.versiones")
        self.assertEqual(len(cfg["_avisos"]), 1)

    def test_dias_con_y_sin_tilde_y_numeros(self):
        config = self.modulo("config")
        self.assertEqual(config.dias_numeros(["Sábado", "lunes", "miercoles", 0]), [0, 1, 3, 6])
        with self.assertRaises(ValueError):
            config.dias_numeros(["feriado"])

    def test_dias_invalidos_vuelven_al_defecto(self):
        self.escribir_config({"dias_envio": ["feriado"]})
        cfg = self.modulo("config").cargar()
        self.assertEqual(cfg["_dias"], [1, 2, 3, 4, 5])
        self.assertEqual(len(cfg["_avisos"]), 1)

    def test_ventana_despierta(self):
        self.escribir_config({"ventana_despierta": {"desde": "06:00", "hasta": "09:00"}})
        self.assertEqual(self.modulo("config").cargar()["_ventana"], [360, 540])

    def test_crear_no_pisa(self):
        config = self.modulo("config")
        p = config.crear("Marta", "marta@empresa.com", False)
        with open(p) as f:
            cfg = json.load(f)
        self.assertEqual(cfg["nombre"], "Marta")
        self.assertEqual(cfg["correos_propios"], ["marta@empresa.com"])
        self.assertFalse(cfg["envio_email"])
        with self.assertRaises(SystemExit):
            config.crear("Otra", None, True)

    def _gws_falso(self, codigo, salida):
        ruta = os.path.join(self.tmp, "gws")
        with open(ruta, "w") as f:
            f.write("#!/bin/sh\necho '%s'\nexit %d\n" % (salida, codigo))
        os.chmod(ruta, os.stat(ruta).st_mode | stat.S_IEXEC)
        return ruta

    def test_envio_activo_segun_gws(self):
        bueno = self._gws_falso(0, '{"emailAddress": "marta@empresa.com"}')
        self.escribir_config({"gws": bueno})
        config = self.modulo("config")
        cfg = config.cargar()
        self.assertTrue(config.envio_activo(cfg))          # sin prueba guardada: alcanza el binario
        self.assertTrue(config.probar_gws(cfg)["listo"])
        self.assertTrue(config.envio_activo(cfg))

        malo = self._gws_falso(1, "auth required")
        self.escribir_config({"gws": malo})
        cfg = config.cargar()
        self.assertFalse(config.probar_gws(cfg)["listo"])
        self.assertFalse(config.envio_activo(cfg))           # la prueba guardada dijo que no

    def test_envio_apagado_por_config_o_sin_gws(self):
        self.escribir_config({"envio_email": False, "gws": self._gws_falso(0, "emailAddress")})
        config = self.modulo("config")
        self.assertFalse(config.envio_activo(config.cargar()))
        self.escribir_config({"gws": os.path.join(self.tmp, "no-existe")})
        cfg = config.cargar()
        if config.gws_binario(cfg) is None:                  # en esta maquina no hay gws real
            self.assertFalse(config.envio_activo(cfg))
            self.assertFalse(config.ajustes_pagina(cfg)["envioEmail"])
