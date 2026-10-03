# ramo-plugins

Marketplace de Claude Code con dos plugins:

- **transcribe**: audio o video a texto, con separación de hablantes (ElevenLabs Scribe v2). Necesita `ELEVENLABS_API_KEY` en `~/.config/elevenlabs/config`.
- **watch**: preguntarle cosas a un video. Es el plugin de [bradautomates/claude-video](https://github.com/bradautomates/claude-video), listado acá para instalar todo de una vez.

```bash
claude plugin marketplace add ramotasaray/ramo-plugins
claude plugin install transcribe@ramo-plugins
claude plugin install watch@ramo-plugins
```
