#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScrapNews - Récupère les news de plusieurs sources et génère un résumé avec Grok
"""

import os
import sys
import requests
import feedparser
from datetime import datetime, timezone
from newspaper import Article
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user
import json
import time

# Importer les modules séparés
from yfinance_tools import get_current_price, get_price_history
from stock_analyzer import StockAnalyzer

# Forcer l'encodage UTF-8 sur Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Charger les variables d'environnement
load_dotenv()

class NewsScraper:
    def __init__(self):
        self.xai_api_key = os.getenv('XAI_API_KEY')
        if not self.xai_api_key:
            raise ValueError("XAI_API_KEY non trouvé dans le fichier .env")
        
        self.client = Client(api_key=self.xai_api_key)
        self.stock_analyzer = StockAnalyzer()
        
        # Sources de news (RSS feeds) spécialisées trading/finance
        self.news_sources = [
            {
                'name': 'Bloomberg Markets',
                'url': 'https://feeds.bloomberg.com/markets/news.rss',
                'language': 'en'
            },
            {
                'name': 'Reuters Business',
                'url': 'https://www.reuters.com/rssFeed/businessNews',
                'language': 'en'
            },
            {
                'name': 'Yahoo Finance',
                'url': 'https://finance.yahoo.com/news/rssindex',
                'language': 'en'
            },
            {
                'name': 'MarketWatch',
                'url': 'https://www.marketwatch.com/rss/topstories',
                'language': 'en'
            },
            {
                'name': 'Investing.com',
                'url': 'https://www.investing.com/rss/news.rss',
                'language': 'en'
            },
            {
                'name': 'Les Echos',
                'url': 'https://www.lesechos.fr/rss/rss_actualites.xml',
                'language': 'fr'
            },
            {
                'name': 'La Tribune Finances',
                'url': 'https://www.latribune.fr/rss/actualites/economie.xml',
                'language': 'fr'
            }
        ]
    
    def fetch_rss_feed(self, source):
        """Récupère les articles d'un flux RSS"""
        try:
            print(f"Récupération des articles de {source['name']}...")
            feed = feedparser.parse(source['url'])
            articles = []
            
            for entry in feed.entries[:5]:  # Limiter à 5 articles par source
                article = {
                    'title': entry.title,
                    'summary': entry.get('summary', ''),
                    'link': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'source': source['name'],
                    'language': source['language']
                }
                articles.append(article)
            
            return articles
        except Exception as e:
            print(f"Erreur lors de la récupération de {source['name']}: {e}")
            return []
    
    def get_full_article_content(self, article_url):
        """Récupère le contenu complet d'un article"""
        try:
            article = Article(article_url)
            article.download()
            article.parse()
            return article.text
        except Exception as e:
            print(f"Erreur lors de la récupération du contenu de l'article: {e}")
            return ""
    
    def collect_all_news(self):
        """Récupère les news de toutes les sources"""
        all_articles = []
        
        for source in self.news_sources:
            articles = self.fetch_rss_feed(source)
            all_articles.extend(articles)
            time.sleep(1)  # Pause pour éviter de surcharger les serveurs
        
        return all_articles
    
    def summarize_with_grok(self, articles):
        """Génère un résumé des articles avec Grok"""
        if not articles:
            return "Aucun article à résumer."
        
        # Préparer le texte pour Grok
        news_text = "ACTUALITÉS TRADING & FINANCE RÉCENTES:\n\n"
        
        for i, article in enumerate(articles[:10], 1):  # Limiter à 10 articles pour le résumé
            news_text += f"{i}. {article['title']}\n"
            news_text += f"   Source: {article['source']}\n"
            news_text += f"   Résumé: {article['summary'][:200]}...\n"
            news_text += f"   Date: {article['published']}\n\n"
        
        prompt = f"""
En tant qu'analyste financier et expert en trading, veuillez créer un résumé complet des actualités financières et économiques récentes.

Voici les articles à analyser:

{news_text}

Générez un résumé structuré qui inclut:
1. Les mouvements majeurs des marchés (actions, indices, devises, matières premières)
2. Les nouvelles économiques importantes (inflation, taux d'intérêt, PIB, emploi)
3. Les actualités entreprises et sectorielles pertinentes pour les traders
4. Les indicateurs techniques et analyses de marché mentionnés
5. Les opportunités et risques identifiés pour les traders

Le résumé doit être en français, orienté trading, concis mais informatif, et organisé de manière logique pour les traders et investisseurs.
"""
        
        try:
            print("Génération du résumé avec Grok...")
            chat = self.client.chat.create(model="grok-4-1-fast")
            chat.append(user("Vous êtes un analyste financier et expert en trading qui fournit des résumés clairs et pertinents des actualités financières. " + prompt))
            
            response = chat.sample()
            return response.content
        except Exception as e:
            print(f"Erreur lors de la génération du résumé: {e}")
            return f"Erreur lors de la génération du résumé: {e}"
    
    def save_summary(self, summary, articles, stock_analysis_result=None):
        """Sauvegarde le résumé et les articles dans des fichiers"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        # Créer le dossier resume s'il n'existe pas
        resume_dir = "resume"
        os.makedirs(resume_dir, exist_ok=True)
        
        # Sauvegarder le résumé dans le dossier resume
        summary_filename = os.path.join(resume_dir, f"trading_news_summary_{timestamp}.md")
        with open(summary_filename, 'w', encoding='utf-8') as f:
            f.write(f"# Résumé des Actualités Trading & Finance\n\n")
            f.write(f"Généré le: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
            
            # Ajouter l'analyse des stocks si disponible
            if stock_analysis_result and stock_analysis_result.get('summary'):
                f.write("## 📊 Analyse des Symboles Mentionnés\n\n")
                f.write(stock_analysis_result['summary'])
                f.write("\n\n")
            
            f.write("## 📈 Résumé des Actualités\n\n")
            f.write(summary)
        
        # Sauvegarder les articles bruts dans le dossier resume
        articles_data = {
            'articles': articles,
            'stock_analysis': stock_analysis_result or {},
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'sources_count': len(self.news_sources),
            'articles_count': len(articles)
        }
        
        articles_filename = os.path.join(resume_dir, f"raw_trading_articles_{timestamp}.json")
        with open(articles_filename, 'w', encoding='utf-8') as f:
            json.dump(articles_data, f, ensure_ascii=False, indent=2)
        
        print(f"\nRésumé sauvegardé dans: {summary_filename}")
        print(f"Articles bruts sauvegardés dans: {articles_filename}")
        
        return summary_filename, articles_filename
    
    def run(self):
        """Fonction principale du scraper"""
        print("Demarrage de ScrapNews - Recuperation des actualites trading & finance...")
        
        # Récupérer les articles
        articles = self.collect_all_news()
        print(f"\n{len(articles)} articles recuperes de {len(self.news_sources)} sources financieres")
        
        if not articles:
            print("Aucun article recuperé. Arrêt du programme.")
            return
        
        # Afficher les titres récupérés
        print("\nArticles trading recuperes:")
        for i, article in enumerate(articles[:10], 1):
            print(f"{i}. {article['title']} ({article['source']})")
        
        # Analyser les symboles mentionnés avec StockAnalyzer
        stock_analysis_result = self.stock_analyzer.analyze_articles(articles)
        stock_analysis = stock_analysis_result['analysis']
        
        # Générer le résumé
        print("\nGeneration du resume trading avec Grok...")
        summary = self.summarize_with_grok(articles)
        
        # Sauvegarder les résultats
        print("\nSauvegarde des resultats dans le dossier resume...")
        summary_file, articles_file = self.save_summary(summary, articles, stock_analysis_result)
        
        print(f"\nScrapNews Trading termine avec succes!")
        print(f"Resume trading: {summary_file}")
        print(f"Articles bruts: {articles_file}")
        
        # Afficher un aperçu du résumé
        print("\nApercu du resume trading:")
        print("=" * 50)
        print(summary[:500] + "..." if len(summary) > 500 else summary)

if __name__ == "__main__":
    try:
        scraper = NewsScraper()
        scraper.run()
    except Exception as e:
        print(f"Erreur: {e}")
        print("Veuillez vérifier que votre clé API XAI est correctement configurée dans le fichier .env")
