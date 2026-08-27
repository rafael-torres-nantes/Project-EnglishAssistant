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
