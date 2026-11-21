# ramo-plugins

Marketplace de Claude Code con tres plugins:

- **transcribe**: audio o video a texto, con separación de hablantes (ElevenLabs Scribe v2). Necesita `ELEVENLABS_API_KEY` en `~/.config/elevenlabs/config`.
- **watch**: preguntarle cosas a un video. Es el plugin de [bradautomates/claude-video](https://github.com/bradautomates/claude-video), listado acá para instalar todo de una vez.
- **versiones**: arma un mensaje en tres largos y lo muestra en una página para elegir, editar y copiar; opcional, envío programado por Gmail. Guía: [plugins/versiones/INSTALAR.md](plugins/versiones/INSTALAR.md).

```bash
claude plugin marketplace add ramotasaray/ramo-plugins
claude plugin install transcribe@ramo-plugins
claude plugin install watch@ramo-plugins
claude plugin install versiones@ramo-plugins
```
