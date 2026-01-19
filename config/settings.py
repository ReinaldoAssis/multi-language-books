"""
Configurações do Multi-Language Books
"""
import os

# =============================================================================
# API Configuration
# =============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCTookAmLDNLljmmpLmym4M_wnRDIQLHI0")
GEMINI_MODEL = "gemini-3-flash-preview"

# =============================================================================
# CEFR Thresholds (baseado em Zipf Frequency)
# =============================================================================
# Zipf frequency: log10 de ocorrências por bilhão de palavras
# Valor 6 = 1 ocorrência por mil palavras (muito comum)
# Valor 3 = 1 ocorrência por milhão de palavras (raro)

CEFR_THRESHOLDS = {
    "A1": 6.0,   # Palavras muito comuns (top ~1000)
    "A2": 5.5,   # Palavras comuns (top ~3000)
    "B1": 5.0,   # Palavras frequentes (top ~10000)
    "B2": 4.5,   # Vocabulário intermediário
    "C1": 4.0,   # Vocabulário avançado
    "C2+": 0.0,  # Qualquer valor abaixo de C1 (vocabulário raro)
}

# Mapeamento de nível para valor numérico (para comparações)
CEFR_LEVEL_ORDER = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2+": 6,
}

# =============================================================================
# Idiomas Suportados
# =============================================================================
# Códigos ISO 639-1 para wordfreq e tradução

SUPPORTED_LANGUAGES = {
    "en": "English",
    "pt": "Português",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "nl": "Nederlands",
    "ru": "Русский",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
}

# Idiomas com suporte completo no wordfreq (lista 'large')
WORDFREQ_FULL_SUPPORT = ["en", "es", "fr", "de", "it", "pt", "nl", "ru", "zh", "ja", "ko"]

# =============================================================================
# Configurações de Processamento
# =============================================================================

# Número máximo de caracteres por request ao Gemini
# (O context window é grande, mas limitamos para segurança)
MAX_CHARS_PER_REQUEST = 100000

# Número de sentenças de contexto antes/depois da sentença a traduzir
CONTEXT_SENTENCES = 2

# Timeout para requests ao Gemini (segundos)
GEMINI_TIMEOUT = 120

# =============================================================================
# Estilização de Saída
# =============================================================================

# CSS para destacar texto traduzido no EPUB
TRANSLATED_TEXT_STYLE = "color: #1a5276; font-style: italic;"
ORIGINAL_TEXT_STYLE = ""  # Sem estilização adicional
