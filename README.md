# 🎧 Project-EnglishAssistant

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Whisper](https://img.shields.io/badge/Faster--Whisper-STT-FF6F00?style=for-the-badge)
![Claude](https://img.shields.io/badge/Claude-Headless-7C3AED?style=for-the-badge)
![Gemini](https://img.shields.io/badge/Gemini-Headless-4285F4?style=for-the-badge)
![Windows](https://img.shields.io/badge/Windows-WASAPI-0078D6?style=for-the-badge&logo=windows&logoColor=white)

Assistente de reuniões em inglês com captura de áudio do sistema, transcrição local via Whisper e sugestões de resposta em tempo real via Claude ou Gemini headless (OAuth, zero API keys).

---

## Índice

- [📚 Contextualização do projeto](#-contextualização-do-projeto)
- [🛠️ Tecnologias/Ferramentas utilizadas](#️-tecnologiasferramentas-utilizadas)
- [🖥️ Funcionamento do sistema](#️-funcionamento-do-sistema)
- [🔀 Arquitetura da aplicação](#-arquitetura-da-aplicação)
- [📁 Estrutura do projeto](#-estrutura-do-projeto)
- [📌 Como executar o projeto](#-como-executar-o-projeto)
- [🕵️ Dificuldades Encontradas](#️-dificuldades-encontradas)

---

## 📚 Contextualização do projeto

Este projeto foi desenvolvido para auxiliar profissionais que participam de reuniões em inglês, fornecendo suporte em tempo real através de:

1. **Captura de áudio do sistema** — Utiliza WASAPI Loopback no Windows para capturar áudio de qualquer aplicação (Teams, Chrome, Zoom, etc.) sem necessidade de microfone virtual.
2. **Transcrição local** — Processa o áudio capturado com Faster-Whisper (modelo Whisper otimizado) para gerar transcrições em tempo real, sem enviar áudio para nuvem.
3. **Sugestões inteligentes** — Envia as transcrições para Claude ou Gemini via CLI headless (usando sessão OAuth local, sem API keys) para gerar sugestões de respostas apropriadas em inglês.
4. **Contexto customizável** — A pasta `input_data/` permite adicionar documentos de contexto (agendas, vocabulário técnico, perfil profissional, notas de reuniões anteriores) que enriquecem as respostas da IA.

---

## 🛠️ Tecnologias/Ferramentas utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3.10+** | Linguagem principal |
| **PyAudioWPatch** | Captura de áudio do sistema via WASAPI Loopback |
| **Faster-Whisper** | Transcrição de fala para texto (STT) local |
| **Claude Code CLI** | IA headless via OAuth (sem API key) |
| **Antigravity CLI** | Gemini headless via OAuth (sem API key) |
| **Rich** | Interface de terminal com formatação rica |
| **python-dotenv** | Gerenciamento de variáveis de ambiente |

---

## 🖥️ Funcionamento do sistema

O sistema opera em um pipeline contínuo:

1. **AudioCaptureService** captura áudio do sistema via WASAPI Loopback em chunks configuráveis.
2. **TranscriptionService** analisa cada chunk para detectar fala (RMS energy) e transcreve com Faster-Whisper.
3. **ContextService** carrega documentos de contexto da pasta `input_data/`.
4. **ResponseService** combina transcrição + contexto e envia para Claude ou Gemini headless.
5. **AssistantController** orquestra todo o pipeline e exibe resultados no terminal via Rich.

---

## 🔀 Arquitetura da aplicação

```
[System Audio] → [WASAPI Loopback] → [Audio Chunks]
                                          ↓
                                   [Speech Detection]
                                          ↓
                                   [Faster-Whisper STT]
                                          ↓
                              [Transcribed Text + Context]
                                          ↓
                              [Claude CLI / Gemini CLI]
                                          ↓
                              [AI Response → Terminal]
```

---

## 📁 Estrutura do projeto

```
Project-EnglishAssistant/
├── main.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── pytest.ini
├── config/
│   └── settings.py
├── controllers/
│   └── assistant_controller.py
├── services/
│   ├── audio_capture_service.py
│   ├── transcription_service.py
│   ├── claude_cli_service.py
│   ├── gemini_cli_service.py
│   ├── context_service.py
│   └── response_service.py
├── utils/
│   ├── audio_helpers.py
│   └── text_helpers.py
├── output/
├── input_data/
│   └── .gitkeep
├── docs/
│   ├── current-state/
│   │   └── environment-assessment.md
│   ├── planning/
│   │   ├── open-questions.md
│   │   └── risks.md
│   └── implementation/
│       └── roadmap-implementacao.md
└── tests/
    └── conftest.py
```

---

## 📌 Como executar o projeto

### Pré-requisitos

- Python 3.10+
- Windows 10/11 (WASAPI Loopback é exclusivo do Windows)
- Claude Code CLI instalado e autenticado (`claude auth login`)
- E/OU Antigravity CLI instalado e autenticado

### Instalação

```bash
git clone https://github.com/rafael-torres-nantes/Project-EnglishAssistant.git
cd Project-EnglishAssistant
pip install -r requirements.txt
cp .env.example .env
# Editar .env com suas preferências
```

### Uso

```bash
# Iniciar o assistente (modo padrão com Claude)
python main.py listen

# Usar Gemini como provedor
python main.py listen --provider gemini

# Especificar modelo Whisper
python main.py listen --whisper-model large-v3

# Listar arquivos de contexto
python main.py context list

# Testar captura de áudio
python main.py test-audio

# Testar conexão com IA
python main.py test-ai
```

### Adicionando Contexto

Coloque arquivos `.txt` ou `.md` na pasta `input_data/`:

```
input_data/
├── meeting-agenda.txt
├── technical-vocabulary.md
├── rafael-profile.md
└── team-names.txt
```

---

## ⚡ Performance (velocidade x precisão)

O pipeline tem dois pontos de latência configuráveis, cada um com trade-off entre velocidade e qualidade:

| Config | Rápido (atual) | Preciso | Onde |
|---|---|---|---|
| `WHISPER_MODEL_SIZE` | `small` | `medium` | `.env` |
| `WHISPER_BEAM_SIZE` | `1` | `5` | `.env` |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cuda` / `float16` — ~40% mais rápido que CPU depois do warm-up (medido nesta máquina, GTX 1650) | `cpu` / `int8` — sem GPU disponível | `.env` |
| Autenticação Claude CLI | OAuth (`claude auth login`) — ~3s de overhead de CLI por chamada, sem custo extra | `ANTHROPIC_API_KEY` + `--bare` — ~1,4s de overhead de CLI por chamada, cobra por token de API | `services/claude_cli_service.py` |
| `CLAUDE_MODEL` | `sonnet` — **~5,3s médios**, contra-intuitivamente mais rápido que haiku nesta CLI (ver nota abaixo) | `haiku` — ~13,2s médios | `.env` |

`config/settings.py` já lê todas as variáveis Whisper do `.env`; se `WHISPER_DEVICE=cuda` falhar (ex: rodando numa máquina sem GPU NVIDIA), `TranscriptionService` cai para `cpu`/`int8` automaticamente e loga um aviso. O modo `--bare` do Claude CLI não está implementado (exige trocar OAuth por `ANTHROPIC_API_KEY`, uma decisão de custo).

**Nota sobre `CLAUDE_MODEL`:** benchmark com `scripts/benchmark_ai_response.py` (3 execuções por config, prompt de reunião realista) mostrou o Sonnet 2,5x mais rápido que o Haiku de forma consistente — o oposto do esperado. A causa é o bloco de "thinking" oculto do Claude CLI (ver seção de streaming abaixo): ele domina o tempo total, e nesta CLI o Haiku gerou um thinking mais longo que o Sonnet. Detalhes e dados completos em [`docs/planning/decisions.md`](docs/planning/decisions.md).

### Streaming da resposta (`STREAMING`)

Com `STREAMING=True` no `.env`, `ClaudeCLIService.run_text_stream` usa `--output-format stream-json --include-partial-messages` e o painel de sugestões vai preenchendo em tempo real em vez de aparecer tudo de uma vez ao final.

**Medido na prática:** o ganho é menor do que o esperado. O modelo gera um bloco de "thinking" oculto antes do texto visível, e esse bloco sozinho já consome a maior parte do tempo total (em teste com haiku, ~7-8s de thinking contra ~1s de texto visível) — então o primeiro pedaço de texto só aparece perto do fim da resposta de qualquer forma. `GeminiCLIService` não tem streaming incremental mapeado; com `STREAMING=True` e provider Gemini, a resposta ainda chega de uma vez (um único "pedaço").

---

## 🕵️ Dificuldades Encontradas

1. **WASAPI Loopback no Windows** — A captura de áudio do sistema requer o uso de WASAPI Loopback, disponível apenas no Windows. A biblioteca PyAudioWPatch é um fork do PyAudio que adiciona suporte nativo a esse recurso.
2. **Latência de transcrição** — O modelo Whisper precisa de chunks de áudio suficientemente longos para transcrição precisa, mas curtos o suficiente para feedback em tempo real. O equilíbrio foi encontrado com chunks de 5 segundos e detecção de silêncio.
3. **Invocação headless sem API keys** — O padrão de zero API keys herda sessões OAuth locais do Claude Code e Antigravity, exigindo que o usuário esteja autenticado localmente.
