"""
Gerador de EPUB para o Multi-Language Books

Responsabilidades:
- Reconstruir EPUB com texto modificado
- Manter estrutura original (capítulos, formatação, imagens)
- Aplicar estilização opcional para diferenciar idiomas
"""
import re
import io
from typing import Optional, Dict, Any, List
from pathlib import Path
from copy import deepcopy

from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag

from .models import EpubStructure, Chapter, Paragraph, Sentence


class EpubGenerator:
    """Gerador de arquivos EPUB com texto multi-idioma"""
    
    # CSS para destacar texto traduzido
    TRANSLATED_STYLE_CSS = """
.translated-text {
    color: #2c3e50;
    font-style: italic;
}
.original-text {
    /* Texto original sem estilização adicional */
}
"""
    
    # CSS alternativo com cores mais sutis
    SUBTLE_STYLE_CSS = """
.translated-text {
    color: #34495e;
}
"""
    
    def __init__(self, 
                 highlight_translated: bool = True,
                 style_type: str = "default"):
        """
        Inicializa o gerador.
        
        Args:
            highlight_translated: Se True, destaca texto traduzido com estilo
            style_type: Tipo de estilo ("default", "subtle", "none")
        """
        self.highlight_translated = highlight_translated
        self.style_type = style_type
    
    def generate(self, structure: EpubStructure) -> bytes:
        """
        Gera um novo EPUB com as traduções aplicadas.
        
        Args:
            structure: Estrutura do EPUB com traduções
            
        Returns:
            Bytes do arquivo EPUB gerado
        """
        # Criar novo livro baseado no original
        if structure.original_epub:
            book = self._create_from_original(structure)
        else:
            book = self._create_new_book(structure)
        
        # Adicionar CSS de estilização se necessário
        if self.highlight_translated and self.style_type != "none":
            self._add_translation_styles(book)
        
        # Atualizar capítulos com traduções
        self._update_chapters(book, structure)
        
        # Gerar bytes do EPUB
        output = io.BytesIO()
        epub.write_epub(output, book)
        output.seek(0)
        
        return output.read()
    
    def _create_from_original(self, structure: EpubStructure) -> epub.EpubBook:
        """Cria livro baseado no original, preservando recursos"""
        original = structure.original_epub
        book = epub.EpubBook()
        
        # Copiar metadados
        book.set_identifier(structure.metadata.get('identifier', 'multi-lang-book'))
        book.set_title(f"{structure.title} (Multi-Language)")
        book.set_language(structure.language)
        
        # Adicionar autor
        book.add_author(structure.author)
        
        # Copiar todos os itens do original
        for item in original.get_items():
            # Pular documentos que serão recriados
            if item.get_type() == 9:  # ITEM_DOCUMENT
                # Será atualizado depois
                book.add_item(item)
            else:
                # Copiar outros recursos (CSS, imagens, fontes)
                book.add_item(item)
        
        # Copiar spine e TOC (garantindo que todos os itens tenham IDs válidos)
        book.spine = original.spine
        book.toc = self._sanitize_toc(original.toc)
        
        return book
    
    def _sanitize_toc(self, toc) -> list:
        """Garante que todos os itens do TOC tenham IDs válidos"""
        sanitized = []
        
        for i, item in enumerate(toc):
            if isinstance(item, tuple):
                # Seção com sub-itens
                section, sub_items = item
                sanitized_section = self._sanitize_toc_item(section, i)
                sanitized_sub = self._sanitize_toc(sub_items)
                sanitized.append((sanitized_section, sanitized_sub))
            else:
                # Item simples (Link ou Section)
                sanitized.append(self._sanitize_toc_item(item, i))
        
        return sanitized
    
    def _sanitize_toc_item(self, item, index: int):
        """Garante que um item do TOC tenha ID válido"""
        if hasattr(item, 'uid') and item.uid is None:
            # Gerar ID baseado no título ou índice
            if hasattr(item, 'title') and item.title:
                item.uid = f"toc_{index}_{item.title.replace(' ', '_')[:20]}"
            else:
                item.uid = f"toc_item_{index}"
        
        # Para Links, garantir que o uid está definido
        if isinstance(item, epub.Link):
            if item.uid is None:
                if item.title:
                    item.uid = f"link_{index}_{item.title.replace(' ', '_')[:20]}"
                else:
                    item.uid = f"link_{index}"
        
        return item
    
    def _create_new_book(self, structure: EpubStructure) -> epub.EpubBook:
        """Cria um novo livro do zero"""
        book = epub.EpubBook()
        
        book.set_identifier(structure.metadata.get('identifier', 'multi-lang-book'))
        book.set_title(f"{structure.title} (Multi-Language)")
        book.set_language(structure.language)
        book.add_author(structure.author)
        
        # Criar capítulos
        spine = ['nav']
        toc = []
        
        for chapter in structure.chapters:
            # Criar item EPUB
            epub_chapter = epub.EpubHtml(
                title=chapter.title,
                file_name=chapter.file_name,
                lang=structure.language
            )
            epub_chapter.set_content(chapter.original_html)
            
            book.add_item(epub_chapter)
            spine.append(epub_chapter)
            toc.append(epub.Link(chapter.file_name, chapter.title, chapter.file_name))
        
        book.toc = toc
        book.spine = spine
        
        # Adicionar navegação
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        return book
    
    def _add_translation_styles(self, book: epub.EpubBook) -> None:
        """Adiciona CSS para estilização de traduções"""
        # Escolher CSS baseado no tipo de estilo
        if self.style_type == "subtle":
            css_content = self.SUBTLE_STYLE_CSS
        else:
            css_content = self.TRANSLATED_STYLE_CSS
        
        # Criar item CSS
        style_item = epub.EpubItem(
            uid="translation_styles",
            file_name="styles/translation.css",
            media_type="text/css",
            content=css_content.encode('utf-8')
        )
        
        book.add_item(style_item)
    
    def _update_chapters(self, book: epub.EpubBook, structure: EpubStructure) -> None:
        """Atualiza os capítulos com as traduções"""
        # Criar mapa de capítulos por nome de arquivo
        chapter_map = {ch.file_name: ch for ch in structure.chapters}
        
        # Iterar sobre itens do livro
        for item in book.get_items():
            if item.get_type() == 9:  # ITEM_DOCUMENT
                file_name = item.get_name()
                
                if file_name in chapter_map:
                    chapter = chapter_map[file_name]
                    
                    # Atualizar conteúdo
                    new_content = self._rebuild_chapter_html(item, chapter)
                    item.set_content(new_content.encode('utf-8'))
    
    def _rebuild_chapter_html(self, item: epub.EpubItem, chapter: Chapter) -> str:
        """
        Reconstrói o HTML do capítulo com traduções.
        
        Args:
            item: Item EPUB original
            chapter: Chapter com traduções
            
        Returns:
            HTML atualizado
        """
        try:
            content = item.get_content().decode('utf-8', errors='ignore')
        except:
            return chapter.original_html
        
        soup = BeautifulSoup(content, 'lxml')
        
        # Adicionar link para CSS de tradução se necessário
        if self.highlight_translated and self.style_type != "none":
            self._add_css_link(soup)
        
        # Criar mapa de parágrafos por índice
        para_map = {p.index: p for p in chapter.paragraphs}
        
        # Encontrar body
        body = soup.find('body')
        if not body:
            return str(soup)
        
        # Processar parágrafos
        self._process_paragraphs(body, para_map, chapter.index)
        
        return str(soup)
    
    def _add_css_link(self, soup: BeautifulSoup) -> None:
        """Adiciona link para CSS de tradução no head"""
        head = soup.find('head')
        if head:
            # Verificar se já existe
            existing = head.find('link', href=lambda x: x and 'translation.css' in x)
            if not existing:
                link = soup.new_tag('link', rel='stylesheet', 
                                   type='text/css', href='../styles/translation.css')
                head.append(link)
    
    def _process_paragraphs(self, body: Tag, para_map: Dict[int, Paragraph], 
                           chapter_index: int) -> None:
        """
        Processa parágrafos substituindo texto traduzido.
        
        Estratégia: Para cada parágrafo na estrutura, encontrar o elemento
        correspondente no HTML e substituir o texto.
        """
        # Tags de parágrafo a processar
        para_tags = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                     'blockquote', 'li', 'td', 'th'}
        
        # Processar cada parágrafo da estrutura
        for para_idx, paragraph in para_map.items():
            # Verificar se há sentenças traduzidas
            translated_sentences = [s for s in paragraph.sentences 
                                   if s.translated_text and s.translated_text != s.text]
            
            if not translated_sentences:
                continue
            
            # Encontrar elemento correspondente no HTML
            # Usar o texto original para localizar
            element = self._find_paragraph_element(body, paragraph, para_tags)
            
            if element:
                # Substituir conteúdo
                self._replace_paragraph_content(element, paragraph)
    
    def _find_paragraph_element(self, body: Tag, paragraph: Paragraph, 
                                para_tags: set) -> Optional[Tag]:
        """
        Encontra o elemento HTML correspondente ao parágrafo.
        
        Usa o texto original do parágrafo para localização.
        """
        original_text = paragraph.original_text.strip()
        
        if not original_text:
            return None
        
        # Buscar por texto parcial (primeiras palavras)
        search_text = ' '.join(original_text.split()[:5])
        
        for tag_name in para_tags:
            for element in body.find_all(tag_name):
                element_text = element.get_text(strip=True)
                if search_text in element_text:
                    # Verificar se é o parágrafo correto (comprimento similar)
                    if abs(len(element_text) - len(original_text)) < len(original_text) * 0.3:
                        return element
        
        return None
    
    def _replace_paragraph_content(self, element: Tag, paragraph: Paragraph) -> None:
        """
        Substitui o conteúdo de um elemento com as traduções.
        
        Preserva tags inline (em, strong, etc.) quando possível.
        """
        # Construir novo texto
        new_text_parts = []
        
        for sentence in paragraph.sentences:
            if sentence.translated_text and sentence.translated_text != sentence.text:
                # Sentença traduzida
                if self.highlight_translated and self.style_type != "none":
                    new_text_parts.append(f'<span class="translated-text">{sentence.translated_text}</span>')
                else:
                    new_text_parts.append(sentence.translated_text)
            else:
                # Sentença original
                if self.highlight_translated and self.style_type != "none":
                    new_text_parts.append(f'<span class="original-text">{sentence.text}</span>')
                else:
                    new_text_parts.append(sentence.text)
        
        new_content = ' '.join(new_text_parts)
        
        # Limpar elemento e inserir novo conteúdo
        element.clear()
        
        # Parsear o novo conteúdo como HTML
        new_soup = BeautifulSoup(new_content, 'lxml')
        
        # Inserir conteúdo (pode ter spans)
        for child in new_soup.body.children if new_soup.body else []:
            if isinstance(child, NavigableString):
                element.append(NavigableString(str(child)))
            else:
                element.append(child)


def generate_epub(structure: EpubStructure,
                 highlight_translated: bool = True,
                 style_type: str = "default") -> bytes:
    """
    Função de conveniência para gerar EPUB.
    
    Args:
        structure: Estrutura do EPUB com traduções
        highlight_translated: Se True, destaca texto traduzido
        style_type: Tipo de estilo ("default", "subtle", "none")
        
    Returns:
        Bytes do arquivo EPUB
    """
    generator = EpubGenerator(
        highlight_translated=highlight_translated,
        style_type=style_type
    )
    return generator.generate(structure)


def save_epub(structure: EpubStructure,
              output_path: str,
              highlight_translated: bool = True,
              style_type: str = "default") -> None:
    """
    Gera e salva EPUB em arquivo.
    
    Args:
        structure: Estrutura do EPUB com traduções
        output_path: Caminho do arquivo de saída
        highlight_translated: Se True, destaca texto traduzido
        style_type: Tipo de estilo
    """
    epub_bytes = generate_epub(structure, highlight_translated, style_type)
    
    with open(output_path, 'wb') as f:
        f.write(epub_bytes)
