# Riscos

| # | Risco | Impacto | Mitigação | Status |
|---|---|---|---|---|
| R1 | WASAPI Loopback indisponível em dispositivo de áudio virtual | Captura falha | Fallback para microfone; mensagem de erro clara | ❌ aberto |
| R2 | Claude/Gemini CLI não autenticados | IA indisponível | Validação no startup com mensagem de instrução | ❌ aberto |
| R3 | Modelo Whisper grande demais para RAM | OOM ou lentidão | Default para 'medium'; configurável via --whisper-model | ❌ aberto |
| R4 | Latência alta entre transcrição e resposta | UX degradada | Chunks curtos + modelo Whisper leve + cache de contexto + `CLAUDE_MODEL=sonnet` (ver [`decisions.md#d1`](decisions.md#d1--claude_model-padrão-trocado-de-haiku-para-sonnet), 2.5x mais rápido que haiku nesta CLI) | ⚠️ parcial |
| R5 | Áudio de baixa qualidade em reuniões | Transcrição imprecisa | Threshold de silêncio configurável; indicador de qualidade | ❌ aberto |
