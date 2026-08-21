# Diagnóstico do Ambiente

**Data**: 2026-08-19

## Recursos Disponíveis

| Recurso | Status | Detalhes |
|---|---|---|
| Python 3.10+ | ✅ Disponível | Runtime principal |
| Claude Code CLI | ✅ Disponível | Autenticado via OAuth |
| Antigravity CLI | ✅ Disponível | Autenticado via OAuth |
| WASAPI Loopback | ✅ Disponível | Windows 10/11 |
| Faster-Whisper | ⏳ Instalar | Via requirements.txt |
| PyAudioWPatch | ⏳ Instalar | Via requirements.txt |

## Dependências Externas

- Claude Code CLI (`claude`) deve estar no PATH e autenticado
- Antigravity CLI (`agy.exe`) em `%LOCALAPPDATA%\agy\bin\`
- Dispositivo de áudio WASAPI compatível
