# Multi-Language Books - Plano de Desenvolvimento

## 📖 Visão Geral

Aplicativo Streamlit que transforma livros EPUB em versões multi-idiomas para estudo de línguas estrangeiras. Utiliza IA (Gemini) para tradução inteligente baseada no nível de proficiência do usuário (CEFR: A1-C2+).

## 🎯 Objetivo Principal

Criar uma ferramenta que:
1. Mantém partes do texto no idioma original (mais difíceis para o nível do usuário)
2. Traduz partes do texto para o idioma nativo (mais fáceis no idioma original)
3. Força o usuário a ler no idioma que está estudando, com suporte contextual

---

## 🏗️ Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Upload EPUB │  │ Configurações│  │ Download EPUB Resultado│  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Processing                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ EPUB Parser │──│ Difficulty   │──│ Translation Engine     │  │
│  │ (ebooklib)  │  │ Analyzer     │  │ (Gemini API)           │  │
│  └─────────────┘  │ (wordfreq)   │  └────────────────────────┘  │
│                   └──────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EPUB Generator                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Reconstrução do EPUB com texto multi-idioma                 ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Módulos e Componentes

### 1. `epub_parser.py` - Parser de EPUB
```python
# Responsabilidades:
# - Ler arquivo EPUB usando ebooklib
# - Extrair capítulos e estrutura
# - Separar texto de corpo (excluindo metadados, TOC, etc.)
# - Preservar formatação HTML/CSS original
# - Retornar estrutura parseada mantendo referências para reconstrução
```

**Funções principais:**
- `parse_epub(file_path) -> EpubStructure`
- `extract_body_text(chapter) -> List[Paragraph]`
- `split_into_sentences(text) -> List[Sentence]`

### 2. `difficulty_analyzer.py` - Analisador de Dificuldade
```python
# Responsabilidades:
# - Analisar dificuldade de cada sentença usando wordfreq
# - Classificar sentenças por nível CEFR (A1-C2+)
# - Considerar múltiplos fatores: frequência das palavras, comprimento, estrutura
```

**Lógica de Classificação CEFR baseada em Zipf Frequency:**

| Nível | Zipf Médio Mínimo | Descrição |
|-------|-------------------|-----------|
| A1    | >= 6.0            | Palavras muito comuns (top 1000) |
| A2    | >= 5.5            | Palavras comuns (top 3000) |
| B1    | >= 5.0            | Palavras frequentes (top 10000) |
| B2    | >= 4.5            | Vocabulário intermediário |
| C1    | >= 4.0            | Vocabulário avançado |
| C2+   | < 4.0             | Vocabulário raro/especializado |

**Funções principais:**
- `analyze_sentence(sentence, lang) -> DifficultyScore`
- `classify_cefr_level(score) -> CEFRLevel`
- `should_translate(sentence, user_level, lang) -> bool`

### 3. `translation_engine.py` - Motor de Tradução
```python
# Responsabilidades:
# - Preparar batches de sentenças para tradução
# - Manter contexto ao redor das sentenças a traduzir
# - Comunicar com Gemini API
# - Processar respostas e mapear traduções
```

**Estratégia de Batching:**
```
Contexto: [Sentença anterior não traduzida]
Traduzir: [Sentença marcada para tradução]
Contexto: [Sentença posterior não traduzida]
```

**Funções principais:**
- `prepare_translation_batch(sentences, indices_to_translate) -> TranslationRequest`
- `translate_batch(batch, source_lang, target_lang) -> List[Translation]`
- `build_gemini_prompt(batch) -> str`

### 4. `epub_generator.py` - Gerador de EPUB
```python
# Responsabilidades:
# - Reconstruir EPUB com texto modificado
# - Manter estrutura original (capítulos, formatação, imagens)
# - Aplicar estilização opcional para diferenciar idiomas
```

**Funções principais:**
- `generate_epub(original_structure, translated_content) -> bytes`
- `apply_language_styling(html, translations) -> str`

### 5. `streamlit_app.py` - Interface do Usuário
```python
# Responsabilidades:
# - Upload de arquivo EPUB
# - Seleção de idiomas (origem e destino)
# - Seleção de nível CEFR
# - Barra de progresso durante processamento
# - Download do resultado
```

---

## 🔄 Fluxo de Processamento

### Etapa 1: Upload e Parsing
```
1. Usuário faz upload do EPUB
2. Sistema extrai estrutura do livro
3. Sistema separa texto de corpo de cada capítulo
4. Sistema divide texto em sentenças preservando parágrafos
```

