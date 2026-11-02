import logging
import re

from config.settings import Settings

logger = logging.getLogger(__name__)


class SpeechAnalysisService:
    """Calcula muletas, velocidade e pausas a partir das palavras transcritas, sem IA."""

    _ALWAYS = {
        "en": {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "hm", "mm", "basically", "literally", "actually", "you know", "i mean", "kind of", "sort of"},
        "pt": {"hum", "hmm", "hm", "ãh", "ahn", "éh", "eh", "ah", "né", "basicamente", "meio que", "na verdade", "tipo assim", "tipo"},
    }
    # Palavras com sentido próprio: só contam como muleta quando a pontuação indica marcador de discurso.
    _ONLY_AS_MARKER = {
        "en": {"so", "right", "well", "okay", "ok"},
        "pt": {"é", "então", "assim", "bom", "sabe", "tá", "cara", "aí", "daí", "mano", "entendeu", "beleza", "certo"},
    }
    _NOT_FILLER_AFTER = {
        "like": {"i", "we", "you", "they", "would", "really", "dont", "didnt", "look", "looks", "looked", "sound", "sounds", "feel", "feels", "something", "just"},
        "kind of": {"a", "this", "that", "what", "which", "any", "some"},
        "sort of": {"a", "this", "that", "what", "which", "any", "some"},
    }
    _NOT_FILLER_BEFORE = {"tipo": {"de", "do", "da"}}
    _MARKER_PUNCTUATION = (",", "...", "…", "?")
    _MAX_PHRASE_WORDS = 2

    @staticmethod
    def normalize(word: str) -> str:
        """
        Normaliza uma palavra para comparação, sem pontuação e em minúsculas.

        Args:
            word: Palavra como veio da transcrição.

        Returns:
            Palavra normalizada.
        """
        return re.sub(r"[^\w]", "", word.lower())

    def is_filler(self, term: str, previous: str, following: str, raw: str, language: str) -> bool:
        """
        Decide se um termo é muleta considerando as palavras vizinhas.

        Args:
            term: Termo normalizado, de uma ou duas palavras.
            previous: Palavra normalizada anterior ao termo.
            following: Palavra normalizada posterior ao termo.
            raw: Texto original do termo, com pontuação.
            language: Idioma detectado ("en" ou "pt"); outro valor considera os dois.

        Returns:
            True se o termo for muleta.
        """
        languages = [language] if language in self._ALWAYS else list(self._ALWAYS)
        if previous in self._NOT_FILLER_AFTER.get(term, set()):
            return False
        if following in self._NOT_FILLER_BEFORE.get(term, set()):
            return False
        if term == "like" and "en" in languages:
            return True
        if any(term in self._ALWAYS[item] for item in languages):
            return True
        is_marker = any(term in self._ONLY_AS_MARKER[item] for item in languages)
        return is_marker and raw.strip().endswith(self._MARKER_PUNCTUATION)

    def analyze(self, words: list[dict], language: str) -> dict:
        """
        Marca muletas e calcula as métricas de uma fala.

        A velocidade usa o trecho entre a primeira e a última palavra, então silêncio antes e
        depois da fala não a distorce.

        Args:
            words: Palavras com "text", "start" e "end" em segundos.
            language: Idioma detectado na transcrição.

        Returns:
            Dicionário com as palavras marcadas, a contagem por muleta e as métricas.
        """
        marked = [{"text": word["text"], "filler": False} for word in words]
        tokens = [self.normalize(word["text"]) for word in words]
        fillers = {}
        index = 0
        while index < len(tokens):
            size = self.match_size(tokens, words, index, language)
            if size:
                term = " ".join(tokens[index:index + size])
                fillers[term] = fillers.get(term, 0) + 1
                for position in range(index, index + size):
                    marked[position]["filler"] = True
                index += size
                continue
            if index > 0 and tokens[index] and tokens[index] == tokens[index - 1]:
                fillers["repetição"] = fillers.get("repetição", 0) + 1
                marked[index]["filler"] = True
            index += 1
        return {"words": marked, "fillers": fillers, **self.measure(words, sum(fillers.values()))}

    def match_size(self, tokens: list[str], words: list[dict], index: int, language: str) -> int:
        """
        Procura a maior muleta que começa na posição informada.

        Args:
            tokens: Palavras normalizadas.
            words: Palavras originais.
            index: Posição inicial.
            language: Idioma detectado.

        Returns:
            Quantidade de palavras da muleta; 0 se não houver.
        """
        previous = tokens[index - 1] if index else ""
        for size in range(self._MAX_PHRASE_WORDS, 0, -1):
            if index + size > len(tokens):
                continue
            term = " ".join(tokens[index:index + size])
            following = tokens[index + size] if index + size < len(tokens) else ""
            raw = words[index + size - 1]["text"]
            if self.is_filler(term, previous, following, raw, language):
                return size
        return 0

    @staticmethod
    def measure(words: list[dict], filler_total: int) -> dict:
        """
        Calcula velocidade e pausas.

        Args:
            words: Palavras com "start" e "end" em segundos.
            filler_total: Total de muletas encontradas.

        Returns:
            Dicionário com as métricas numéricas da fala.
        """
        metrics = {"word_count": len(words), "filler_total": filler_total, "speaking_seconds": 0.0, "words_per_minute": 0, "fillers_per_minute": 0.0, "long_pauses": 0, "longest_pause_seconds": 0.0}
        if not words:
            return metrics
        speaking = max(words[-1]["end"] - words[0]["start"], 0.001)
        gaps = [after["start"] - before["end"] for before, after in zip(words, words[1:])]
        metrics["speaking_seconds"] = round(speaking, 1)
        metrics["words_per_minute"] = round(len(words) / speaking * 60)
        metrics["fillers_per_minute"] = round(filler_total / speaking * 60, 1)
        metrics["long_pauses"] = sum(1 for gap in gaps if gap >= Settings.COACH_LONG_PAUSE_SECONDS)
        metrics["longest_pause_seconds"] = round(max(gaps, default=0.0), 1)
        return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = [{"text": " so,", "start": 0.0, "end": 0.3}, {"text": " um", "start": 0.4, "end": 0.6}, {"text": " deploy", "start": 0.7, "end": 1.0}]
    logger.info("Teste local: %s", SpeechAnalysisService().analyze(sample, "en"))
