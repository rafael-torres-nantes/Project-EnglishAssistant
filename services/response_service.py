import logging
from typing import Iterator

from services.claude_cli_service import ClaudeCLIService
from services.gemini_cli_service import GeminiCLIService
from config.settings import Settings
from prompt_template.conversational_prompt import CONVERSATIONAL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ResponseService:
    def __init__(self, provider: str):
        self.provider = provider.lower()
        if self.provider == 'claude':
            self.ai_service = ClaudeCLIService()
        elif self.provider == 'gemini':
            self.ai_service = GeminiCLIService()
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'claude' or 'gemini'.")

    def _build_system_prompt(self, context: str) -> str:
        try:
            return CONVERSATIONAL_SYSTEM_PROMPT.format(meeting_context=context)
        except Exception as e:
            logger.error("Failed to build system prompt: %s", e)
            return f"Context:\n{context}\n\nPlease help the user with their English responses."

    def _build_prompt(self, transcribed_text: str, context: str) -> str:
        return (
            f"[Meeting Audio Transcription]\n{transcribed_text}\n\n"
            f"Based on this meeting conversation, suggest appropriate responses "
            f"I could give in English.\nConsider the context provided in the system prompt."
        )

    def generate_response(self, transcribed_text: str, context: str) -> str:
        try:
            system_prompt = self._build_system_prompt(context)
            prompt = self._build_prompt(transcribed_text, context)
            return self.ai_service.run_text(prompt, system_prompt)
        except Exception as e:
            logger.error("Error generating response: %s", e)
            return f"Error generating response: {str(e)}"

    def generate_response_stream(self, transcribed_text: str, context: str) -> Iterator[str]:
        """Gera a resposta da IA em streaming, repassando os pedaços assim que chegam.

        Args:
            transcribed_text: Texto transcrito da fala capturada na reunião.
            context: Conteúdo de contexto carregado da pasta de contexto.

        Yields:
            Pedaços de texto da resposta da IA.
        """
        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(transcribed_text, context)
        yield from self.ai_service.run_text_stream(prompt, system_prompt)

    def _build_tutor_system_prompt(self, context: str) -> str:
        return (
            "You are an expert English Tutor. The user is practicing English. "
            "Correct their mistakes gently, explain concepts clearly, and keep the conversation engaging. "
            f"Here is some context about the user's current studies or focus:\n\n{context}"
        )

    def generate_tutor_response(self, user_text: str, context: str) -> str:
        try:
            system_prompt = self._build_tutor_system_prompt(context)
            return self.ai_service.run_text(user_text, system_prompt)
        except Exception as e:
            logger.error("Error generating tutor response: %s", e)
            return f"Error generating response: {str(e)}"

    def generate_tutor_response_stream(self, user_text: str, context: str) -> Iterator[str]:
        system_prompt = self._build_tutor_system_prompt(context)
        yield from self.ai_service.run_text_stream(user_text, system_prompt)

    def stop(self) -> None:
        logger.info("Response service stopped.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
