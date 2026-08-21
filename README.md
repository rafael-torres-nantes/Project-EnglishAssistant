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
4. **Contexto customizável** — A pasta `context_input/` permite adicionar documentos de contexto (agendas, vocabulário técnico, notas de reuniões anteriores) que enriquecem as respostas da IA.

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
3. **ContextService** carrega documentos de contexto da pasta `context_input/`.
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
├── context_input/
│   └── .gitkeep
├── output/
├── input_data/
├── docs/
│   ├── current-state/
│   │   └── environment-assessment.md
│   ├── planning/
│   │   ├── open-questions.md
│   │   └── risks.md
│   └── implementation/
│       └── README.md
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

Coloque arquivos `.txt` ou `.md` na pasta `context_input/`:

```
context_input/
├── meeting-agenda.txt
├── technical-vocabulary.md
└── team-names.txt
```

---

## 🕵️ Dificuldades Encontradas

1. **WASAPI Loopback no Windows** — A captura de áudio do sistema requer o uso de WASAPI Loopback, disponível apenas no Windows. A biblioteca PyAudioWPatch é um fork do PyAudio que adiciona suporte nativo a esse recurso.
2. **Latência de transcrição** — O modelo Whisper precisa de chunks de áudio suficientemente longos para transcrição precisa, mas curtos o suficiente para feedback em tempo real. O equilíbrio foi encontrado com chunks de 5 segundos e detecção de silêncio.
3. **Invocação headless sem API keys** — O padrão de zero API keys herda sessões OAuth locais do Claude Code e Antigravity, exigindo que o usuário esteja autenticado localmente.
