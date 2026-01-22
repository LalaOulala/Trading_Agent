"""
Smoke test de l'API Grok (xAI).

Objectif:
    Vérifier que la clé `XAI_API_KEY` est bien configurée et que l'appel au modèle
    fonctionne (sans logique de trading).

Fonctionnement:
    - Charge un `.env` local (même dossier que ce script).
    - Envoie un prompt simple et affiche la réponse.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user

def main() -> None:
    """
    Point d'entrée du smoke test Grok.

    Effets de bord:
        - Appel réseau vers xAI.
        - Affiche la réponse sur stdout.

    Exceptions:
        RuntimeError: si `XAI_API_KEY` n'est pas définie.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Définis la variable d'env XAI_API_KEY dans ton shell ou dans un fichier .env."
        )

    client = Client(api_key=api_key)

    chat = client.chat.create(model="grok-4-1-fast")
    chat.append(user("What is the meaning of life, the universe, and everything?"))

    response = chat.sample()
    print(response.content)

if __name__ == "__main__":
    main()
