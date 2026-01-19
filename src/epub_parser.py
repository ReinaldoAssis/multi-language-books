"""
Parser de arquivos EPUB para o Multi-Language Books

Responsabilidades:
- Ler arquivo EPUB usando ebooklib
- Extrair capítulos e estrutura
- Separar texto de corpo (excluindo metadados, TOC, etc.)
- Preservar formatação HTML/CSS original
- Dividir texto em sentenças
"""
import re
import io
import warnings
from typing import List, Optional, Tuple, Union, BinaryIO
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
import nltk

from .models import Sentence, Paragraph, Chapter, EpubStructure

# Suprimir warning de XML parseado como HTML
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Garantir que o tokenizador de sentenças está disponível
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)


class EpubParser:
    """Parser de arquivos EPUB"""
    
    # Tags que geralmente contêm texto de corpo
    BODY_TAGS = {'p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                 'blockquote', 'li', 'td', 'th', 'caption', 'figcaption'}
    
    # Tags que devem ser ignoradas (navegação, metadados, etc.)
    IGNORE_TAGS = {'nav', 'script', 'style', 'head', 'meta', 'link', 
                   'toc', 'landmarks', 'page-list'}
    
    # Classes/IDs que indicam conteúdo não-corpo
    IGNORE_CLASSES = {'toc', 'table-of-contents', 'nav', 'navigation',
                      'footnote', 'endnote', 'copyright', 'dedication'}
    
    # Padrões de texto a ignorar (pagebreaks, marcadores especiais, etc.)
    IGNORE_TEXT_PATTERNS = [
        r'^\?pagebreak.*\?$',           # ?pagebreak number="1"?
        r'^\[pagebreak\]$',              # [pagebreak]
        r'^<pagebreak.*/>$',             # <pagebreak/>
        r'^\s*$',                        # Texto vazio ou só espaços
        r'^[\d\s]+$',                    # Só números (páginas)
    ]
    
    def __init__(self, language: str = "en"):
        """
        Inicializa o parser.
        
        Args:
            language: Código ISO do idioma para tokenização de sentenças
        """
        self.language = language
        self._sentence_counter = 0
        
    def parse(self, epub_source: Union[str, Path, BinaryIO, bytes]) -> EpubStructure:
        """
        Faz o parsing de um arquivo EPUB.
        
        Args:
            epub_source: Caminho do arquivo, objeto file-like, ou bytes
            
        Returns:
            EpubStructure com a estrutura completa do livro
        """
        self._sentence_counter = 0
        
        # Carregar o EPUB
        book = self._load_epub(epub_source)
        
        # Extrair metadados
        title = self._get_metadata(book, 'title') or "Untitled"
        author = self._get_metadata(book, 'creator') or "Unknown"
        language = self._get_metadata(book, 'language') or self.language
        
        # Atualizar idioma se detectado
        self.language = language
        
        metadata = {
            'title': title,
            'author': author,
            'language': language,
            'identifier': self._get_metadata(book, 'identifier'),
            'publisher': self._get_metadata(book, 'publisher'),
            'date': self._get_metadata(book, 'date'),
        }
        
        # Extrair capítulos
        chapters = self._extract_chapters(book)
        
        return EpubStructure(
            title=title,
            author=author,
            chapters=chapters,
            metadata=metadata,
            original_epub=book,
            language=language
        )
    
    def _load_epub(self, epub_source: Union[str, Path, BinaryIO, bytes]) -> epub.EpubBook:
        """Carrega o arquivo EPUB de várias fontes"""
        if isinstance(epub_source, (str, Path)):
            return epub.read_epub(str(epub_source))
        elif isinstance(epub_source, bytes):
            return epub.read_epub(io.BytesIO(epub_source))
        else:
            # Assume file-like object
            return epub.read_epub(epub_source)
    
    def _get_metadata(self, book: epub.EpubBook, key: str) -> Optional[str]:
        """Extrai metadado do livro"""
        try:
            metadata = book.get_metadata('DC', key)
            if metadata:
                return metadata[0][0]
        except (IndexError, KeyError):
            pass
        return None
    
    def _extract_chapters(self, book: epub.EpubBook) -> List[Chapter]:
        """Extrai todos os capítulos do livro"""
        chapters = []
        chapter_index = 0
        
        # Iterar sobre os documentos (XHTML/HTML)
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Verificar se é conteúdo de corpo (não TOC, nav, etc.)
                if self._is_content_document(item):
                    chapter = self._parse_chapter(item, chapter_index)
                    if chapter and chapter.paragraphs:
                        chapters.append(chapter)
                        chapter_index += 1
        
        return chapters
    
    def _is_content_document(self, item: epub.EpubItem) -> bool:
        """Verifica se o documento é conteúdo de corpo (não navegação/TOC)"""
        file_name = item.get_name().lower()
        
        # Ignorar arquivos de navegação comuns
        ignore_patterns = ['toc', 'nav', 'cover', 'title', 'copyright', 
                          'dedication', 'contents']
        
        for pattern in ignore_patterns:
            if pattern in file_name:
                # Verificar se realmente é navegação analisando o conteúdo
                content = item.get_content().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(content, 'lxml')
                
                # Se tiver tag nav ou epub:type="toc", é navegação
                if soup.find('nav') or soup.find(attrs={'epub:type': 'toc'}):
                    return False
        
        return True
    
    def _parse_chapter(self, item: epub.EpubItem, chapter_index: int) -> Optional[Chapter]:
        """Faz o parsing de um capítulo"""
        try:
            content = item.get_content().decode('utf-8', errors='ignore')
        except Exception:
            return None
        
        soup = BeautifulSoup(content, 'lxml')
        
        # Extrair título do capítulo
        title = self._extract_chapter_title(soup)
        
        # Extrair parágrafos
        paragraphs = self._extract_paragraphs(soup, chapter_index)
        
        if not paragraphs:
            return None
        
        return Chapter(
            title=title,
            paragraphs=paragraphs,
            original_html=content,
            index=chapter_index,
            file_name=item.get_name(),
            epub_item=item
        )
    
    def _extract_chapter_title(self, soup: BeautifulSoup) -> str:
        """Extrai o título do capítulo"""
        # Tentar encontrar h1, h2, etc.
        for tag in ['h1', 'h2', 'h3']:
            header = soup.find(tag)
            if header:
                return header.get_text(strip=True)
        
        # Tentar título da página
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        return "Chapter"
    
    def _extract_paragraphs(self, soup: BeautifulSoup, chapter_index: int) -> List[Paragraph]:
        """Extrai parágrafos do HTML"""
        paragraphs = []
        paragraph_index = 0
        
        # Encontrar body ou main content
        body = soup.find('body') or soup
        
        # Processar elementos de texto
        for element in body.find_all(self.BODY_TAGS):
            # Pular se estiver dentro de tags ignoradas
            if self._should_ignore_element(element):
                continue
            
            # Extrair texto do elemento
            text = self._extract_text(element)
            
            if not text or len(text.strip()) < 3:
                continue
            
            # Dividir em sentenças
            sentences = self._split_into_sentences(text, paragraph_index, chapter_index)
            
            if sentences:
                paragraph = Paragraph(
                    sentences=sentences,
                    original_html=str(element),
                    original_text=text,
                    index=paragraph_index,
                    chapter_index=chapter_index,
                    tag_name=element.name,
                    tag_attrs=dict(element.attrs) if element.attrs else {}
                )
                paragraphs.append(paragraph)
                paragraph_index += 1
        
        return paragraphs
    
    def _should_ignore_element(self, element: Tag) -> bool:
        """Verifica se o elemento deve ser ignorado"""
        # Verificar tags pai
        for parent in element.parents:
            if parent.name in self.IGNORE_TAGS:
                return True
            
            # Verificar classes do pai
            if parent.get('class'):
                classes = parent.get('class')
                if isinstance(classes, list):
                    classes = ' '.join(classes)
                classes = classes.lower()
                
                for ignore_class in self.IGNORE_CLASSES:
                    if ignore_class in classes:
                        return True
        
        # Verificar classes do próprio elemento
        if element.get('class'):
            classes = element.get('class')
            if isinstance(classes, list):
                classes = ' '.join(classes)
            classes = classes.lower()
            
            for ignore_class in self.IGNORE_CLASSES:
                if ignore_class in classes:
                    return True
        
        # Verificar epub:type
        epub_type = element.get('epub:type', '')
        if any(t in epub_type for t in ['toc', 'footnote', 'endnote']):
            return True
        
        return False
    
    def _extract_text(self, element: Tag) -> str:
        """Extrai texto limpo de um elemento HTML"""
        # Obter texto, preservando espaços entre elementos inline
        texts = []
        for child in element.children:
            if isinstance(child, NavigableString):
                texts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in ['br']:
                    texts.append(' ')
                elif child.name in ['em', 'strong', 'i', 'b', 'span', 'a']:
                    texts.append(child.get_text())
                # Ignorar outros elementos inline/block que são processados separadamente
        
        text = ' '.join(texts)
        
        # Limpar espaços múltiplos
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _split_into_sentences(self, text: str, paragraph_index: int, 
                              chapter_index: int) -> List[Sentence]:
        """Divide texto em sentenças"""
        sentences = []
        
        # Usar NLTK para tokenização de sentenças
        try:
            # Mapear código de idioma para nome do tokenizador NLTK
            lang_map = {
                'en': 'english',
                'pt': 'portuguese',
                'es': 'spanish',
                'fr': 'french',
                'de': 'german',
                'it': 'italian',
                'nl': 'dutch',
                'ru': 'russian',
            }
            
            tokenizer_lang = lang_map.get(self.language[:2], 'english')
            sent_tokenizer = nltk.data.load(f'tokenizers/punkt_tab/{tokenizer_lang}.pickle')
            sentence_texts = sent_tokenizer.tokenize(text)
        except Exception:
            # Fallback para tokenização simples
            sentence_texts = self._simple_sentence_split(text)
        
        # Rastrear posição no texto original
        current_pos = 0
        
        for sent_text in sentence_texts:
            sent_text = sent_text.strip()
            if not sent_text:
                continue
            
            # Verificar se a sentença deve ser ignorada
            if self._should_ignore_sentence(sent_text):
                continue
            
            # Encontrar posição no texto original
            start_pos = text.find(sent_text, current_pos)
            if start_pos == -1:
                start_pos = current_pos
            end_pos = start_pos + len(sent_text)
            current_pos = end_pos
            
            sentence = Sentence(
                text=sent_text,
                index=self._sentence_counter,
                paragraph_index=paragraph_index,
                chapter_index=chapter_index,
                start_pos=start_pos,
                end_pos=end_pos
            )
            sentences.append(sentence)
            self._sentence_counter += 1
        
        return sentences
    
    def _simple_sentence_split(self, text: str) -> List[str]:
        """Divisão simples de sentenças como fallback"""
        # Regex para encontrar finais de sentença
        pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _should_ignore_sentence(self, text: str) -> bool:
        """
        Verifica se uma sentença deve ser ignorada.
        
        Args:
            text: Texto da sentença
            
        Returns:
            True se deve ser ignorada
        """
        # Verificar padrões de texto a ignorar
        for pattern in self.IGNORE_TEXT_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        
        # Ignorar texto muito curto (menos de 2 palavras, exceto títulos)
        words = text.split()
        if len(words) < 2 and len(text) < 20:
            # Permitir títulos de capítulos curtos
            if not any(c.isalpha() for c in text):
                return True
        
        return False


def parse_epub(epub_source: Union[str, Path, BinaryIO, bytes], 
               language: str = "en") -> EpubStructure:
    """
    Função de conveniência para parsing de EPUB.
    
    Args:
        epub_source: Caminho do arquivo, objeto file-like, ou bytes
        language: Código ISO do idioma (para tokenização)
        
    Returns:
        EpubStructure com a estrutura completa do livro
    """
    parser = EpubParser(language=language)
    return parser.parse(epub_source)
