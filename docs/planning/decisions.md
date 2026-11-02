# Decisões Técnicas

## D1 — CLAUDE_MODEL padrão trocado de `haiku` para `sonnet`

**Data**: 2026-08-22
**Status**: ✅ Aplicado (`.env`)

### Contexto

`R4` ([`risks.md`](risks.md)) apontava latência alta entre transcrição e resposta como risco aberto.
Para decidir a melhor configuração de provider/modelo de IA, foi rodado um benchmark
(`scripts/benchmark_ai_response.py`) com um prompt de reunião realista, 3 execuções por
configuração, contra `ResponseService.generate_response` — o mesmo caminho de código usado
em produção pelo `AssistantController`.

### Resultado medido

| Configuração | Tempo médio | Min / Max | Observação de qualidade |
|---|---|---|---|
| Claude Haiku (default anterior) | 13.15s | 12.74s / 13.54s | Boa, porém mais verbosa |
| **Claude Sonnet (novo default)** | **5.30s** | 4.96s / 5.62s | Resposta natural, ação concreta sugerida |
| Gemini 3.5 Flash High | 10.19s | 8.25s / 11.82s | Formato mais aderente ao prompt de sistema (sem "filler"), mas depende do Antigravity |

### Por que o Sonnet venceu (contra-intuitivo)

A expectativa era que Haiku fosse o mais rápido por ser o modelo menor. O [README](../../README.md) já
documentava (seção "Streaming da resposta") que o Claude CLI gera um bloco de "thinking"
oculto antes do texto visível, e que esse bloco consome a maior parte do tempo total
(~7-8s de thinking contra ~1s de texto visível, medido com haiku). O benchmark confirma
esse comportamento na prática: a latência observada aqui vem majoritariamente do overhead
do subprocesso `claude` CLI / do bloco de thinking, não do tamanho do modelo — por isso o
Sonnet, com um bloco de thinking mais curto nesta CLI, terminou 2.5x mais rápido que o Haiku
de forma consistente nas 3 repetições (não foi ruído de rede).

### Decisão

- `CLAUDE_MODEL=sonnet` no `.env` (era `haiku`).
- `AI_PROVIDER=claude` e `STREAMING=True` mantidos — já são a melhor combinação: streaming
  reduz a latência percebida e o provider Claude evita a dependência extra do Antigravity.
- Budget cap (`--max-budget-usd 0.50` em `ClaudeCLIService`) já protege contra custo por
  chamada, então a troca de modelo não introduz risco financeiro sem teto.

### Como reproduzir

```bash
python scripts/benchmark_ai_response.py
```

Ajustar `runs_per_config` ou a lista de configs em `if __name__ == "__main__":` para testar
outras combinações (ex: outros modelos Gemini, ou incluir a etapa de transcrição Whisper).

## D2 — Migração para Gemini e Otimizações de Latência/UX

**Data**: 2026-08-27
**Status**: ✅ Aplicado (`.env`, `config/settings.py`, `controllers/assistant_controller.py`)

### Contexto
O usuário solicitou melhorias para a interrupção da fala da pessoa na reunião, forçando a IA a gerar uma resposta parcial no exato milissegundo de corte. Também houve necessidade de aumentar a velocidade de resposta trocando a stack de provider e limitando o tamanho da resposta estruturada, que agora exibe 6 bullet-points progressivos e traduzidos para Português em parênteses.

### Decisão
- `GEMINI_MODEL=gemini-3.7-flash-low` no `.env`: trocado o modelo para o mais rápido disponível via Antigravity, com threshold baixo de thinking.
- **Teclado não-bloqueante**: Utilizado `msvcrt.kbhit()` para Windows, escutando a tecla 'p' em background sem atrasar o loop de áudio WASAPI.
- **Limpeza de Buffer**: Adicionado flush (`clear()`) da fila de áudio (`audio_queue`) após a geração da resposta. Evita que a IA processe falas residuais captadas enquanto ela demorava para pensar.
- **Feedback Visual (Rich)**: Corrigido bug de quebra de tela ao intercalar `console.print()` com painéis transitórios (`Live`). Agora o `Live` display encolhe temporariamente (`⏳ Cleaning up...`) antes de efetuar prints absolutos, prevenindo duplicação da UI no stdout do terminal.
- **Engenharia de Prompt**: Adicionada estrutura de 6 bullet-points em ordem de complexidade, e tradução PT-BR (parênteses) das explicações conceituais.

