"""
Funções utilitárias para o Multi-Language Books
"""
import re
from typing import List, Tuple


def clean_text(text: str) -> str:
    """
    Limpa texto removendo espaços extras e caracteres especiais.
    
    Args:
        text: Texto a ser limpo
        
    Returns:
        Texto limpo
    """
    # Remover espaços múltiplos
    text = re.sub(r'\s+', ' ', text)
    # Remover espaços antes de pontuação
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)
    return text.strip()


def estimate_reading_time(word_count: int, wpm: int = 200) -> Tuple[int, int]:
    """
    Estima tempo de leitura.
    
    Args:
        word_count: Número de palavras
        wpm: Palavras por minuto (padrão: 200)
        
    Returns:
        Tupla (horas, minutos)
    """
    total_minutes = word_count / wpm
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)
    return hours, minutes


def format_file_size(size_bytes: int) -> str:
    """
    Formata tamanho de arquivo para exibição.
    
    Args:
        size_bytes: Tamanho em bytes
        
    Returns:
        String formatada (ex: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Trunca texto em um comprimento máximo.
    
    Args:
        text: Texto a truncar
        max_length: Comprimento máximo
        suffix: Sufixo para indicar truncamento
        
    Returns:
        Texto truncado
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_language_name(code: str) -> str:
    """
    Retorna o nome do idioma a partir do código ISO.
    
    Args:
        code: Código ISO do idioma (ex: "en", "pt")
        
    Returns:
        Nome do idioma
    """
    from config.settings import SUPPORTED_LANGUAGES
    return SUPPORTED_LANGUAGES.get(code, code)


def is_sentence_boundary(char: str) -> bool:
    """
    Verifica se um caractere é um delimitador de sentença.
    
    Args:
        char: Caractere a verificar
        
    Returns:
        True se for delimitador
    """
    return char in '.!?'


def count_words(text: str) -> int:
    """
    Conta palavras em um texto.
    
    Args:
        text: Texto para contar palavras
        
    Returns:
        Número de palavras
    """
    return len(text.split())


def normalize_language_code(code: str) -> str:
    """
    Normaliza código de idioma para formato ISO 639-1.
    
    Args:
        code: Código de idioma (pode ser longo, ex: "pt-BR")
        
    Returns:
        Código normalizado (ex: "pt")
    """
    if not code:
        return "en"
    
    # Pegar apenas os primeiros 2 caracteres
    code = code.lower()[:2]
    
    # Mapeamentos especiais
    mappings = {
        'pt': 'pt',
        'en': 'en',
        'es': 'es',
        'fr': 'fr',
        'de': 'de',
        'it': 'it',
        'nl': 'nl',
        'ru': 'ru',
        'zh': 'zh',
        'ja': 'ja',
        'ko': 'ko',
    }
    
    return mappings.get(code, 'en')
