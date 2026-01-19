"""
Testes para o gerador de EPUB
"""
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.epub_generator import EpubGenerator, generate_epub, save_epub
from src.epub_parser import parse_epub
from src.models import Sentence, Paragraph, Chapter, EpubStructure, CEFRLevel


def test_generator_basic():
    """Testa geração básica de EPUB"""
    print("\n" + "="*60)
    print("Teste de Geração Básica de EPUB")
    print("="*60)
    
    # Criar estrutura mínima de teste
    sentence1 = Sentence(
        text="Hello world.",
        index=0,
        paragraph_index=0,
        chapter_index=0,
        translated_text="Olá mundo."
    )
    
    sentence2 = Sentence(
        text="How are you?",
        index=1,
        paragraph_index=0,
        chapter_index=0,
        translated_text=None  # Não traduzida
    )
    
    paragraph = Paragraph(
        sentences=[sentence1, sentence2],
        original_html="<p>Hello world. How are you?</p>",
        original_text="Hello world. How are you?",
        index=0,
        chapter_index=0
    )
    
    chapter = Chapter(
        title="Chapter 1",
        paragraphs=[paragraph],
        original_html="<html><body><p>Hello world. How are you?</p></body></html>",
        index=0,
        file_name="chapter1.xhtml"
    )
    
    structure = EpubStructure(
        title="Test Book",
        author="Test Author",
        chapters=[chapter],
        metadata={},
        language="en"
    )
    
    print("\n  Estrutura de teste criada:")
    print(f"    Capítulos: {structure.chapter_count}")
    print(f"    Sentenças: {structure.total_sentences}")
    
    # Testar geração
    generator = EpubGenerator(highlight_translated=True)
    
    try:
        epub_bytes = generator.generate(structure)
        print(f"\n  ✓ EPUB gerado: {len(epub_bytes)} bytes")
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
    
    print("\n✅ Teste básico concluído!")


def test_css_injection():
    """Testa injeção de CSS para estilização"""
    print("\n" + "="*60)
    print("Teste de Injeção de CSS")
    print("="*60)
    
    generator = EpubGenerator(highlight_translated=True, style_type="default")
    
    print("\n  CSS padrão:")
    print("  " + "-" * 40)
    for line in generator.TRANSLATED_STYLE_CSS.strip().split('\n'):
        print(f"    {line}")
    
    generator_subtle = EpubGenerator(highlight_translated=True, style_type="subtle")
    
    print("\n  CSS sutil:")
    print("  " + "-" * 40)
    for line in generator_subtle.SUBTLE_STYLE_CSS.strip().split('\n'):
        print(f"    {line}")
    
    print("\n✅ Teste de CSS concluído!")


def test_text_replacement():
    """Testa substituição de texto no HTML"""
    print("\n" + "="*60)
    print("Teste de Substituição de Texto")
    print("="*60)
    
    from bs4 import BeautifulSoup
    
    # HTML de teste
    html = """
    <html>
    <body>
        <p>The sun was setting. She walked along the path.</p>
        <p>Birds were singing. It was peaceful.</p>
    </body>
    </html>
    """
    
    # Criar sentenças
    sentences = [
        Sentence(text="The sun was setting.", index=0, paragraph_index=0, 
                chapter_index=0, translated_text="O sol estava se pondo."),
        Sentence(text="She walked along the path.", index=1, paragraph_index=0,
                chapter_index=0, translated_text=None),
    ]
    
    paragraph = Paragraph(
        sentences=sentences,
        original_html="<p>The sun was setting. She walked along the path.</p>",
        original_text="The sun was setting. She walked along the path.",
        index=0,
        chapter_index=0
    )
    
    print("\n  HTML Original:")
    print(f"    {paragraph.original_html}")
    
    print("\n  Sentenças:")
    for s in sentences:
        status = "✓ Traduzida" if s.translated_text else "✗ Original"
        print(f"    [{status}] {s.text}")
        if s.translated_text:
            print(f"               → {s.translated_text}")
    
    # Testar substituição
    generator = EpubGenerator(highlight_translated=True)
    
    soup = BeautifulSoup(html, 'lxml')
    body = soup.find('body')
    
    para_map = {0: paragraph}
    generator._process_paragraphs(body, para_map, 0)
    
    print("\n  HTML Resultante:")
    for p in soup.find_all('p'):
        print(f"    {p}")
    
    print("\n✅ Teste de substituição concluído!")


def test_with_epub(epub_path: str):
    """Testa geração com EPUB real (sem tradução, apenas estrutura)"""
    print("\n" + "="*60)
    print(f"Teste com EPUB Real: {epub_path}")
    print("="*60)
    
    # Parse
    structure = parse_epub(epub_path)
    
    print(f"\n  📖 {structure.title}")
    print(f"  ✍️  {structure.author}")
    print(f"  📚 {structure.chapter_count} capítulos")
    
    # Simular algumas traduções
    all_sentences = structure.get_all_sentences()
    
    # Traduzir as primeiras 10 sentenças como teste
    for i, sent in enumerate(all_sentences[:10]):
        sent.translated_text = f"[TRADUÇÃO {i}] {sent.text[:30]}..."
    
    print(f"\n  Simulando tradução de 10 sentenças...")
    
    # Gerar EPUB
    output_path = "output/test_generator.epub"
    Path("output").mkdir(exist_ok=True)
    
    try:
        save_epub(structure, output_path, highlight_translated=True)
        
        import os
        size = os.path.getsize(output_path)
        print(f"\n  ✓ EPUB gerado: {output_path}")
        print(f"  ✓ Tamanho: {size / 1024:.1f} KB")
        
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Teste com EPUB real concluído!")


if __name__ == "__main__":
    # Testes básicos
    test_generator_basic()
    test_css_injection()
    test_text_replacement()
    
    # Teste com EPUB real se fornecido
    if len(sys.argv) > 1:
        epub_path = sys.argv[1]
        if Path(epub_path).exists():
            test_with_epub(epub_path)
        else:
            print(f"\n❌ Arquivo não encontrado: {epub_path}")
    else:
        print("\n" + "-"*60)
        print("NOTA: Para testar com um arquivo EPUB real, execute:")
        print("  python tests/test_generator.py caminho/para/livro.epub")
        print("-"*60)