## D3 — Fix de layout do Rich Live (streaming) e extração do prompt de sistema

**Data**: 2026-08-27
**Status**: ✅ Aplicado (`controllers/assistant_controller.py`, `prompt_template/conversational_prompt.py`, `services/response_service.py`)

### Contexto

A correção de UI descrita em D2 (painel `⏳ Cleaning up...` antes do print final) não foi
suficiente: respostas de streaming longas que rolavam o terminal ainda desalinhavam o cursor
do `rich.Live`, duplicando o painel de sugestões na tela. O prompt de sistema conversacional
(`SYSTEM_PROMPT_TEMPLATE`), por sua vez, tinha crescido a ponto de poluir `config/settings.py`.

### Decisão

- Streaming ganhou um `Live` próprio e persistente (`transient=False`, `auto_refresh=False`
  com `refresh=True` manual em cada update) só para o bloco de sugestões, em vez de reaproveitar
  o `Live` do status principal — corrige o rastreio de cursor quando o terminal rola.
- Transcrição forçada (`force_process`) e os prints permanentes (transcrição, sugestão final,
  erro) agora fazem `live.stop()` / `live.start()` em volta do `console.print()`, no lugar do
  hack de painel `⏳ Cleaning up...` — elimina a duplicação de painel na tela.
- `SYSTEM_PROMPT_TEMPLATE` saiu de `config/settings.py` e virou `CONVERSATIONAL_SYSTEM_PROMPT`
  em `prompt_template/conversational_prompt.py`; `ResponseService._build_system_prompt` passou
  a importar de lá. `config/settings.py` volta a ser só configuração.
- O prompt ganhou uma regra de correção fonética: mapear termos técnicos transcritos errado
  (ex.: "OTS LOW DE BALANCE") para o conceito real (ex.: "What is load balancer?") antes de
  responder — o Whisper erra termos técnicos com frequência em reuniões de engenharia.

### Nota sobre D2

A entrada D2 descrevia a correção de UI de forma prospectiva; o comportamento correto só foi
implementado nesta decisão (D3). Para o estado atual do `Live`, use D3 como referência.

## D4 — Treinador de comunicação: limites, microfone no servidor e CLI pré-aquecida

**Data**: 2026-11-02
**Status**: ✅ Aplicado (`main.py coach`); falta o teste com voz humana

### Limites do produto

- O treinador só usa microfone e só dá retorno depois da fala. Não há modo nem contexto para
  entrevista ou teste avaliado ao vivo.
- Não lê `input_data/` nem usa `AudioCaptureService`; `tests/test_coach_controller.py` trava
  isso, e `MicrophoneCaptureService` recusa dispositivo de loopback.
- O roteiro da apresentação fica só na memória, e o log de latência não guarda texto da fala.

### Decisões

- **Microfone no servidor** (PyAudioWPatch), não no navegador: não existe upload de áudio, e o
  servidor local escuta só em `127.0.0.1`.
- **Biblioteca padrão** (`http.server`), sem dependência nova. Como a página liga o microfone,
  o servidor recusa `Host` e `Origin` externos e exige `application/json`, o que bloqueia pedido
  vindo de outro site aberto no navegador.
- **Claude, mesmo com `AI_PROVIDER=gemini`**: o `agy.exe` não tem streaming mapeado neste
  projeto. Sempre pelo login da CLI, sem chave de API e sem `--bare`.
- **CLI pré-aquecida**: `--input-format stream-json` deixa o processo iniciado antes de o pedido
  chegar. Cada processo atende um único pedido, então não acumula contexto nem muda a resposta.