### Etapa 2: Análise de Dificuldade
```
1. Para cada sentença:
   a. Tokenizar palavras
   b. Calcular Zipf frequency média
   c. Considerar palavras desconhecidas (freq = 0)
   d. Classificar nível CEFR da sentença
2. Marcar sentenças que devem ser traduzidas:
   - Se nível_sentença <= nível_usuário → TRADUZIR (é fácil demais no original)
   - Se nível_sentença > nível_usuário → MANTER ORIGINAL (é o desafio)
```

### Etapa 3: Preparação para Tradução
```
1. Agrupar sentenças marcadas para tradução
2. Para cada sentença a traduzir, incluir contexto:
   - 1-2 sentenças anteriores
   - 1-2 sentenças posteriores
3. Criar prompt estruturado para Gemini
```

### Etapa 4: Tradução via Gemini API
```
1. Construir prompt com instruções claras:
   - Formato de entrada/saída esperado
   - Manter numeração para mapeamento
   - Preservar pontuação e formatação
2. Enviar request única (ou poucas) para Gemini
3. Parsear resposta e mapear traduções
```

### Etapa 5: Reconstrução do EPUB
```
1. Substituir sentenças traduzidas no texto original
2. Opcionalmente: aplicar estilização (cor, itálico) para diferenciar idiomas
3. Reconstruir capítulos com HTML atualizado
4. Gerar novo arquivo EPUB
5. Disponibilizar para download
```

---

## 📊 Estruturas de Dados

```python
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

class CEFRLevel(Enum):
    A1 = 1
    A2 = 2
    B1 = 3
    B2 = 4
    C1 = 5
    C2_PLUS = 6

@dataclass
class Sentence:
    text: str
    index: int
    paragraph_index: int
    chapter_index: int
    difficulty_score: float = 0.0
    cefr_level: Optional[CEFRLevel] = None
    should_translate: bool = False
    translated_text: Optional[str] = None

@dataclass
class Paragraph:
    sentences: List[Sentence]
    original_html: str
    index: int
    chapter_index: int

@dataclass
class Chapter:
    title: str
    paragraphs: List[Paragraph]
    original_html: str
    index: int
    file_name: str

@dataclass
class EpubStructure:
    title: str
    author: str
    chapters: List[Chapter]
    metadata: dict
    resources: List[bytes]  # imagens, CSS, etc.
```

---

## 🤖 Prompt do Gemini

```markdown
You are a professional translator helping create a bilingual learning book.

**Task:** Translate ONLY the sentences marked with [TRANSLATE] from {source_lang} to {target_lang}.

**Important Rules:**
1. Keep the exact sentence numbering in your response
2. Only translate sentences marked with [TRANSLATE]
3. Maintain the same tone and style
4. Preserve proper nouns unless they have common translations
5. Return ONLY the translations in the format: "ID: translated text"

**Input:**
[CONTEXT] 1: The sun was setting over the mountains.
[TRANSLATE] 2: She walked slowly along the path.
[CONTEXT] 3: The birds were singing their evening songs.
[TRANSLATE] 4: It was a beautiful moment of peace.
[CONTEXT] 5: She smiled, feeling grateful.

**Expected Output Format:**
2: Ela caminhou lentamente pelo caminho.
4: Foi um lindo momento de paz.
```

---

## 🎨 Interface Streamlit

