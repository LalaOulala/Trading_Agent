#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test YFinance - Test simple pour récupérer le prix actuel de AAPL
"""

import sys
import os
import pandas as pd
from datetime import datetime, timezone

# Forcer l'encodage UTF-8 sur Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from yfinance_tools import get_current_price, get_price_history, get_detailed_info, get_market_status

def save_price_history(symbol, history, folder="price_history"):
    """Sauvegarde l'historique des prix dans un fichier CSV"""
    try:
        # Créer le dossier s'il n'existe pas
        os.makedirs(folder, exist_ok=True)
        
        # Nom de fichier avec timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(folder, f"{symbol}_history_{timestamp}.csv")
        
        # Sauvegarder en CSV
        history.to_csv(filename, index=True)
        print(f"   Historique sauvegardé dans: {filename}")
        
        return filename
        
    except Exception as e:
        print(f"   Erreur sauvegarde historique: {e}")
        return None

def test_aapl_price():
    """Test simple pour récupérer le prix de AAPL"""
    symbol = "AAPL"
    
    print(f"=== Test YFinance - {symbol} ===\n")
    
    # Test 1: Prix actuel
    print("1. Prix actuel:")
    price = get_current_price(symbol)
    if price:
        print(f"   OK {symbol}: ${price:.2f}")
    else:
        print(f"   Erreur récupération prix {symbol}")
    
    # Test 2: Historique récent
    print(f"\n2. Historique 5 jours:")
    history = get_price_history(symbol, "5d")
    if history is not None and not history.empty:
        print(f"   OK Historique disponible: {len(history)} jours")
        print("   Prix récents:")
        for i, (date, row) in enumerate(history.tail(3).iterrows()):
            print(f"     {date.strftime('%Y-%m-%d')}: ${row['Close']:.2f}")
        
        # Sauvegarder l'historique
        saved_file = save_price_history(symbol, history)
        
    else:
        print(f"   Erreur historique {symbol}")
    
    # Test 3: Infos détaillées
    print(f"\n3. Infos entreprise:")
    info = get_detailed_info(symbol)
    if info:
        print(f"   OK Entreprise: {info.get('company_name', 'N/A')}")
        print(f"   Secteur: {info.get('sector', 'N/A')}")
        if info.get('market_cap'):
            print(f"   Market Cap: ${info.get('market_cap', 0):,}")
        else:
            print(f"   Market Cap: N/A")
        print(f"   P/E Ratio: {info.get('pe_ratio', 'N/A')}")
        if info.get('volume'):
            print(f"   Volume: {info.get('volume', 0):,}")
        else:
            print(f"   Volume: N/A")
    else:
        print(f"   Erreur infos détaillées {symbol}")
    
    # Test 4: Statut marché
    print(f"\n4. Statut marché:")
    is_open, status = get_market_status()
    if is_open is not None:
        print(f"   OK Marché: {status}")
    else:
        print(f"   Erreur statut marché")
    
    print(f"\n=== Test terminé pour {symbol} ===")

if __name__ == "__main__":
    test_aapl_price()
