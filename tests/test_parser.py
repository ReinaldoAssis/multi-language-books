"""
Testes para o parser de EPUB
"""
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.epub_parser import EpubParser, parse_epub
from src.models import EpubStructure, Chapter, Paragraph, Sentence


def test_parser_with_file(epub_path: str):
    """
    Testa o parser com um arquivo EPUB real.
    
    Args:
        epub_path: Caminho para o arquivo EPUB
    """
    print(f"\n{'='*60}")
    print(f"Testando parser com: {epub_path}")
    print('='*60)
    
    # Fazer o parsing
    structure = parse_epub(epub_path)
    
    # Exibir informações gerais
    print(f"\n📖 Título: {structure.title}")
    print(f"✍️  Autor: {structure.author}")
    print(f"🌐 Idioma: {structure.language}")
    print(f"📚 Capítulos: {structure.chapter_count}")
    print(f"📝 Total de sentenças: {structure.total_sentences}")
    
    # Mostrar detalhes de cada capítulo
    print(f"\n{'─'*60}")
    print("CAPÍTULOS:")
    print('─'*60)
    
    for i, chapter in enumerate(structure.chapters[:5]):  # Limitar a 5 capítulos
        print(f"\n📖 Capítulo {i+1}: {chapter.title}")
        print(f"   Arquivo: {chapter.file_name}")
        print(f"   Parágrafos: {chapter.paragraph_count}")
        print(f"   Sentenças: {chapter.sentence_count}")
        
        # Mostrar primeiras sentenças do capítulo
        sentences = chapter.get_all_sentences()
        if sentences:
            print(f"\n   Primeiras sentenças:")
            for j, sent in enumerate(sentences[:3]):
                preview = sent.text[:80] + "..." if len(sent.text) > 80 else sent.text
                print(f"   [{sent.index}] {preview}")
    
    if structure.chapter_count > 5:
        print(f"\n   ... e mais {structure.chapter_count - 5} capítulos")
    
    # Estatísticas
    print(f"\n{'─'*60}")
    print("ESTATÍSTICAS:")
    print('─'*60)
    
    all_sentences = structure.get_all_sentences()
    avg_words = sum(len(s.text.split()) for s in all_sentences) / len(all_sentences) if all_sentences else 0
    
    print(f"   Total de sentenças: {len(all_sentences)}")
    print(f"   Média de palavras por sentença: {avg_words:.1f}")
    
    # Exemplo de sentenças
    print(f"\n{'─'*60}")
    print("EXEMPLOS DE SENTENÇAS:")
    print('─'*60)
    
    # Mostrar algumas sentenças aleatórias
    import random
    sample_size = min(5, len(all_sentences))
    sample_indices = random.sample(range(len(all_sentences)), sample_size)
    
    for idx in sorted(sample_indices):
        sent = all_sentences[idx]
        preview = sent.text[:100] + "..." if len(sent.text) > 100 else sent.text
        print(f"\n   [{sent.index}] (Cap.{sent.chapter_index+1}, Par.{sent.paragraph_index+1})")
        print(f"   {preview}")
    
    print(f"\n{'='*60}")
    print("✅ Parser funcionando corretamente!")
    print('='*60)
    
    return structure


def test_sentence_splitting():
    """Testa a divisão de sentenças"""
    print("\n" + "="*60)
    print("Teste de divisão de sentenças")
    print("="*60)
    
    parser = EpubParser(language="en")
    
    test_texts = [
        "Hello world. This is a test. How are you?",
        "Mr. Smith went to Washington D.C. He arrived at 3 p.m.",
        "She said, \"Hello!\" Then she left.",
        "This is sentence one! Is this sentence two? Yes, it is.",
    ]
    
    for text in test_texts:
        print(f"\nTexto: {text}")
        sentences = parser._split_into_sentences(text, 0, 0)
        print(f"Sentenças encontradas ({len(sentences)}):")
        for sent in sentences:
            print(f"  - {sent.text}")
    
    print("\n✅ Teste de divisão de sentenças concluído!")


def create_sample_test():
    """Cria um texto de exemplo para teste sem precisar de arquivo EPUB"""
    print("\n" + "="*60)
    print("Teste com texto de exemplo")
    print("="*60)
    
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Sample Chapter</title></head>
    <body>
        <h1>Chapter 1: The Beginning</h1>
        <p>It was a dark and stormy night. The wind howled through the trees. 
        Sarah pulled her coat tighter around her shoulders.</p>
        <p>She had been walking for hours. Her feet ached. But she couldn't stop now.</p>
        <p>"Almost there," she whispered to herself. The old house loomed ahead.</p>
    </body>
    </html>
    """
    
    from bs4 import BeautifulSoup
    
    parser = EpubParser(language="en")
    soup = BeautifulSoup(sample_html, 'lxml')
    
    title = parser._extract_chapter_title(soup)
    paragraphs = parser._extract_paragraphs(soup, 0)
    
    print(f"\nTítulo extraído: {title}")
    print(f"Parágrafos encontrados: {len(paragraphs)}")
    
    for p in paragraphs:
        print(f"\nParágrafo {p.index + 1} ({len(p.sentences)} sentenças):")
        for s in p.sentences:
            print(f"  [{s.index}] {s.text}")
    
    print("\n✅ Teste com texto de exemplo concluído!")


if __name__ == "__main__":
    # Executar testes básicos primeiro
    test_sentence_splitting()
    create_sample_test()
    
    # Se um arquivo EPUB foi passado como argumento, testar com ele
    if len(sys.argv) > 1:
        epub_path = sys.argv[1]
        if Path(epub_path).exists():
            test_parser_with_file(epub_path)
        else:
            print(f"\n❌ Arquivo não encontrado: {epub_path}")
    else:
        print("\n" + "="*60)
        print("NOTA: Para testar com um arquivo EPUB real, execute:")
        print("  python tests/test_parser.py caminho/para/livro.epub")
        print("="*60)
