"""
Orchestrateur du workflow complet (recherche -> trader -> chef).

Étapes par défaut:
    1) `grok_tools_test.py`       -> écrit `responses/<run>/report.txt`
    2) `reflex_trader_agent.py`   -> écrit `reflex_trader/<run>.txt`
    3) `grok_chef_agent.py`       -> écrit `grok_chef/<run>.txt` (+ soumission ordres optionnelle)

Usage:
    - `python run.py` (dry-run côté Grok Chef)
    - `python run.py --execute` (soumet des ordres en paper, si approuvé par Grok Chef)
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandResult:
    cmd: list[str]
    stdout: str
    stderr: str


def _ellipsize(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _run(cmd: list[str], *, verbose: bool) -> CommandResult:
    pretty = " ".join(shlex.quote(c) for c in cmd)
    if verbose:
        print(f"\n=== {pretty} ===\n")
    try:
        completed = subprocess.run(
            cmd, check=True, capture_output=True, text=True, encoding="utf-8"
        )
    except subprocess.CalledProcessError as exc:
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        print("Command failed:", pretty)
        if stdout:
            print("\n--- stdout (tail) ---")
            print("\n".join(stdout.splitlines()[-30:]))
        if stderr:
            print("\n--- stderr (tail) ---")
            print("\n".join(stderr.splitlines()[-30:]))
        raise

    return CommandResult(
        cmd=cmd,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip(),
    )


def _ensure_non_empty_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} introuvable: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"{label} vide: {path}")
    return path


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    env_path = root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _extract_json_values(text: str) -> list[Any]:
    """
    Extrait et parse des valeurs JSON (objets ou arrays) trouvées dans un texte.

    Stratégie:
        - scan en respectant les chaînes JSON
        - détecte `{` ou `[` puis extrait jusqu'au niveau 0
        - tente `json.loads`
    """
    values: list[Any] = []

    i = 0
    while i < len(text):
        start_obj = text.find("{", i)
        start_arr = text.find("[", i)
        candidates = [p for p in [start_obj, start_arr] if p != -1]
        if not candidates:
            break
        start = min(candidates)

        obj_depth = 0
        arr_depth = 0
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
                obj_depth += 1
            elif ch == "}":
                obj_depth -= 1
            elif ch == "[":
                arr_depth += 1
            elif ch == "]":
                arr_depth -= 1

            if obj_depth == 0 and arr_depth == 0 and j > start:
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

        values.append(parsed)
        i = end + 1

    return values


def _extract_first_object_with_keys(text: str, keys: set[str]) -> dict[str, Any] | None:
    for value in _extract_json_values(text):
        if not isinstance(value, dict):
            continue
        if all(k in value for k in keys):
            return value
    return None


def _alpaca_portfolio_summary() -> tuple[dict[str, Any] | None, str | None]:
    api_key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
    api_secret = (
        os.environ.get("ALPACA_API_SECRET")
        or os.environ.get("ALPACA_SECRET")
        or os.environ.get("APCA_API_SECRET_KEY")
    )
    if not api_key or not api_secret:
        return None, "credentials Alpaca manquants"

    paper_raw = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    paper = paper_raw not in {"0", "false", "no"}

    try:
        from alpaca.trading.client import TradingClient
    except Exception:
        return None, "lib alpaca-py indisponible"

    try:
        client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
        account = client.get_account()
        positions = client.get_all_positions()
    except Exception as exc:
        return None, f"erreur Alpaca: {exc}"

    pos_items: list[dict[str, Any]] = []
    for p in positions:
        pos_items.append(
            {
                "symbol": getattr(p, "symbol", None),
                "qty": getattr(p, "qty", None),
                "market_value": getattr(p, "market_value", None),
                "unrealized_pl": getattr(p, "unrealized_pl", None),
            }
        )

    return (
        {
            "paper": paper,
            "cash": getattr(account, "cash", None),
            "equity": getattr(account, "equity", None),
            "buying_power": getattr(account, "buying_power", None),
            "positions": pos_items,
        },
        None,
    )


def _latest_research_report(responses_dir: Path) -> Path:
    if not responses_dir.exists():
        raise FileNotFoundError(f"Dir responses introuvable: {responses_dir}")

    run_dirs = [p for p in responses_dir.iterdir() if p.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"Aucun run trouvé dans: {responses_dir}")

    run_dir = max(run_dirs, key=lambda p: p.stat().st_mtime)
    report = run_dir / "report.txt"
    return _ensure_non_empty_file(report, "Report recherche")


def _latest_txt_file(directory: Path, label: str) -> Path:
    if not directory.exists():
        raise FileNotFoundError(f"{label} dir introuvable: {directory}")

    files = [p for p in directory.iterdir() if p.is_file() and p.suffix == ".txt"]
    if not files:
        raise FileNotFoundError(f"Aucun fichier .txt trouvé dans: {directory}")

    path = max(files, key=lambda p: p.stat().st_mtime)
    return _ensure_non_empty_file(path, label)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lance le workflow complet: recherche -> trader -> chef."
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
        "--skip-chef",
        action="store_true",
        help="Ne lance pas `grok_chef_agent.py`.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Affiche les commandes exécutées (sinon: affichage concis).",
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
        "--trader-json",
        type=Path,
        default=None,
        help="Optionnel: JSON direct de l'agent trader (utilisé par Grok Chef).",
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
        "--execute",
        action="store_true",
        help="(Chef) Soumet les ordres à Alpaca (sinon: dry-run).",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="(Chef) Autorise l'exécution live si `ALPACA_PAPER=false` (avec --execute).",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        default=5,
        help="(Chef) Limite: nombre max d'ordres.",
    )
    parser.add_argument(
        "--max-notional-per-order-usd",
        type=str,
        default="250",
        help="(Chef) Limite: notional max estimé par ordre (USD).",
    )
    parser.add_argument(
        "--max-total-notional-usd",
        type=str,
        default="500",
        help="(Chef) Limite: notional total max estimé (USD).",
    )
    parser.add_argument(
        "--allow-shorts",
        action="store_true",
        help="(Chef) Autorise le short (désactivé par défaut).",
    )

    args = parser.parse_args()

    try:
        root = Path(__file__).resolve().parent
        _load_env(root)

        responses_dir = root / "responses"
        reflex_dir = root / "reflex_trader"
        chef_dir = root / "grok_chef"

        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Workflow start: {started_at}")

        # --- Step 1: recherche ---
        research_report: Path | None = None
        if args.research_report:
            research_report = _ensure_non_empty_file(args.research_report, "Report recherche")
        else:
            if not args.skip_research:
                print("[Research] running…")
                _run([sys.executable, str(root / "grok_tools_test.py")], verbose=args.verbose)
            research_report = _latest_research_report(responses_dir)

        research_title = None
        try:
            first_line = _ensure_non_empty_file(research_report, "Report recherche").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            research_title = first_line.strip() if first_line.strip() else None
        except Exception:
            research_title = None

        print(
            f"[Research] {'skipped' if args.skip_research and not args.research_report else 'done'} -> {research_report}"
            + (f" | {_ellipsize(research_title, 120)}" if research_title else "")
        )

        # --- Step 2: trader ---
        trader_report: Path | None = None
        if args.trader_report:
            trader_report = _ensure_non_empty_file(args.trader_report, "Report trader")
        else:
            if not args.skip_trader:
                trader_cmd = [
                    sys.executable,
                    str(root / "reflex_trader_agent.py"),
                    "--responses-dir",
                    str(responses_dir),
                    "--reports-count",
                    str(args.reports_count),
                ]
                if args.analysis_file:
                    trader_cmd += ["--analysis-file", str(args.analysis_file)]
                if args.fetch_prices:
                    trader_cmd += ["--fetch-prices"]
                print("[Trader] running…")
                _run(trader_cmd, verbose=args.verbose)
            if not args.trader_json:
                trader_report = _latest_txt_file(reflex_dir, "Report trader")

        trader_requested_symbols: list[str] | None = None
        if args.trader_json:
            try:
                raw = _ensure_non_empty_file(args.trader_json, "Trader JSON").read_text(
                    encoding="utf-8"
                )
                trader_obj = json.loads(raw)
                rmd = (
                    trader_obj.get("requested_market_data", [])
                    if isinstance(trader_obj, dict)
                    else []
                )
                symbols: list[str] = []
                if isinstance(rmd, list):
                    for item in rmd:
                        if isinstance(item, dict) and isinstance(item.get("symbol"), str):
                            symbols.append(item["symbol"])
                trader_requested_symbols = symbols or None
            except Exception:
                trader_requested_symbols = None
        else:
            try:
                trader_text = _ensure_non_empty_file(trader_report, "Report trader").read_text(
                    encoding="utf-8"
                )
                trader_obj = _extract_first_object_with_keys(
                    trader_text, {"requested_market_data", "pedagogical_conclusion"}
                )
                if trader_obj and isinstance(trader_obj.get("requested_market_data"), list):
                    symbols = []
                    for item in trader_obj["requested_market_data"]:
                        if isinstance(item, dict) and isinstance(item.get("symbol"), str):
                            symbols.append(item["symbol"])
                    trader_requested_symbols = symbols or None
            except Exception:
                trader_requested_symbols = None

        trader_label = (
            "skipped"
            if args.skip_trader and not args.trader_report and not args.trader_json
            else "done"
        )
        trader_out = args.trader_json if args.trader_json else trader_report
        print(
            f"[Trader] {trader_label} -> {trader_out}"
            + (
                f" | requested symbols: {', '.join(trader_requested_symbols[:12])}"
                if trader_requested_symbols
                else ""
            )
        )

        # --- Step 3: chef ---
        chef_report: Path | None = None
        if not args.skip_chef:
            chef_cmd = [
                sys.executable,
                str(root / "grok_chef_agent.py"),
                "--research-report",
                str(research_report),
                "--max-orders",
                str(args.max_orders),
                "--max-notional-per-order-usd",
                str(args.max_notional_per_order_usd),
                "--max-total-notional-usd",
                str(args.max_total_notional_usd),
            ]
            if args.trader_json:
                chef_cmd += ["--trader-json", str(args.trader_json)]
            else:
                if not trader_report:
                    raise RuntimeError(
                        "Aucun input trader disponible. Fournis `--trader-json` ou génère un report trader."
                    )
                chef_cmd += ["--trader-report", str(trader_report)]

            if args.allow_shorts:
                chef_cmd += ["--allow-shorts"]
            if args.execute:
                chef_cmd += ["--execute"]
            if args.allow_live:
                chef_cmd += ["--allow-live"]

            print("[Chef] running…")
            _run(chef_cmd, verbose=args.verbose)
            chef_report = _latest_txt_file(chef_dir, "Report Grok Chef")

            chef_text = _ensure_non_empty_file(chef_report, "Report Grok Chef").read_text(
                encoding="utf-8"
            )
            plan_obj = _extract_first_object_with_keys(
                chef_text, {"approved", "orders", "summary"}
            )

            approved = plan_obj.get("approved") if plan_obj else None
            summary = plan_obj.get("summary") if plan_obj else None
            orders = plan_obj.get("orders") if plan_obj else None

            order_lines: list[str] = []
            if isinstance(orders, list):
                for order in orders[:5]:
                    if not isinstance(order, dict):
                        continue
                    sym = order.get("symbol")
                    side = order.get("side")
                    qty = order.get("qty")
                    otype = order.get("order_type")
                    lp = order.get("limit_price")
                    if isinstance(sym, str) and isinstance(side, str):
                        if otype == "limit" and lp is not None:
                            order_lines.append(f"- {sym} {side} qty={qty} limit={lp}")
                        else:
                            order_lines.append(f"- {sym} {side} qty={qty} {otype}")

            execution_results = None
            for value in _extract_json_values(chef_text):
                if (
                    isinstance(value, list)
                    and value
                    and all(isinstance(x, dict) for x in value)
                ):
                    if any("id" in x or "status" in x for x in value):
                        execution_results = value
            exec_lines: list[str] = []
            if isinstance(execution_results, list):
                for item in execution_results[:8]:
                    sym = item.get("symbol")
                    oid = item.get("id")
                    status = item.get("status")
                    side = item.get("side")
                    qty = item.get("qty")
                    if sym and oid:
                        exec_lines.append(f"- {sym} {side} qty={qty} -> {status} ({oid})")

            chef_label = "done"
            print(
                f"[Chef] {chef_label} -> {chef_report}"
                + (f" | approved={approved}" if isinstance(approved, bool) else "")
                + (f" | execute={bool(args.execute)}" if args.execute else "")
                + (
                    f" | {_ellipsize(summary, 160)}"
                    if isinstance(summary, str) and summary.strip()
                    else ""
                )
            )
            if order_lines:
                print("Planned orders:")
                print("\n".join(order_lines))
            if exec_lines:
                print("Submitted orders:")
                print("\n".join(exec_lines))
        else:
            print("[Chef] skipped")

        portfolio, portfolio_err = _alpaca_portfolio_summary()
        if portfolio:
            paper = portfolio.get("paper")
            cash = portfolio.get("cash")
            equity = portfolio.get("equity")
            buying_power = portfolio.get("buying_power")
            positions = portfolio.get("positions") or []
            print(
                f"\nPortfolio (alpaca): paper={paper} cash={cash} equity={equity} buying_power={buying_power} positions={len(positions)}"
            )
            if positions:
                shown: list[str] = []
                for pos in positions[:8]:
                    sym = pos.get("symbol")
                    qty = pos.get("qty")
                    if sym:
                        shown.append(f"{sym}:{qty}")
                if shown:
                    print("Positions:", ", ".join(shown))
        else:
            print(f"\nPortfolio (alpaca): (non disponible: {portfolio_err})")

        print("\n=== Outputs ===")
        print(f"- Research report: {research_report}")
        print(f"- Trader: {args.trader_json if args.trader_json else trader_report}")
        print(f"- Grok Chef: {chef_report if chef_report else '(skipped)'}")
    except Exception as exc:
        if args.verbose:
            raise
        print(f"\nWorkflow FAILED: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
