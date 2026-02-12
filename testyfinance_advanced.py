#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test YFinance Complet - Test complet des fonctionnalités YFinance
"""

import sys
import os
import pandas as pd
from datetime import datetime, timezone, timedelta

# Forcer l'encodage UTF-8 sur Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from yfinance_tools import (
    get_current_price, 
    get_price_history, 
    get_price_history_advanced,
    get_detailed_info, 
    get_market_status
)

def save_price_history(symbol, history, folder="price_history", suffix=""):
    """Sauvegarde l'historique des prix dans un fichier CSV"""
    try:
        # Créer le dossier s'il n'existe pas
        os.makedirs(folder, exist_ok=True)
        
        # Nom de fichier avec timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(folder, f"{symbol}_history_{timestamp}{suffix}.csv")
        
        # Sauvegarder en CSV
        history.to_csv(filename, index=True)
        print(f"   Historique sauvegardé dans: {filename}")
        
        return filename
        
    except Exception as e:
        print(f"   Erreur sauvegarde historique: {e}")
        return None

def test_basic_functions():
    """Test des fonctions de base"""
    symbol = "AAPL"
    
    print(f"=== Test YFinance Basique - {symbol} ===\n")
    
    # Test 1: Prix actuel
    print("1. Prix actuel:")
    price = get_current_price(symbol)
    if price:
        print(f"   OK {symbol}: ${price:.2f}")
    else:
        print(f"   Erreur récupération prix {symbol}")
    
    # Test 2: Historique simple
    print(f"\n2. Historique 5 jours (quotidien):")
    history = get_price_history(symbol, "5d")
    if history is not None and not history.empty:
        print(f"   OK Historique disponible: {len(history)} jours")
        print("   Prix récents:")
        for i, (date, row) in enumerate(history.tail(3).iterrows()):
            print(f"     {date.strftime('%Y-%m-%d')}: ${row['Close']:.2f}")
        
        # Sauvegarder l'historique
        save_price_history(symbol, history)
        
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
    
    print(f"\n=== Test basique terminé pour {symbol} ===")

def test_advanced_intervals():
    """Test des différents intervalles et périodes"""
    symbol = "AAPL"
    
    print(f"\n=== Test Intervalles Avancés - {symbol} ===\n")
    
    # Test 1: Différents intervalles sur 1 jour
    print("1. Test intervalles sur 1 jour:")
    
    intervals = ["1h", "30m", "15m", "5m"]
    for interval in intervals:
        print(f"   a) 1 jour avec intervalle {interval}:")
        history = get_price_history(symbol, period="1d", interval=interval)
        if history is not None:
            print(f"      {len(history)} points de données")
            save_price_history(symbol, history, suffix=f"_1d_{interval}")
        else:
            print(f"      Erreur intervalle {interval}")
    
    # Test 2: Différentes périodes avec intervalle quotidien
    print(f"\n2. Test périodes avec intervalle 1d:")
    
    periods = ["1mo", "3mo", "6mo", "1y"]
    for period in periods:
        print(f"   a) {period} avec intervalle 1d:")
        history = get_price_history(symbol, period=period, interval="1d")
        if history is not None:
            print(f"      {len(history)} points de données")
            save_price_history(symbol, history, suffix=f"_{period}_1d")
        else:
            print(f"      Erreur période {period}")
    
    # Test 3: Données intraday haute résolution
    print(f"\n3. Test données intraday haute résolution:")
    
    print("   a) 5 jours avec intervalle 5m:")
    history_5d_5m = get_price_history(symbol, period="5d", interval="5m")
    if history_5d_5m is not None:
        print(f"      {len(history_5d_5m)} points de données")
        save_price_history(symbol, history_5d_5m, suffix="_5d_5m")
        
        # Statistiques détaillées
        first_price = history_5d_5m['Close'].iloc[0]
        last_price = history_5d_5m['Close'].iloc[-1]
        change_pct = ((last_price - first_price) / first_price) * 100
        avg_volume = history_5d_5m['Volume'].mean() if 'Volume' in history_5d_5m.columns else 0
        max_price = history_5d_5m['High'].max()
        min_price = history_5d_5m['Low'].min()
        
        print(f"      Performance: {first_price:.2f}→{last_price:.2f} ({change_pct:+.1f}%)")
        print(f"      Fourchette: ${min_price:.2f} - ${max_price:.2f}")
        print(f"      Volume moyen: {avg_volume:,.0f}")
    else:
        print("      Erreur données 5m")
    
    print("   b) 1 semaine avec intervalle 1m:")
    history_1w_1m = get_price_history(symbol, period="5d", interval="1m")
    if history_1w_1m is not None:
        print(f"      {len(history_1w_1m)} points de données")
        save_price_history(symbol, history_1w_1m, suffix="_5d_1m")
    else:
        print("      Erreur données 1m (peut être limité)")
    
    print(f"\n=== Test intervalles terminé pour {symbol} ===")

def test_custom_dates():
    """Test avec dates personnalisées"""
    symbol = "AAPL"
    
    print(f"\n=== Test Dates Personnalisées - {symbol} ===\n")
    
    # Test 1: Derniers 30 jours
    print("1. Derniers 30 jours:")
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print(f"   Du {start_date} au {end_date}:")
    history_30d = get_price_history_advanced(symbol, start_date=start_date, end_date=end_date, interval="1d")
    if history_30d is not None:
        print(f"   {len(history_30d)} points de données")
        save_price_history(symbol, history_30d, suffix="_30days_custom")
    else:
        print("   Erreur 30 jours personnalisés")
    
    # Test 2: Année en cours (YTD)
    print(f"\n2. Année en cours (YTD):")
    current_year = datetime.now().year
    start_date_ytd = f"{current_year}-01-01"
    end_date_ytd = datetime.now().strftime('%Y-%m-%d')
    
    print(f"   Du {start_date_ytd} au {end_date_ytd}:")
    history_ytd = get_price_history_advanced(symbol, start_date=start_date_ytd, end_date=end_date_ytd, interval="1d")
    if history_ytd is not None:
        print(f"   {len(history_ytd)} points de données")
        save_price_history(symbol, history_ytd, suffix="_ytd_custom")
    else:
        print("   Erreur YTD personnalisé")
    
    # Test 3: Période spécifique avec intervalle horaire
    print(f"\n3. Période spécifique avec intervalle horaire:")
    start_date_hour = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date_hour = datetime.now().strftime('%Y-%m-%d')
    
    print(f"   Du {start_date_hour} au {end_date_hour} (intervalle 1h):")
    history_hour = get_price_history_advanced(symbol, start_date=start_date_hour, end_date=end_date_hour, interval="1h")
    if history_hour is not None:
        print(f"   {len(history_hour)} points de données")
        save_price_history(symbol, history_hour, suffix="_7days_1h")
    else:
        print("   Erreur période horaire")
    
    print(f"\n=== Test dates personnalisées terminé pour {symbol} ===")

if __name__ == "__main__":
    print("🚀 Démarrage du test complet YFinance...\n")
    
    # Lancer les tests
    test_basic_functions()
    test_advanced_intervals()
    test_custom_dates()
    
    print(f"\n✅ Tests YFinance terminés avec succès !")
    print(f"📁 Fichiers sauvegardés dans le dossier 'price_history/'")
