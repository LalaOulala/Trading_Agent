"""
Orchestrateur du workflow (recherche -> trader).

Étapes par défaut:
    1) `grok_tools_test.py`       -> écrit `responses/<run>/report.txt`
    2) `reflex_trader_agent.py`   -> écrit `reflex_trader/<run>.txt`

Objectif:
    - Lancer le workflow en une commande, avec un affichage CLI concis.
    - Les détails restent dans les fichiers `.txt` générés.

Pré-requis:
    - Variables d'env: `XAI_API_KEY` (et, optionnellement, clés Alpaca si `--fetch-prices`).

Notes:
    - Ce script ne crée pas d'ordres (il ne fait que orchestrer recherche + trader).
    - En cas d'échec, il affiche un message court. Utilise `--verbose` pour debug complet.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def _ellipsize(text: str, max_chars: int) -> str:
    """
    Réduit un texte à une taille maximale (utile pour un affichage CLI concis).

    Comportement:
        - Compacte les espaces (whitespace) en une seule espace.
        - Si `max_chars <= 0`, retourne une chaîne vide.
        - Si tronqué, ajoute un caractère de fin `…`.

    Paramètres:
        text: Texte à afficher.
        max_chars: Longueur maximale en caractères.

    Retours:
        Le texte compacté, éventuellement tronqué.
    """
    if max_chars <= 0:
        return ""
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _resolve_repo_path(path: Path, *, repo_root: Path) -> Path:
    """
    Résout un chemin CLI relatif par rapport à la racine du repo.

    Pourquoi:
        `run.py` peut être exécuté depuis un autre CWD. Sans cette normalisation,
        les chemins par défaut (`responses`, `reflex_trader`) peuvent pointer vers
        le mauvais dossier.
    """
    return path if path.is_absolute() else (repo_root / path)


def _run(cmd: list[str], *, verbose: bool) -> None:
    """
    Exécute une commande en sous-process.

    Modes:
        - Par défaut (`verbose=False`): capture la sortie et n’affiche que les erreurs (tail).
        - Verbose (`verbose=True`): affiche la commande et laisse le sous-process écrire sur
          stdout/stderr (utile pour debug).

    Paramètres:
        cmd: Liste d'arguments de commande (sans shell).
        verbose: Active le mode verbeux.

    Effets de bord:
        Écrit sur stdout/stderr.

    Exceptions:
        subprocess.CalledProcessError: si le sous-process retourne un code != 0.
    """
    pretty = " ".join(shlex.quote(c) for c in cmd)
    if verbose:
        print(f"\n=== {pretty} ===\n")
        subprocess.run(cmd, check=True)
        return

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        print(f"Command failed: {pretty}")
        if stdout:
            print("\n--- stdout (tail) ---")
            print("\n".join(stdout.splitlines()[-30:]))
        if stderr:
            print("\n--- stderr (tail) ---")
            print("\n".join(stderr.splitlines()[-30:]))
        raise


def _ensure_non_empty_file(path: Path, label: str) -> Path:
    """
    Valide l'existence d'un fichier et son contenu non vide.

    Paramètres:
        path: Chemin du fichier.
        label: Libellé utilisé dans les messages d'erreur.

    Retours:
        Le `path` (pratique pour chaîner).

    Exceptions:
        FileNotFoundError: si le fichier n'existe pas.
        ValueError: si le fichier existe mais est vide (`st_size == 0`).
    """
    if not path.exists():
        raise FileNotFoundError(f"{label} introuvable: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"{label} vide: {path}")
    return path


def _latest_research_report(responses_dir: Path) -> Path:
    """
    Retourne le report "recherche" le plus récent dans un dossier `responses/`.

    Convention attendue (créée par `grok_tools_test.py`):
        - `responses/<run>/report.txt` où `<run>` est un dossier horodaté.

    Paramètres:
        responses_dir: Dossier racine `responses/`.

    Retours:
        Chemin vers `report.txt`.

    Exceptions:
        FileNotFoundError: si le dossier ou aucun report valide n'est trouvé.
    """
    if not responses_dir.exists():
        raise FileNotFoundError(f"Dir responses introuvable: {responses_dir}")

    run_dirs = sorted([p for p in responses_dir.iterdir() if p.is_dir()], reverse=True)
    for run_dir in run_dirs:
        report = run_dir / "report.txt"
        if report.exists() and report.stat().st_size > 0:
            return report
    raise FileNotFoundError(f"Aucun report trouvé dans: {responses_dir}")


def _latest_trader_report(reflex_dir: Path) -> Path:
    """
    Retourne la sortie trader (`.txt`) la plus récente dans `reflex_trader/`.

    Convention attendue (créée par `reflex_trader_agent.py`):
        - `reflex_trader/YYYY-MM-DD_HH-MM-SS.txt`

    Paramètres:
        reflex_dir: Dossier racine `reflex_trader/`.

    Retours:
        Chemin vers le fichier `.txt` le plus récent non vide.

    Exceptions:
        FileNotFoundError: si le dossier ou aucun fichier `.txt` non vide n'est trouvé.
    """
    if not reflex_dir.exists():
        raise FileNotFoundError(f"Dir reflex_trader introuvable: {reflex_dir}")

    files = sorted([p for p in reflex_dir.iterdir() if p.is_file() and p.suffix == ".txt"])
    for path in reversed(files):
        if path.stat().st_size > 0:
            return path
    raise FileNotFoundError(f"Aucune sortie trader trouvée dans: {reflex_dir}")


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    """
    Extrait et parse les objets JSON trouvés dans un texte (robuste aux pré/post textes).

    But:
        Les fichiers de sortie des agents peuvent contenir du texte autour du JSON.
        On cherche donc des blocs `{...}` équilibrés et on tente `json.loads`.

    Paramètres:
        text: Contenu brut contenant potentiellement du JSON.

    Retours:
        Une liste d'objets JSON (dict) trouvés dans l'ordre d'apparition.

    Notes:
        - Ne retourne que des objets (dict), pas les arrays JSON racines.
        - Ignore silencieusement les blocs `{...}` non parseables.
    """
    objects: list[dict[str, Any]] = []

    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break

        depth = 0
        in_string = False
        escape = False
        end: int | None = None

        for j in range(start, len(text)):
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break

        if end is None:
            break

        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except Exception:
            i = end + 1
            continue

        if isinstance(parsed, dict):
            objects.append(parsed)
        i = end + 1

    return objects


def _extract_first_object_with_keys(text: str, keys: set[str]) -> dict[str, Any] | None:
    """
    Retourne le premier objet JSON d'un texte qui contient toutes les clés demandées.

    Paramètres:
        text: Contenu dans lequel chercher du JSON.
        keys: Ensemble de clés requises.

    Retours:
        Le premier `dict` JSON qui contient toutes les clés, sinon `None`.
    """
    for obj in _extract_json_objects(text):
        if all(k in obj for k in keys):
            return obj
    return None


def _research_title(report_path: Path) -> str | None:
    """
    Extrait un titre concis depuis un report recherche.

    Stratégie:
        Prend la première ligne non vide du fichier (souvent: "Titre : ...").

    Paramètres:
        report_path: Chemin vers `responses/*/report.txt`.

    Retours:
        Le titre (première ligne) ou `None` si lecture impossible.
    """
    try:
        first_line = _ensure_non_empty_file(report_path, "Report recherche").read_text(
            encoding="utf-8"
        ).splitlines()[0]
        return first_line.strip() if first_line.strip() else None
    except Exception:
        return None


def _trader_summary(trader_report_path: Path) -> tuple[str | None, list[str] | None]:
    """
    Extrait un résumé minimal depuis la sortie de l'agent trader.

    Informations extraites:
        - `portfolio_available`: depuis la section "Inputs" (ligne `- Portfolio available: ...`).
        - `requested_symbols`: depuis le premier JSON contenant `requested_market_data`.

    Paramètres:
        trader_report_path: Chemin vers `reflex_trader/*.txt`.

    Retours:
        Tuple `(portfolio_available, requested_symbols)`, chaque champ pouvant être `None`.

    Exceptions:
        FileNotFoundError / ValueError: si le fichier n'existe pas ou est vide.
    """
    text = _ensure_non_empty_file(trader_report_path, "Report trader").read_text(
        encoding="utf-8"
    )

    portfolio_available: str | None = None
    m = re.search(r"(?m)^- Portfolio available:\s*(.+)\s*$", text)
    if m:
        portfolio_available = m.group(1).strip()

    symbols: list[str] = []
    trader_obj = _extract_first_object_with_keys(text, {"requested_market_data"})
    if trader_obj and isinstance(trader_obj.get("requested_market_data"), list):
        for item in trader_obj["requested_market_data"]:
            if isinstance(item, dict) and isinstance(item.get("symbol"), str):
                sym = item["symbol"].strip()
                if sym:
                    symbols.append(sym)

    return portfolio_available, (symbols or None)


def main() -> None:
    """
    Point d'entrée CLI.

    Rôle:
        - Lance `grok_tools_test.py` (sauf `--skip-research`) et récupère le dernier report.
        - Lance `reflex_trader_agent.py` (sauf `--skip-trader`) et récupère la dernière sortie.
        - Affiche un résumé court (chemins + titre + symboles demandés).

    Codes de sortie:
        - 0: succès
        - 1: échec (message court). Utilise `--verbose` pour voir l'erreur complète.
    """
    parser = argparse.ArgumentParser(
        description="Lance le workflow complet: recherche -> trader (affichage CLI concis)."
    )
    parser.add_argument(
        "--responses-dir",
        type=Path,
        default=Path("responses"),
        help="Répertoire contenant les runs de reports (`responses/YYYY.../report.txt`).",
    )
    parser.add_argument(
        "--reflex-dir",
        type=Path,
        default=Path("reflex_trader"),
        help="Répertoire contenant les sorties de l'agent trader (`reflex_trader/*.txt`).",
    )

    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Ne lance pas `grok_tools_test.py` (utilise un report existant).",
    )
    parser.add_argument(
        "--skip-trader",
        action="store_true",
        help="Ne lance pas `reflex_trader_agent.py` (utilise une sortie existante).",
    )
    parser.add_argument(
        "--research-report",
        type=Path,
        default=None,
        help="Chemin vers un `responses/*/report.txt` existant (sinon: dernier).",
    )
    parser.add_argument(
        "--trader-report",
        type=Path,
        default=None,
        help="Chemin vers une sortie `reflex_trader/*.txt` existante (sinon: dernière).",
    )

    parser.add_argument(
        "--reports-count",
        type=int,
        default=1,
        help="(Trader) Nombre de reports récents à inclure.",
    )
    parser.add_argument(
        "--analysis-file",
        type=Path,
        default=None,
        help="(Trader) Fichier analyse derniers jours.",
    )
    parser.add_argument(
        "--fetch-prices",
        action="store_true",
        help="(Trader) Récupère aussi les prix via Alpaca Market Data.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Affiche les commandes exécutées et la sortie des sous-scripts.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    responses_dir = _resolve_repo_path(args.responses_dir, repo_root=root)
    reflex_dir = _resolve_repo_path(args.reflex_dir, repo_root=root)
    research_report_arg = (
        _resolve_repo_path(args.research_report, repo_root=root)
        if args.research_report
        else None
    )
    trader_report_arg = (
        _resolve_repo_path(args.trader_report, repo_root=root)
        if args.trader_report
        else None
    )
    analysis_file_arg = (
        _resolve_repo_path(args.analysis_file, repo_root=root)
        if args.analysis_file
        else None
    )

    try:
        # --- Step 1: recherche ---
        if research_report_arg:
            research_report = _ensure_non_empty_file(research_report_arg, "Report recherche")
        else:
            if not args.skip_research:
                print("[Research] running…")
                _run([sys.executable, str(root / "grok_tools_test.py")], verbose=args.verbose)
            research_report = _latest_research_report(responses_dir)

        title = _research_title(research_report)
        print(
            f"[Research] {'skipped' if args.skip_research and not args.research_report else 'done'} -> {research_report}"
            + (f" | {_ellipsize(title, 120)}" if title else "")
        )

        # --- Step 2: trader ---
        if trader_report_arg:
            trader_report = _ensure_non_empty_file(trader_report_arg, "Report trader")
        else:
            if not args.skip_trader:
                trader_cmd = [
                    sys.executable,
                    str(root / "reflex_trader_agent.py"),
                    "--responses-dir",
                    str(responses_dir),
                    "--reports-count",
                    str(args.reports_count),
                    "--out-dir",
                    str(reflex_dir),
                ]
                if analysis_file_arg:
                    trader_cmd += ["--analysis-file", str(analysis_file_arg)]
                if args.fetch_prices:
                    trader_cmd += ["--fetch-prices"]

                print("[Trader] running…")
                _run(trader_cmd, verbose=args.verbose)

            trader_report = _latest_trader_report(reflex_dir)

        portfolio_available, requested_symbols = _trader_summary(trader_report)
        bits: list[str] = []
        if portfolio_available is not None:
            bits.append(f"portfolio={portfolio_available}")
        if requested_symbols:
            bits.append(f"requested symbols: {', '.join(requested_symbols[:10])}")

        print(
            f"[Trader] {'skipped' if args.skip_trader and not args.trader_report else 'done'} -> {trader_report}"
            + (f" | {' | '.join(bits)}" if bits else "")
        )

        print("\n=== Outputs ===")
        print(f"- Research report: {research_report}")
        print(f"- Trader report: {trader_report}")
    except Exception as exc:
        if args.verbose:
            raise
        print(f"\nWorkflow FAILED: {exc}")
        if isinstance(exc, FileNotFoundError):
            print(
                "Hint: vérifie les chemins inputs/outputs "
                f"(responses={responses_dir}, reflex_trader={reflex_dir}) "
                "ou relance sans --skip-research/--skip-trader."
            )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
