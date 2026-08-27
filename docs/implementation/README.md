# Roadmap de Implementação

| Fase | Entregável | Status | Arquivo |
|---|---|---|---|
| F1 | Scaffold do projeto | ✅ Concluído | Estrutura completa |
| F2 | Captura de áudio WASAPI | ✅ Concluído | `services/audio_capture_service.py` |
| F3 | Transcrição Whisper | ✅ Concluído | `services/transcription_service.py` |
| F4 | Integração Claude CLI | ✅ Concluído | `services/claude_cli_service.py` |
| F5 | Integração Gemini CLI | ✅ Concluído | `services/gemini_cli_service.py` |
| F6 | Context input | ✅ Concluído | `services/context_service.py` |
| F7 | Controller principal | ✅ Concluído | `controllers/assistant_controller.py` |
| F8 | CLI entrypoint | ✅ Concluído | `main.py` |
| F9 | Testes unitários | ⏳ Em andamento | `tests/` |
| F10 | Documentação final | ⏳ Em andamento | `README.md`, `docs/` |
| F11 | Benchmark e otimização de latência de resposta IA | ✅ Concluído | `scripts/benchmark_ai_response.py`, [`docs/planning/decisions.md`](../planning/decisions.md) |

| F12 | Interrup��o manual (tecla 'p') e UI fixa | ? Conclu�do | \controllers/assistant_controller.py\ |
| F13 | Otimiza��o de prompt e tradu��o em tempo real | ? Conclu�do | \config/settings.py\ |

