#!/usr/bin/env python3
"""
Tests para TweetProcessor
"""
import pytest
from pathlib import Path
from tweet_processor import TweetProcessor


def test_tweet_processor_with_replacement(tmp_path):
    """Test para verificar que el procesador de tweets reemplaza archivos existentes."""
    
    # Preparar directorios
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Tweets" / "Tweets 2025"
    destination.mkdir(parents=True)
    
    # Crear un archivo de tweets existente en el destino
    existing_md = destination / "Tweets Test.md"
    existing_md.write_text("# Tweets existentes\n\nContenido viejo")
    
    existing_html = destination / "Tweets Test.html"
    existing_html.write_text("<html><body>HTML viejo</body></html>")
    
    # Crear un nuevo archivo de tweets en Incoming
    new_md = incoming / "Tweets Test.md"
    new_md.write_text("# Tweets nuevos\n\nContenido nuevo")
    
    # Procesar tweets
    processor = TweetProcessor(incoming, destination)
    moved_files = processor.process_tweets()
    
    # Verificar que se procesaron archivos
    assert len(moved_files) == 2  # MD y HTML
    
    # Verificar que el contenido fue reemplazado
    final_md = destination / "Tweets Test.md"
    final_html = destination / "Tweets Test.html"
    
    assert final_md.exists()
    assert final_html.exists()
    
    # Verificar que el contenido es el nuevo
    md_content = final_md.read_text()
    html_content = final_html.read_text()
    
    assert "Contenido nuevo" in md_content
    assert "Contenido viejo" not in md_content
    assert "<html>" in html_content  # Verificar que es un archivo HTML válido


def test_tweet_processor_no_tweets(tmp_path):
    """Test para verificar comportamiento cuando no hay archivos de tweets."""
    
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Tweets" / "Tweets 2025"
    destination.mkdir(parents=True)
    
    processor = TweetProcessor(incoming, destination)
    moved_files = processor.process_tweets()
    
    assert len(moved_files) == 0


def test_tweet_processor_with_tweets(tmp_path):
    """Test para verificar procesamiento normal de tweets."""
    
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Tweets" / "Tweets 2025"
    destination.mkdir(parents=True)
    
    # Crear archivo de tweets
    tweet_md = incoming / "Tweets Test.md"
    tweet_md.write_text("# Tweets de prueba\n\nEste es un tweet de prueba.")
    
    processor = TweetProcessor(incoming, destination)
    moved_files = processor.process_tweets()
    
    # Verificar que se procesaron archivos
    assert len(moved_files) == 2  # MD y HTML
    
    # Verificar que los archivos existen en el destino
    final_md = destination / "Tweets Test.md"
    final_html = destination / "Tweets Test.html"
    
    assert final_md.exists()
    assert final_html.exists()
    
    # Verificar contenido
    md_content = final_md.read_text()
    html_content = final_html.read_text()
    
    assert "Tweets de prueba" in md_content
    assert "tweet de prueba" in md_content
    assert "<html>" in html_content  # Verificar que es un archivo HTML válido 