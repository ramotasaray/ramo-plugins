# Plugin versiones

Skill `/versiones`: arma un mensaje transaccional en tres largos por sección y lo publica como página (Claude Artifact) donde el usuario elige, edita y aprueba; el correo se puede agendar con launchd y `gws`. Solo librería estándar de Python. Lo usan varias personas desde este mismo código.

## Verificar

Desde la raíz del repo:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/versiones/tests
```

Corre las pruebas de `config.py`, `destinatarios.py`, el label de `agendar.py`, `build.py` sobre un draft de ejemplo y `deriva.py` (que SKILL.md y ENVIO.md no nombren flags inexistentes). Las pruebas usan una carpeta de datos temporal (`VERSIONES_DATOS`): nunca tocan `~/.claude` real ni llaman a `gws` ni a `launchctl`.

Correr la skill: no hay servidor; se invoca `/versiones` en Claude Code. Para ver la página local: `build.py` con `--out` a una carpeta temporal y `python3 -m http.server <puerto> --directory <carpeta>`.

## Qué no se toca

- `skills/versiones/template.html` (121 KB): editar solo por partes (`grep -n`, `sed -n`), nunca reescribirlo entero. El agente que usa la skill nunca lo lee.
- Nada personal en este repo, que es público: nombres, correos, rutas de un usuario, zonas horarias, integraciones propias. Todo eso va en el `config.json` o el `preferencias.md` de la carpeta de datos de cada usuario.

## Dónde viven los datos

En `~/.claude/versiones-datos/` (o la ruta de la variable `VERSIONES_DATOS`), nunca dentro de la carpeta del plugin, que se reemplaza en cada actualización: `config.json`, `preferencias.md`, `drafts/`, `agenda/`, `registro.jsonl`, `artifact.txt`, `gws-estado.json`. `config.py` resuelve la ruta y los ajustes; todos los scripts lo usan.

## Quién lo usa y cómo

- El autor del repo usa la skill desde este código: su `~/.claude/skills/versiones` es un enlace simbólico a `plugins/versiones/skills/versiones`. Sus cambios rigen al instante en su Mac. Él NO instala el plugin: tendría la skill dos veces.
- Los demás usuarios instalan el plugin desde GitHub (`INSTALAR.md`), con `autoUpdate: true`: reciben un cambio cuando está en la rama `main` en GitHub y `version` subió.

## Reglas

- **Subir `version` en `.claude-plugin/plugin.json` en cada cambio que deba llegar a los usuarios.** Sin ese cambio, Claude Code no detecta la actualización.
- Un valor que un usuario puede querer distinto va en `config.py` (`DEFECTOS`) y en la tabla de ajustes de `SKILL.md`, no fijo en el código.
- Después de editar `SKILL.md`, `ENVIO.md` o un CLI, correr la verificación: incluye `deriva.py`.
- `agendar.py` copia `gate.py`, `config.py` y `agendar.py` dentro de cada `agenda/<id>/`, porque la ruta del plugin cambia al actualizarse. Si un envío agendado pasa a depender de otro script, sumarlo a esa copia.
