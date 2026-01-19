"""
Modelos de dados para o Multi-Language Books
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class CEFRLevel(Enum):
    """Níveis de proficiência CEFR"""
    A1 = 1
    A2 = 2
    B1 = 3
    B2 = 4
    C1 = 5
    C2_PLUS = 6
    
    @classmethod
    def from_string(cls, level_str: str) -> "CEFRLevel":
        """Converte string para CEFRLevel"""
        mapping = {
            "A1": cls.A1,
            "A2": cls.A2,
            "B1": cls.B1,
            "B2": cls.B2,
            "C1": cls.C1,
            "C2+": cls.C2_PLUS,
            "C2": cls.C2_PLUS,
        }
        return mapping.get(level_str.upper(), cls.B1)
    
    def __str__(self) -> str:
        if self == CEFRLevel.C2_PLUS:
            return "C2+"
        return self.name
    
    def __ge__(self, other: "CEFRLevel") -> bool:
        return self.value >= other.value
    
    def __le__(self, other: "CEFRLevel") -> bool:
        return self.value <= other.value
    
    def __gt__(self, other: "CEFRLevel") -> bool:
        return self.value > other.value
    
    def __lt__(self, other: "CEFRLevel") -> bool:
        return self.value < other.value


@dataclass
class Sentence:
    """Representa uma sentença no texto"""
    text: str
    index: int  # Índice global da sentença no livro
    paragraph_index: int  # Índice do parágrafo dentro do capítulo
    chapter_index: int  # Índice do capítulo
    
    # Campos preenchidos durante análise de dificuldade
    difficulty_score: float = 0.0  # Zipf frequency média
    cefr_level: Optional[CEFRLevel] = None
    should_translate: bool = False
    
    # Campo preenchido após tradução
    translated_text: Optional[str] = None
    
    # Posição no texto original para reconstrução
    start_pos: int = 0  # Posição inicial no parágrafo
    end_pos: int = 0    # Posição final no parágrafo
    
    @property
    def is_translated(self) -> bool:
        """Verifica se a sentença foi traduzida"""
        return self.translated_text is not None
    
    @property
    def final_text(self) -> str:
        """Retorna o texto final (traduzido ou original)"""
        return self.translated_text if self.is_translated else self.text


@dataclass
class Paragraph:
    """Representa um parágrafo no texto"""
    sentences: List[Sentence]
    original_html: str  # HTML original para reconstrução
    original_text: str  # Texto puro extraído
    index: int  # Índice do parágrafo dentro do capítulo
    chapter_index: int
    
    # Tag HTML que envolve o parágrafo (p, div, etc.)
    tag_name: str = "p"
    tag_attrs: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def sentence_count(self) -> int:
        return len(self.sentences)
    
    @property
    def translated_count(self) -> int:
        return sum(1 for s in self.sentences if s.is_translated)
    
    def get_final_text(self) -> str:
        """Retorna o texto final com traduções aplicadas"""
        return " ".join(s.final_text for s in self.sentences)


@dataclass
class Chapter:
    """Representa um capítulo do livro"""
    title: str
    paragraphs: List[Paragraph]
    original_html: str  # HTML original completo
    index: int
    file_name: str  # Nome do arquivo no EPUB (ex: chapter1.xhtml)
    
    # Item do ebooklib para referência
    epub_item: Any = None
    
    @property
    def paragraph_count(self) -> int:
        return len(self.paragraphs)
    
    @property
    def sentence_count(self) -> int:
        return sum(p.sentence_count for p in self.paragraphs)
    
    @property
    def translated_count(self) -> int:
        return sum(p.translated_count for p in self.paragraphs)
    
    def get_all_sentences(self) -> List[Sentence]:
        """Retorna todas as sentenças do capítulo"""
        sentences = []
        for paragraph in self.paragraphs:
            sentences.extend(paragraph.sentences)
        return sentences


@dataclass
class EpubStructure:
    """Estrutura completa do EPUB"""
    title: str
    author: str
    chapters: List[Chapter]
    metadata: Dict[str, Any]
    
    # Recursos originais (CSS, imagens, fontes)
    # Mantidos como referência ao objeto epub original
    original_epub: Any = None
    
    # Idioma detectado do livro
    language: str = "en"
    
    @property
    def chapter_count(self) -> int:
        return len(self.chapters)
    
    @property
    def total_sentences(self) -> int:
        return sum(c.sentence_count for c in self.chapters)
    
    @property
    def total_translated(self) -> int:
        return sum(c.translated_count for c in self.chapters)
    
    @property
    def translation_percentage(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return (self.total_translated / self.total_sentences) * 100
    
    def get_all_sentences(self) -> List[Sentence]:
        """Retorna todas as sentenças do livro"""
        sentences = []
        for chapter in self.chapters:
            sentences.extend(chapter.get_all_sentences())
        return sentences
    
    def get_sentences_to_translate(self) -> List[Sentence]:
        """Retorna apenas sentenças marcadas para tradução"""
        return [s for s in self.get_all_sentences() if s.should_translate]


@dataclass
class TranslationRequest:
    """Request de tradução para o Gemini"""
    sentences: List[Sentence]  # Sentenças a traduzir
    context_before: List[Sentence]  # Contexto anterior
    context_after: List[Sentence]   # Contexto posterior
    source_lang: str
    target_lang: str
    
    def build_prompt_text(self) -> str:
        """Constrói o texto para o prompt do Gemini"""
        lines = []
        
        # Contexto anterior
        for s in self.context_before:
            lines.append(f"[CONTEXT] {s.index}: {s.text}")
        
        # Sentenças a traduzir
        for s in self.sentences:
            lines.append(f"[TRANSLATE] {s.index}: {s.text}")
        
        # Contexto posterior
        for s in self.context_after:
            lines.append(f"[CONTEXT] {s.index}: {s.text}")
        
        return "\n".join(lines)


@dataclass
class TranslationResult:
    """Resultado de uma tradução"""
    sentence_index: int
    original_text: str
    translated_text: str
    success: bool = True
    error_message: Optional[str] = None


@dataclass 
class ProcessingStats:
    """Estatísticas do processamento"""
    total_chapters: int = 0
    total_paragraphs: int = 0
    total_sentences: int = 0
    sentences_to_translate: int = 0
    sentences_translated: int = 0
    
    # Distribuição por nível CEFR
    cefr_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Tempo de processamento
    parsing_time: float = 0.0
    analysis_time: float = 0.0
    translation_time: float = 0.0
    generation_time: float = 0.0
    
    @property
    def total_time(self) -> float:
        return self.parsing_time + self.analysis_time + self.translation_time + self.generation_time
    
    @property
    def translation_percentage(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return (self.sentences_to_translate / self.total_sentences) * 100
