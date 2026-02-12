#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YFinance Tools - Fonctions pour récupérer les prix et historiques via Yahoo Finance
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def get_current_price_yfinance(symbol):
    """Récupère le prix actuel d'un symbole via Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Essayer différentes méthodes pour obtenir le prix
        try:
            info = ticker.info
            
            if 'currentPrice' in info and info['currentPrice']:
                price = float(info['currentPrice'])
                if price > 0:
                    return price
            
            if 'regularMarketPrice' in info and info['regularMarketPrice']:
                price = float(info['regularMarketPrice'])
                if price > 0:
                    return price
        except:
            pass
        
        # Fallback via l'historique du jour
        try:
            history = ticker.history(period="1d")
            if not history.empty:
                price = float(history['Close'].iloc[-1])
                if price > 0:
                    return price
        except:
            pass
        
        return None
        
    except Exception as e:
        print(f"Erreur récupération prix {symbol}: {e}")
        return None


def get_current_price(symbol):
    """Prix actuel avec fallbacks"""
    try:
        price = get_current_price_yfinance(symbol)
        if price and price > 0:
            return price
    except:
        pass
    
    return None


def get_price_history(symbol, period="5d"):
    """Récupère l'historique des prix via Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period)
        
        if not history.empty:
            return history
        else:
            return None
            
    except Exception as e:
        print(f"Erreur historique prix {symbol}: {e}")
        return None


def get_detailed_info(symbol):
    """Récupère des informations détaillées sur une action"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Filtrer les informations les plus pertinentes
        relevant_info = {
            'symbol': symbol,
            'company_name': info.get('longName', ''),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'market_cap': info.get('marketCap', None),
            'current_price': info.get('currentPrice', None),
            'previous_close': info.get('previousClose', None),
            'open': info.get('open', None),
            'day_high': info.get('dayHigh', None),
            'day_low': info.get('dayLow', None),
            'volume': info.get('volume', None),
            'avg_volume': info.get('averageVolume', None),
            'pe_ratio': info.get('trailingPE', None),
            'eps': info.get('trailingEps', None),
            'beta': info.get('beta', None),
            'dividend_yield': info.get('dividendYield', None),
            '52_week_high': info.get('fiftyTwoWeekHigh', None),
            '52_week_low': info.get('fiftyTwoWeekLow', None),
        }
        
        return relevant_info
        
    except Exception as e:
        print(f"Erreur infos détaillées {symbol}: {e}")
        return None


def calculate_technical_indicators(history):
    """Calcule des indicateurs techniques basiques"""
    try:
        if history is None or history.empty:
            return None
        
        df = history.copy()
        
        # Moyennes mobiles
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        
        # RSI (Relative Strength Index)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Variation sur différentes périodes
        df['Change_1d'] = df['Close'].pct_change(1) * 100
        df['Change_5d'] = df['Close'].pct_change(5) * 100
        df['Change_20d'] = df['Close'].pct_change(20) * 100
        
        # Volatilité (écart-type sur 20 jours)
        df['Volatility'] = df['Close'].rolling(window=20).std()
        
        return df
        
    except Exception as e:
        print(f"Erreur indicateurs techniques: {e}")
        return None


def get_market_status():
    """Vérifie si les marchés sont ouverts"""
    try:
        from datetime import datetime
        import pytz
        
        # Heures de marché US (EST/EDT)
        eastern = pytz.timezone('US/Eastern')
        now_eastern = datetime.now(eastern)
        
        # Jours de semaine (lundi-vendredi)
        if now_eastern.weekday() >= 5:  # 5 = samedi, 6 = dimanche
            return False, "Weekend"
        
        # Heures de trading (9:30 AM - 4:00 PM ET)
        market_open = now_eastern.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_eastern.replace(hour=16, minute=0, second=0, microsecond=0)
        
        if market_open <= now_eastern <= market_close:
            return True, "Market Open"
        else:
            return False, "Market Closed"
            
    except Exception as e:
        print(f"Erreur statut marché: {e}")
        return None, "Unknown"


if __name__ == "__main__":
    # Test des fonctions
    symbol = "AAPL"
    
    print(f"=== Test YFinance Tools - {symbol} ===\n")
    
    # Prix actuel
    price = get_current_price(symbol)
    print(f"Prix actuel: ${price}")
    
    # Historique
    history = get_price_history(symbol, "10d")
    if history is not None:
        print(f"\nHistorique disponible: {len(history)} jours")
        print(f"Prix récents: {history['Close'].tail(3).tolist()}")
    
    # Infos détaillées
    info = get_detailed_info(symbol)
    if info:
        print(f"\nEntreprise: {info['company_name']}")
        print(f"Secteur: {info['sector']}")
        print(f"Market Cap: ${info['market_cap']:,}" if info['market_cap'] else "")
    
    # Indicateurs techniques
    tech_data = calculate_technical_indicators(history)
    if tech_data is not None:
        latest = tech_data.iloc[-1]
        print(f"\nRSI: {latest['RSI']:.1f}" if pd.notna(latest['RSI']) else "")
        print(f"Variation 5j: {latest['Change_5d']:+.2f}%" if pd.notna(latest['Change_5d']) else "")
    
    # Statut marché
    is_open, status = get_market_status()
    print(f"\nStatut marché: {status}")