### Página Principal
```
┌─────────────────────────────────────────────────────────────────┐
│  📚 Multi-Language Books                                        │
│  Transforme livros em ferramentas de aprendizado de idiomas     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📤 Upload do Livro                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Arraste seu arquivo EPUB aqui ou clique para selecionar │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ⚙️ Configurações                                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Idioma do livro:     [English ▼]                        │   │
│  │ Seu idioma nativo:   [Português ▼]                      │   │
│  │ Seu nível:           [B1 ▼]                             │   │
│  │                                                          │   │
│  │ ☑️ Destacar texto traduzido com cor diferente            │   │
│  │ ☑️ Mostrar estatísticas de tradução                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [🚀 Processar Livro]                                           │
│                                                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45%                   │
│  Processando capítulo 5 de 12...                                │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  📊 Estatísticas                                                │
│  • Total de sentenças: 2,450                                    │
│  • Sentenças traduzidas: 1,225 (50%)                           │
│  • Sentenças mantidas no original: 1,225 (50%)                 │
│                                                                 │
│  [📥 Baixar EPUB Multi-Idioma]                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura de Arquivos do Projeto

```
multi-language-books/
├── streamlit_app.py          # Aplicação principal Streamlit
├── requirements.txt          # Dependências
├── config/
│   ├── __init__.py
│   └── settings.py           # Configurações (API keys, thresholds)
├── src/
│   ├── __init__.py
│   ├── epub_parser.py        # Parser de EPUB
│   ├── difficulty_analyzer.py # Análise de dificuldade
│   ├── translation_engine.py  # Motor de tradução Gemini
│   ├── epub_generator.py      # Gerador de EPUB
│   └── utils.py              # Funções utilitárias
├── tests/
│   ├── test_parser.py
│   ├── test_analyzer.py
│   └── test_translation.py
└── README.md
```

---

## 📋 Dependências (requirements.txt)

```
streamlit>=1.28.0
ebooklib>=0.18
beautifulsoup4>=4.12.0
wordfreq>=3.0.0
google-genai>=1.0.0
lxml>=4.9.0
nltk>=3.8.0
```

---

## 🚀 Fases de Implementação

### Fase 1: Setup e Parser (Dia 1-2)
- [X] Configurar estrutura do projeto
- [X] Implementar `epub_parser.py`
- [X] Testes com diferentes EPUBs
- [x] Extrair e segmentar sentenças corretamente

### Fase 2: Análise de Dificuldade (Dia 3-4)
- [X] Implementar `difficulty_analyzer.py`
- [X] Calibrar thresholds CEFR
- [X] Testar com textos de diferentes níveis
- [X] Ajustar algoritmo de classificação

### Fase 3: Motor de Tradução (Dia 5-6)
- [X] Implementar `translation_engine.py`
- [X] Criar prompts otimizados para Gemini
- [X] Implementar batching inteligente
- [X] Tratamento de erros e retry

### Fase 4: Gerador de EPUB (Dia 7-8)
- [X] Implementar `epub_generator.py`
- [X] Preservar formatação original
- [X] Adicionar estilização para idiomas
- [X] Testar em diferentes leitores

### Fase 5: Interface Streamlit (Dia 9-10)
- [ ] Implementar UI completa
- [ ] Adicionar barra de progresso
- [ ] Implementar preview de resultado
- [ ] Polish e UX improvements

### Fase 6: Testes e Refinamento (Dia 11-12)
- [ ] Testes end-to-end
- [ ] Otimização de performance
- [ ] Documentação
- [ ] Deploy

---

## ⚠️ Considerações Importantes

### Limitações Conhecidas
1. **wordfreq** pode não ter dados para todos os idiomas
2. Sentenças com vocabulário muito técnico podem ser mal classificadas
3. Expressões idiomáticas podem ter frequência distorcida

### Mitigações
1. Fallback para análise simples quando wordfreq não disponível
2. Permitir ajuste manual de threshold pelo usuário
3. Considerar comprimento médio das palavras como fator adicional

### Rate Limiting Gemini
- Modelo `gemini-3-flash-preview` tem limits generosos
- Combinar máximo de texto possível em cada request
- Implementar retry com exponential backoff

---

## 🔑 Configuração da API

```python
# config/settings.py
import os

GEMINI_API_KEY = "AIzaSyAz4y0DHk-Z--_T3Lo0TKOYBNZL5i3OocI"
GEMINI_MODEL = "gemini-3-flash-preview"

# Thresholds CEFR (Zipf frequency)
CEFR_THRESHOLDS = {
    "A1": 6.0,
    "A2": 5.5,
    "B1": 5.0,
    "B2": 4.5,
    "C1": 4.0,
    "C2+": 0.0  # Qualquer valor abaixo de C1
}

# Idiomas suportados
SUPPORTED_LANGUAGES = {
    "en": "English",
    "pt": "Português",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "jp": "日本語",
    "ko": "한국어"
}
```

---

## 📈 Métricas de Sucesso

1. **Precisão da classificação CEFR**: >= 80% de concordância com avaliação humana
2. **Qualidade da tradução**: Feedback positivo dos usuários
3. **Performance**: Processar livro médio (200 páginas) em < 5 minutos
4. **Usabilidade**: Interface intuitiva, sem necessidade de manual

---

## 🔮 Melhorias Futuras

1. **Modo adaptativo**: Ajustar nível automaticamente baseado no progresso
2. **Glossário**: Extrair e exibir vocabulário novo
3. **Áudio**: Integrar TTS para pronúncia
4. **Spaced Repetition**: Integrar com Anki para vocabulário
5. **Múltiplos formatos**: Suportar PDF, MOBI, TXT
6. **Cache**: Salvar traduções para reutilização
