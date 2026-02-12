"""
Smoke test de l'API Alpaca (paper par défaut).

Objectif:
    Valider rapidement que les clés Alpaca sont correctes et que l'API répond,
    sans effectuer d'ordres (appels read-only).

Fonctionnement:
    - Charge les credentials depuis le fichier `.env` à la racine du repo.
    - Appelle quelques endpoints simples (account, clock, positions).

Variables d'environnement (recommandées):
    - `ALPACA_API_KEY`
    - `ALPACA_API_SECRET`
    - `ALPACA_PAPER=true|false` (optionnel, défaut: true)

Variables alternatives (compatibilité):
    - `APCA_API_KEY_ID`
    - `APCA_API_SECRET_KEY`
    - `ALPACA_SECRET`
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from alpaca.trading.client import TradingClient
from dotenv import load_dotenv


def _load_env() -> None:
    """
    Charge le fichier `.env` à la racine du repo.

    Effets de bord:
        - Remplit `os.environ` (sans écraser les variables déjà définies dans le shell).
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _get_env_value(names: list[str]) -> str | None:
    """
    Retourne la première variable d'environnement non vide parmi `names`.

    Paramètres:
        names: Liste ordonnée de noms de variables d'environnement à tester.

    Retours:
        La première valeur non vide trouvée, sinon `None`.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _get_required_credentials() -> tuple[str, str]:
    """
    Résout la clé et le secret Alpaca depuis l'environnement.

    Retours:
        Un tuple `(api_key, api_secret)`.

    Exceptions:
        RuntimeError: si les variables requises ne sont pas présentes.
    """
    api_key = _get_env_value(["ALPACA_API_KEY", "APCA_API_KEY_ID"])
    api_secret = _get_env_value(
        ["ALPACA_API_SECRET", "ALPACA_SECRET", "APCA_API_SECRET_KEY"]
    )

    if not api_key or not api_secret:
        raise RuntimeError(
            "Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_API_SECRET "
            "in .env (or APCA_API_KEY_ID / APCA_API_SECRET_KEY)."
        )
    return api_key, api_secret


def _get_paper_flag() -> bool:
    """
    Détermine si on utilise l'environnement paper.

    Source:
        - `ALPACA_PAPER` (par défaut `"true"`).

    Retours:
        `True` si paper, `False` si live.
    """
    raw = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    return raw not in {"0", "false", "no"}


@dataclass
class AlpacaApiTester:
    """
    Wrapper minimal (read-only) pour vérifier la connectivité Alpaca.

    Cette classe existe surtout pour structurer le script et rendre le "test"
    explicite: on instancie, puis on appelle `run()`.
    """

    api_key: str
    api_secret: str
    paper: bool = True

    def run(self) -> None:
        """
        Exécute le smoke test et affiche un résumé.

        Effets de bord:
            Écrit sur stdout (console).

        Notes:
            Les appels effectués sont read-only (pas d'ordres).
        """
        client = TradingClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
            paper=self.paper,
        )

        account = client.get_account()
        clock = client.get_clock()
        positions = client.get_all_positions()

        print("Alpaca connection OK")
        print(f"Paper: {self.paper}")
        print(f"Account status: {account.status}")
        print(f"Cash: ${account.cash}")
        print(f"Equity: ${account.equity}")
        print(f"Buying power: ${account.buying_power}")
        print(f"Market open: {clock.is_open}")
        print(f"Open positions: {len(positions)}")


def main() -> None:
    """
    Point d'entrée du script de smoke test.

    Rôle:
        - charge `.env`
        - lit les credentials
        - instancie `AlpacaApiTester` et exécute le test
    """
    _load_env()
    api_key, api_secret = _get_required_credentials()
    paper = _get_paper_flag()

    tester = AlpacaApiTester(api_key=api_key, api_secret=api_secret, paper=paper)
    tester.run()


if __name__ == "__main__":
    main()
