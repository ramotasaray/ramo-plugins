# ramo-plugins

Marketplace público de plugins de Claude Code (`.claude-plugin/marketplace.json`). Cada plugin vive en `plugins/<nombre>/`.

## Reglas para todo plugin

- El repo es público y los plugins se comparten o venden a personas que el autor no conoce. Nada personal en el código: nombres, correos, rutas de un usuario, zonas horarias, links propios. Lo personal va en una carpeta de datos del usuario, fuera del repo.
- Nunca repartir secretos ni credenciales del autor (client_secret.json, tokens, API keys). Cada usuario crea los suyos.
- Todo plugin trae `plugins/<nombre>/INSTALAR.md` para el usuario final, que no es programador. Lleva:
  1. Qué hace, en una línea.
  2. Un texto para pegar en Claude Code que instala el plugin.
  3. Cada requisito externo (programas, cuentas, keys): cómo conseguirlo a su nombre, cuánto tarda y cuánto cuesta.
  4. Cómo le llegan las actualizaciones.
- Todo plugin trae `plugins/<nombre>/CLAUDE.md` con el comando de verificación.
- Subir `version` en `plugins/<nombre>/.claude-plugin/plugin.json` en cada cambio que deba llegar a los usuarios.
