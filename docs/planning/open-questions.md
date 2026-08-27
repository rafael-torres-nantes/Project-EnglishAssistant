# Questões Abertas

## Rafael

- [ ] Definir se o assistente deve salvar transcrições automaticamente em output/
- [ ] Avaliar necessidade de GUI (Tkinter/web) vs terminal-only
- [ ] Definir se deve suportar múltiplos idiomas de entrada (não só inglês)
- [x] Avaliar integração com hotkeys para ativar/desativar captura — parcialmente resolvido:
      tecla `p` força o processamento imediato da fala acumulada, sem esperar o timeout de
      silêncio (`controllers/assistant_controller.py`, commit `1230164`)
- [ ] Avaliar hotkey para pausar/retomar a captura de áudio em si (distinto de forçar
      processamento, que já existe)
- [ ] Definir formato de export das transcrições (txt, srt, json)