### Resultado medido

Whisper `small` em CUDA, Sonnet, fala sintética de 16 a 18 s e `WHISPER_BEAM_SIZE=1`. Mediana de 3
execuções, em segundos acumulados desde o fim da gravação:

| Caso | Transcrição e métricas | 1ª palavra da IA | Total |
|---|---|---|---|
| Ensaio EN, CLI fria | 0,60 | 2,75 | 5,47 |
| Ensaio EN, CLI aquecida | 0,60 | 2,10 | 5,05 |
| Ensaio PT, CLI aquecida | 0,80 | 7,04 | 10,11 |
| Ensaio PT, `COACH_EFFORT=low` | 0,75 | 5,05 | 7,76 |
| Ensaio PT, `COACH_MODEL=haiku` | 0,66 | 4,99 | 6,92 |
| Apresentação PT, CLI aquecida | 0,78 | 5,60 | 10,50 |

- Em PT, as 3 execuções registradas com blocos geraram `thinking` antes do texto; em EN, nenhuma
  das 3. É isso que afasta PT de EN, e `MAX_THINKING_TOKENS=0` não removeu o bloco.
- Muletas e velocidade são locais e chegam em menos de 1 s, antes da IA, em qualquer idioma.
- `COACH_EFFORT=low` e Haiku não foram adotados, porque trocam qualidade por velocidade. Ficam
  como opção no `.env`, por decisão do Rafael.

### Limitações conhecidas

- A fala sintética não prova que o Whisper preserva muletas de voz humana.
- A regra de não acrescentar conteúdo é só de prompt. Em 1 de 5 ideias testadas, o modelo ainda
  acrescentou um pedido de conversa que não estava na ideia.

### Como reproduzir

```bash
python scripts/benchmark_coach_latency.py <fala.wav> --mode rehearsal --runs 3
python scripts/report_coach_latency.py
```

## D5 — Painel Listen no front-end

**Data**: 2026-11-02
**Status**: ✅ Aplicado (aba Listen em `web/index.html`)

- **Separado do treinador:** a aba consome `/api/meeting/*` e captura só o áudio do sistema. A D4
  continua valendo: o treinador não lê `input_data/` nem usa `AudioCaptureService`.
- **Pontos em vez de roteiro:** o `MEETING_SYSTEM_PROMPT` devolve a pergunta e de 3 a 4 tópicos,
  para a pessoa organizar a ideia e falar com as próprias palavras.
- **Qualquer idioma:** `MEETING_WHISPER_LANGUAGE` vazio detecta o idioma de cada fala, e os tópicos
  seguem o idioma da conversa.
- **Escopo mantido:** o prompt continua sem sugestão quando a transcrição mostra entrevista de
  emprego, teste ou avaliação.
- **Contexto fora do Git:** `input_data/` fica ignorada, exceto arquivos já versionados, porque o
  repositório é público.

## D6 — Contextos e prompt editáveis pela interface

**Data**: 2026-11-02
**Status**: ✅ Aplicado (`services/listen_workspace_service.py`)

- **Onde mora:** os contextos continuam em `input_data/`. A seleção, o prompt personalizado e a
  lixeira ficam em `input_data/.listen/`, sem banco de dados.
- **Parte editável e parte fixa:** a interface edita só `MEETING_INSTRUCTIONS`. A regra de escopo e
  o contexto entram sempre depois, e o texto editável é escapado para não quebrar o `str.format`.
- **Página separada:** `web/index.html`, `web/css/` e `web/js/`. O servidor atende só a lista fechada
  `_ASSETS`, e a CSP deixou de aceitar script inline.
- **Início com um clique:** `run.bat` chama o `run.py`, que sobe o `main.py coach`, espera a API e
  abre o navegador. Ele substituiu `scripts/start_coach.ps1`. O `.bat` existe porque, em 02/11/2026,
  nesta máquina o `.py` está associado ao VS Code (`UserChoice` = `VSCode.py`) e abriria no editor.
