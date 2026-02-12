"""
Script de conclusion marché (Tavily web + Grok x_search).

Objectif:
    Produire une conclusion de marché actions (US / S&P 500 par défaut) basée sur des
    faits sourcés:
    - Web: collectés côté script via Tavily (source web principale)
    - X: collectés côté Grok via le tool serveur `x_search` (signaux chauds à recouper)

Organisation:
    - Prompts: `prompts/redaction.txt` et `prompts/presentation.txt`
    - Sorties: un dossier par exécution dans `responses/YYYY-MM-DD_HH-MM-SS/`

Pré-requis:
    - Variables d'environnement `XAI_API_KEY` et `TAVILY_API_KEY`.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user
from xai_sdk.tools import x_search

from trading_pipeline.collectors.tavily_web import TavilyWebCollector


MODEL = "grok-4-1-fast"  # modèle volontairement en dur
MAX_TURNS = 2  # garde-fou coûts: x_search + rédaction
MAX_TOKENS = 1600  # garde-fou coûts: limite la taille de la réponse
X_LOOKBACK_HOURS = 24
MAX_FALLBACK_CITATIONS = 20

TAVILY_QUERY = "S&P 500 market drivers today macro yields earnings sectors premarket"
TAVILY_TOPIC = "finance"
TAVILY_SEARCH_DEPTH = "basic"
TAVILY_TIME_RANGE = "day"
TAVILY_MAX_RESULTS = 8
TAVILY_INCLUDE_DOMAINS: list[str] | None = [
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "investopedia.com",
]
TAVILY_EXCLUDE_DOMAINS: list[str] | None = None
MAX_TAVILY_SIGNALS_IN_PROMPT = 8
MAX_TAVILY_SNIPPET_CHARS = 320

PROMPTS_DIRNAME = "prompts"
REDACTION_PROMPT_FILENAME = "redaction.txt"
PRESENTATION_PROMPT_FILENAME = "presentation.txt"


def _load_env(script_dir: Path) -> None:
    """
    Charge un fichier `.env` local (dans le même dossier que ce script).

    Remarque:
        On ne surcharge pas les variables déjà présentes dans le shell.

    Paramètres:
        script_dir: Dossier contenant ce script.
    """
    env_path = script_dir / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _read_text_file(path: Path) -> str:
    """
    Lit un fichier texte UTF-8 et retourne un contenu non vide.

    Paramètres:
        path: Chemin du fichier à lire.

    Retours:
        Contenu du fichier, avec espaces de début/fin supprimés.

    Exceptions:
        FileNotFoundError: si le fichier n'existe pas.
        ValueError: si le fichier est vide (après `.strip()`).
    """
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Prompt vide: {path}")
    return content


def _ensure_sources_section(
    content: str, citations: list[str], max_citations: int
) -> str:
    """
    Garantit la présence d'une section "Sources" dans le texte final.

    Logique:
        - Si le modèle a déjà inclus une section "Sources", on ne touche à rien.
        - Sinon, si l'API renvoie des `citations`, on ajoute un bloc "Sources :" avec
          des URLs dédupliquées (limitées à `max_citations`).
        - Si une ligne "Note :" existe, on insère "Sources" juste avant pour respecter
          le format demandé (Sources avant Note). Sinon, on ajoute en fin de document.

    Paramètres:
        content: Texte final produit par le modèle.
        citations: Liste d'URLs vues par le modèle (potentiellement avec doublons).
        max_citations: Nombre maximum d'URLs à inclure dans le fallback.

    Retours:
        Le texte final, éventuellement enrichi d'un bloc "Sources :".
    """
    if not citations or "sources" in content.lower():
        return content

    deduped: list[str] = []
    seen: set[str] = set()
    for url in citations:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
        if len(deduped) >= max_citations:
            break

    sources_block = "Sources :\n" + "\n".join(f"- {url}" for url in deduped)
    note_match = re.search(r"\nNote\s*:", content, flags=re.IGNORECASE)
    if not note_match:
        return content + "\n\n" + sources_block

    insert_at = note_match.start()
    return (
        content[:insert_at].rstrip()
        + "\n\n"
        + sources_block
        + "\n\n"
        + content[insert_at:].lstrip()
    )


def _compact_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _truncate(text: str, max_chars: int) -> str:
    clean = _compact_whitespace(text)
    if max_chars <= 0 or len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _collect_tavily_context(tavily_api_key: str) -> tuple[str, list[str], list[str]]:
    """
    Collecte des signaux web via Tavily et formate un bloc texte pour le prompt LLM.

    Retours:
        - bloc texte compact destiné au prompt utilisateur,
        - liste des URLs sources Tavily,
        - notes techniques Tavily.
    """
    collector = TavilyWebCollector(
        api_key=tavily_api_key,
        topic=TAVILY_TOPIC,
        search_depth=TAVILY_SEARCH_DEPTH,
        time_range=TAVILY_TIME_RANGE,
        max_results=TAVILY_MAX_RESULTS,
        include_domains=TAVILY_INCLUDE_DOMAINS,
        exclude_domains=TAVILY_EXCLUDE_DOMAINS,
        include_answer=True,
    )
    collected = collector.collect(TAVILY_QUERY)

    lines: list[str] = []
    urls: list[str] = []
    for idx, signal in enumerate(collected.signals[:MAX_TAVILY_SIGNALS_IN_PROMPT], start=1):
        urls.append(signal.url)
        score = f" | score={signal.score:.3f}" if signal.score is not None else ""
        lines.append(f"{idx}. {signal.title}{score}")
        lines.append(f"   URL: {signal.url}")
        snippet = _truncate(signal.snippet, MAX_TAVILY_SNIPPET_CHARS)
        if snippet:
            lines.append(f"   Extrait: {snippet}")

    if not lines:
        lines.append("(Aucun signal web Tavily exploitable)")

    if collected.notes:
        lines.append("")
        lines.append("Notes Tavily:")
        for note in collected.notes:
            lines.append(f"- {_compact_whitespace(note)}")

    return "\n".join(lines), urls, collected.notes


def main() -> None:
    """
    Lance une exécution complète (recherche + rédaction) et écrit les fichiers de sortie.

    Sorties:
        - `responses/<date_heure>/report.txt` : la conclusion finale
        - `responses/<date_heure>/debug.txt` : métadonnées (usage, tool calls, citations)

    Exceptions:
        RuntimeError: si `XAI_API_KEY` ou les prompts ne sont pas disponibles.
    """
    script_dir = Path(__file__).resolve().parent
    _load_env(script_dir)

    xai_api_key = os.getenv("XAI_API_KEY")
    if not xai_api_key:
        raise RuntimeError(
            "Définis `XAI_API_KEY` dans `.env` (ou dans ton shell) avant de lancer ce script."
        )
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise RuntimeError(
            "Définis `TAVILY_API_KEY` dans `.env` (ou dans ton shell) avant de lancer ce script."
        )

    client = Client(api_key=xai_api_key)

    now = datetime.now(timezone.utc)
    now_utc = now.strftime("%Y-%m-%d %H:%M UTC")
    now_local = now.astimezone()
    now_local_str = now_local.strftime("%Y-%m-%d %H:%M %Z")
    from_date = now - timedelta(hours=X_LOOKBACK_HOURS)

    prompts_dir = script_dir / PROMPTS_DIRNAME
    redaction_prompt_path = prompts_dir / REDACTION_PROMPT_FILENAME
    presentation_prompt_path = prompts_dir / PRESENTATION_PROMPT_FILENAME
    try:
        redaction_prompt = _read_text_file(redaction_prompt_path)
        presentation_prompt = _read_text_file(presentation_prompt_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Prompts introuvables. Attendu:\n"
            f"- {redaction_prompt_path}\n"
            f"- {presentation_prompt_path}\n"
        ) from exc

    try:
        tavily_context, tavily_urls, tavily_notes = _collect_tavily_context(tavily_api_key)
    except Exception as exc:
        raise RuntimeError(
            f"Collecte web Tavily impossible ({type(exc).__name__}: {exc})"
        ) from exc

    user_prompt = f"""
{presentation_prompt}

