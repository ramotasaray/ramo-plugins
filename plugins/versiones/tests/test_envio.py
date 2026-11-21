"""destinatarios.py (responder a todos) y el label de launchd de agendar.py."""
from base import ConDatos


class TestDestinatarios(ConDatos):
    def test_correos_propios_salen_de_config(self):
        self.escribir_config({"correos_propios": ["yo@correo.com"]})
        dest = self.modulo("destinatarios")
        self.assertEqual(dest.propios(), {"yo@correo.com"})

    def test_ultimo_de_otro_se_le_contesta_y_el_resto_en_copia(self):
        self.escribir_config({"correos_propios": ["yo@correo.com"]})
        dest = self.modulo("destinatarios")
        h = {"from": "Marta <marta@empresa.com>",
             "to": "yo@correo.com, sam@x.com", "cc": "andrea@y.com"}
        para, copia = dest.responder_a_todos("hilo", h=h)
        self.assertEqual(para, ["marta@empresa.com"])
        self.assertEqual(copia, ["sam@x.com", "andrea@y.com"])     # sin el propio

    def test_ultimo_propio_repite_sus_destinatarios(self):
        self.escribir_config({"correos_propios": ["yo@correo.com"]})
        dest = self.modulo("destinatarios")
        h = {"from": "yo@correo.com", "to": "marta@empresa.com", "cc": "sam@x.com, yo@correo.com"}
        para, copia = dest.responder_a_todos("hilo", h=h)
        self.assertEqual(para, ["marta@empresa.com"])
        self.assertEqual(copia, ["sam@x.com"])

    def test_sin_correos_propios_el_usuario_queda_como_destinatario(self):
        # Por eso config.py --crear pide el correo: sin el, el usuario se copia a si mismo.
        dest = self.modulo("destinatarios")
        h = {"from": "marta@empresa.com", "to": "yo@correo.com", "cc": ""}
        para, copia = dest.responder_a_todos("hilo", h=h)
        self.assertEqual(copia, ["yo@correo.com"])


class TestLabel(ConDatos):
    def test_prefijo_por_defecto(self):
        agendar = self.modulo("agendar")
        self.assertEqual(agendar.label("20261121-0800-x"), "com.versiones.20261121-0800-x")

    def test_prefijo_propio_conserva_labels_viejos(self):
        self.escribir_config({"launchd_prefijo": "com.ejemplo.versiones."})
        agendar = self.modulo("agendar")
        self.assertEqual(agendar.label("abc"), "com.ejemplo.versiones.abc")
        dirs, plist = agendar.rutas("abc")
        self.assertTrue(plist.endswith("/Library/LaunchAgents/com.ejemplo.versiones.abc.plist"))
        self.assertEqual(dirs, self.datos + "/agenda/abc")

    def test_agenda_en_la_carpeta_de_datos(self):
        agendar = self.modulo("agendar")
        self.assertEqual(agendar.AGENDA, self.datos + "/agenda")
        self.assertEqual(agendar.listar(None), 0)      # sin agenda: no falla
