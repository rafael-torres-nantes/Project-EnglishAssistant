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

## Notas de Ambiente (Windows)

**Atualizado**: 2026-08-27

- Faster-Whisper com `WHISPER_DEVICE=cuda` falhava ao carregar as DLLs do cuBLAS/cuDNN em
  alguns setups Windows (pacotes `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` instalados via pip,
  fora do PATH do sistema). `main.py` agora varre `sys.path` por esses pacotes e injeta o
  diretório `bin` de cada um no `PATH` e via `os.add_dll_directory()` antes de qualquer import
  do Whisper — só roda em `os.name == 'nt'`.