Informations utiles (pour remplir le titre et cadrer le périmètre) :
- Maintenant (heure locale) : {now_local_str}
- Maintenant (UTC) : {now_utc}
- Fenêtre X : dernières {X_LOOKBACK_HOURS}h (de {from_date.strftime("%Y-%m-%d %H:%M UTC")} à {now_utc})
- Web query Tavily: {TAVILY_QUERY}

Données web (Tavily, base factuelle prioritaire) :
{tavily_context}
""".strip()

    chat = client.chat.create(
        model=MODEL,
        tools=[
            x_search(from_date=from_date, to_date=now),
        ],
        tool_choice="required",
        parallel_tool_calls=False,
        max_turns=MAX_TURNS,
        max_tokens=MAX_TOKENS,
    )
    chat.append(system(redaction_prompt))
    chat.append(user(user_prompt))

    response = chat.sample()

    responses_root_dir = script_dir / "responses"
    responses_root_dir.mkdir(parents=True, exist_ok=True)

    run_dir = responses_root_dir / now_local.strftime("%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    output_path = run_dir / "report.txt"
    content = (response.content or "").strip()
    citations = list(response.citations or [])
    citations.extend(tavily_urls)
    content = _ensure_sources_section(
        content=content, citations=citations, max_citations=MAX_FALLBACK_CITATIONS
    )

    output_path.write_text(content, encoding="utf-8")

    debug_path = run_dir / "debug.txt"
    debug_path.write_text(
        "\n".join(
            [
                f"Model: {MODEL}",
                f"Local: {now_local_str}",
                f"UTC: {now_utc}",
                f"Prompts: {redaction_prompt_path}, {presentation_prompt_path}",
                f"Tavily query: {TAVILY_QUERY}",
                f"Tavily config: topic={TAVILY_TOPIC}, depth={TAVILY_SEARCH_DEPTH}, "
                f"time_range={TAVILY_TIME_RANGE}, max_results={TAVILY_MAX_RESULTS}",
                f"Tavily notes: {tavily_notes}",
                f"Tavily URLs: {tavily_urls}",
                f"Usage: {response.usage}",
                f"Tools used (billed): {response.server_side_tool_usage}",
                f"Tool calls: {response.tool_calls}",
                f"Citations (all URLs seen): {response.citations}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Analyse écrite dans: {output_path}")
    print(f"Debug écrit dans: {debug_path}")
    print("\nCitations (toutes les URLs vues):\n", response.citations)
    print("\nUsage tokens:\n", response.usage)
    print("\nTools utilisés (facturés):\n", response.server_side_tool_usage)
    print("\nDétail des tool calls:\n", response.tool_calls)


if __name__ == "__main__":
    main()
