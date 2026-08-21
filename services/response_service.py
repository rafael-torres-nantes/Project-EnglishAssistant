import logging
from services.claude_cli_service import ClaudeCLIService
from services.gemini_cli_service import GeminiCLIService
from config.settings import Settings

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
            return Settings.SYSTEM_PROMPT_TEMPLATE.format(meeting_context=context)
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

    def stop(self) -> None:
        logger.info("Response service stopped.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
