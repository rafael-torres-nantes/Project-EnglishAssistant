#!/usr/bin/env python3
"""Sobe o back-end e abre o front-end com um clique. Feche esta janela para encerrar."""
import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class AppRunner:
    """Inicia o servidor local, espera a API responder e abre o navegador."""

    _HOST = "127.0.0.1"
    _FIRST_PORT = 8778
    _PORT_ATTEMPTS = 10
    _READY_TIMEOUT_SECONDS = 180

    def __init__(self, open_browser: bool = True):
        """Inicializa o executor.

        Args:
            open_browser: Abre o navegador quando o servidor estiver pronto.

        Returns:
            None
        """
        self.open_browser = open_browser

    def probe(self, port: int) -> str:
        """Descobre quem está na porta.

        Args:
            port: Porta local.

        Returns:
            "app" se for este projeto, "other" se for outro programa, "free" se estiver livre.
        """
        try:
            with urllib.request.urlopen(f"http://{self._HOST}:{port}/api/meeting/state", timeout=2) as response:
                return "app" if response.status == 200 else "other"
        except urllib.error.HTTPError:
            return "other"
        except OSError:
            return "free"

    def open_page(self, port: int) -> None:
        """Mostra o endereço e abre o navegador, se pedido.

        Args:
            port: Porta do servidor.

        Returns:
            None
        """
        url = f"http://{self._HOST}:{port}/"
        print(f"Pronto: {url}")
        if self.open_browser:
            webbrowser.open(url)

    def wait_until_ready(self, server: subprocess.Popen, port: int) -> bool:
        """Espera a API responder, sem passar do prazo.

        Args:
            server: Processo do servidor.
            port: Porta do servidor.

        Returns:
            True quando a API responder; False se o processo morrer ou o prazo acabar.
        """
        deadline = time.time() + self._READY_TIMEOUT_SECONDS
        while time.time() < deadline:
            if server.poll() is not None:
                return False
            if self.probe(port) == "app":
                return True
            time.sleep(0.5)
        return False

    def run(self) -> int:
        """Sobe o servidor, ou reaproveita um que já esteja rodando.

        Returns:
            Código de saída do processo.
        """
        port = None
        for candidate in range(self._FIRST_PORT, self._FIRST_PORT + self._PORT_ATTEMPTS):
            state = self.probe(candidate)
            if state == "app":
                print("O assistente já está rodando.")
                self.open_page(candidate)
                return 0
            if state == "free":
                port = candidate
                break
        if port is None:
            print(f"Nenhuma porta livre a partir de {self._FIRST_PORT}.")
            return 1

        print("Iniciando. A primeira carga do modelo de transcrição pode levar até um minuto...")
        server = subprocess.Popen([sys.executable, "main.py", "coach", "--port", str(port)], cwd=ROOT)
        try:
            if not self.wait_until_ready(server, port):
                print("O servidor não respondeu. Veja a mensagem de erro acima.")
                return 1
            self.open_page(port)
            print("Feche esta janela ou pressione Ctrl+C para encerrar.")
            return server.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if server.poll() is None:
                server.terminate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sobe o assistente e abre o navegador")
    parser.add_argument("--no-browser", action="store_true", help="Não abre o navegador")
    arguments = parser.parse_args()
    exit_code = AppRunner(open_browser=not arguments.no_browser).run()
    if exit_code != 0:
        # Com duplo clique, a janela fecharia antes de dar tempo de ler o erro.
        input("Pressione Enter para fechar...")
    sys.exit(exit_code)
