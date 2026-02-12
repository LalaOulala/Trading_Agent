"""
Exemple minimal pour tester la pertinence du web search avec Tavily.

Usage rapide:
    python tavily_search_example.py \
      --query "S&P 500 market drivers today" \
      --topic finance \
      --time-range day \
      --max-results 8 \
      --include-answer

Pré-requis:
    - Définir `TAVILY_API_KEY` dans `.env` ou dans le shell.
    - Installer la dépendance: `pip install tavily-python`
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv


def _load_env(script_dir: Path) -> None:
    env_path = script_dir / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _split_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or None


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _trusted_hits(results: list[dict[str, Any]], trusted_domains: list[str]) -> tuple[int, int]:
    trusted = {d.lower() for d in trusted_domains}
    hits = 0
    for item in results:
        url = str(item.get("url", ""))
        domain = _domain(url)
        if any(domain == t or domain.endswith(f".{t}") for t in trusted):
            hits += 1
    return hits, len(results)


def _make_client(api_key: str) -> Any:
    try:
        from tavily import TavilyClient
    except Exception as exc:
        raise RuntimeError(
            "Le package `tavily-python` est requis. Installe-le avec: "
            "`python -m pip install tavily-python`."
        ) from exc
    return TavilyClient(api_key=api_key)


def _build_search_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": args.query,
        "topic": args.topic,
        "search_depth": args.search_depth,
        "max_results": args.max_results,
        "include_answer": args.include_answer,
        "include_usage": True,
    }
    if args.time_range != "none":
        kwargs["time_range"] = args.time_range
    if args.include_raw_content != "none":
        kwargs["include_raw_content"] = args.include_raw_content
    include_domains = _split_csv(args.include_domains)
    if include_domains:
        kwargs["include_domains"] = include_domains
    exclude_domains = _split_csv(args.exclude_domains)
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    return kwargs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Teste Tavily Search et imprime un résumé de pertinence."
    )
    parser.add_argument(
        "--query",
        default="S&P 500 market drivers today",
        help="Requête de recherche.",
    )
    parser.add_argument(
        "--topic",
        choices=["general", "news", "finance"],
        default="finance",
        help="Topic Tavily.",
    )
    parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Tradeoff coût/latence/qualité.",
    )
    parser.add_argument(
        "--time-range",
        choices=["none", "day", "week", "month", "year", "d", "w", "m", "y"],
        default="day",
        help="Filtre temporel.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=8,
        help="Nombre max de résultats (0..20).",
    )
    parser.add_argument(
        "--include-answer",
        action="store_true",
        help="Demande un answer LLM côté Tavily.",
    )
    parser.add_argument(
        "--include-raw-content",
        choices=["none", "text", "markdown"],
        default="none",
        help="Inclure le contenu brut (augmente la taille de réponse).",
    )
    parser.add_argument(
        "--include-domains",
        default=None,
        help="Liste CSV de domaines à inclure (ex: reuters.com,bloomberg.com).",
    )
    parser.add_argument(
        "--exclude-domains",
        default=None,
        help="Liste CSV de domaines à exclure.",
    )
    parser.add_argument(
        "--trusted-domains",
        default="reuters.com,bloomberg.com,cnbc.com,wsj.com,investopedia.com",
        help="Liste CSV pour évaluer la pertinence des sources.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Chemin optionnel pour sauvegarder la réponse JSON brute.",
    )
    args = parser.parse_args()

    if args.max_results < 0 or args.max_results > 20:
        raise ValueError("--max-results doit être entre 0 et 20.")

    script_dir = Path(__file__).resolve().parent
    _load_env(script_dir)

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Définis `TAVILY_API_KEY` dans `.env` (ou shell) avant de lancer ce script."
        )

    client = _make_client(api_key=api_key)
    kwargs = _build_search_kwargs(args)
    response = client.search(**kwargs)

    if not isinstance(response, dict):
        raise RuntimeError("Réponse Tavily inattendue: objet JSON attendu.")

    results = response.get("results") or []
    if not isinstance(results, list):
        raise RuntimeError("Réponse Tavily invalide: `results` doit être une liste.")

    trusted_domains = _split_csv(args.trusted_domains) or []
    trusted_hits, total_results = _trusted_hits(results, trusted_domains)
    trusted_ratio = (trusted_hits / total_results) if total_results else 0.0

    print("=== Tavily search summary ===")
    print(f"Query: {args.query}")
    print(f"Topic: {args.topic} | Depth: {args.search_depth} | Time range: {args.time_range}")
    print(f"Results: {total_results}")
    print(f"Response time: {response.get('response_time')}")

    usage = response.get("usage")
    credits = usage.get("credits") if isinstance(usage, dict) else None
    if credits is not None:
        print(f"Credits used: {credits}")

    print(
        f"Trusted-domain hits: {trusted_hits}/{total_results} "
        f"({trusted_ratio:.0%})"
    )
    print("")
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title", "(sans titre)")).strip()
        url = str(item.get("url", "")).strip()
        score = item.get("score")
        print(f"{idx:02d}. score={score} | {title}")
        print(f"    {url}")

    answer = response.get("answer")
    if answer:
        print("\n--- Tavily answer ---")
        print(str(answer).strip())

    if args.out:
        out_path = args.out if args.out.is_absolute() else (script_dir / args.out)
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = script_dir / f"tavily_search_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRéponse brute sauvegardée dans: {out_path}")


if __name__ == "__main__":
    main()
