# Instalar /versiones

`/versiones` te arma un mensaje en tres largos y te lo muestra en una página donde eliges, editas y copias. Si quieres, también deja programado un correo para que salga solo desde tu Gmail.

## 1. Instalar (2 minutos)

Abre Claude Code y pega esto tal cual:

```text
Instálame el plugin versiones: corre `claude plugin marketplace add ramotasaray/ramo-plugins` y `claude plugin install versiones@ramo-plugins`. Después, en ~/.claude/settings.json, dentro de extraKnownMarketplaces, deja la entrada "ramo-plugins" con su "source" de GitHub (repo ramotasaray/ramo-plugins) y "autoUpdate": true. Muéstrame cómo quedó.
```

Cierra Claude Code y vuelve a abrirlo.

## 2. Primer uso

Escribe `/versiones` y pega el mensaje al que quieres responder, o di qué quieres escribir. La primera vez te pregunta tu nombre, tu correo y si quieres envío programado. Puedes contestar que no por ahora y activarlo después.

## 3. Envío programado (opcional)

Sin esto, todo funciona igual: eliges el texto, aprietas **Copiar** y lo pegas en Gmail. Con esto, apruebas el correo y tu Mac lo manda a la hora que elijas.

Para mandar desde tu Gmail, tu Mac usa `gws`, un programa de Google. `gws` necesita una conexión con Google a tu nombre. La creas una sola vez en tu propia cuenta de Google Cloud: es gratis y no hace falta tarjeta. Nadie más tiene acceso a esa conexión ni a tu correo.

Lo que vas a necesitar:
- 15 minutos.
- Tu Gmail y su contraseña, porque Google te pide iniciar sesión dos o tres veces en el navegador.
- Homebrew, el instalador de programas para Mac. Si no lo tienes, Claude te dice cómo instalarlo.

Pega esto en Claude Code:

```text
Quiero activar el envío programado de /versiones. Paso a paso, esperándome cuando tenga que hacer algo en el navegador:
1. Revisa si tengo Homebrew; si no, dime cómo instalarlo (yo pego el comando en la Terminal).
2. Instala con brew `googleworkspace-cli` y `google-cloud-sdk` (este segundo trae `gcloud`).
3. Corre `gcloud auth login` para que yo inicie sesión con mi Gmail.
4. Corre `gws auth setup --login`: crea mi propio proyecto de Google Cloud y mi conexión, y me pide permiso para Gmail. Si se traba en la "pantalla de consentimiento", guíame en console.cloud.google.com: tipo de usuario Externo, mi Gmail como usuaria de prueba, cliente OAuth de tipo "App de escritorio", y que el archivo client_secret.json quede en ~/.config/gws/.
5. Al final corre la prueba de arranque de versiones (`config.py --mostrar`) y dime si el envío quedó ACTIVO.
```

Si Google te muestra "Google no verificó esta app", es normal: la app es tuya. Toca **Configuración avanzada** y después **Ir a** con el nombre de tu proyecto.

Tu Mac tiene que estar encendida a la hora del envío.

## Actualizaciones

Te llegan solas: cada vez que abres Claude Code, revisa si hay una versión nueva y la instala.
