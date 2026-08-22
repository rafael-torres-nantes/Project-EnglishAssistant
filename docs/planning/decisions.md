# Decisões Técnicas

## D1 — CLAUDE_MODEL padrão trocado de `haiku` para `sonnet`

**Data**: 2026-08-22
**Status**: ✅ Aplicado (`.env`)

### Contexto

`R4` (`risks.md`) apontava latência alta entre transcrição e resposta como risco aberto.
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

A expectativa era que Haiku fosse o mais rápido por ser o modelo menor. O README já
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
