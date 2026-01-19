"""
Testes para o motor de tradução
"""
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.translation_engine import (
    TranslationEngine,
    translate_epub_structure,
    translate_text
)
from src.epub_parser import parse_epub
from src.difficulty_analyzer import analyze_difficulty
from src.models import Sentence, CEFRLevel


def test_single_translation():
    """Testa tradução de texto simples"""
    print("\n" + "="*60)
    print("Teste de Tradução Simples")
    print("="*60)
    
    test_texts = [
        ("Hello, how are you?", "en", "pt"),
        ("The weather is beautiful today.", "en", "pt"),
        ("She decided to pursue her dreams.", "en", "pt"),
        ("Olá, como vai você?", "pt", "en"),
        ("Bonjour, comment allez-vous?", "fr", "pt"),
    ]
    
    for text, source, target in test_texts:
        print(f"\n[{source} → {target}]")
        print(f"  Original:  {text}")
        
        try:
            translation = translate_text(text, source, target)
            print(f"  Tradução:  {translation}")
        except Exception as e:
            print(f"  ❌ Erro: {e}")
    
    print("\n✅ Teste de tradução simples concluído!")


def test_batch_creation():
    """Testa criação de batches"""
    print("\n" + "="*60)
    print("Teste de Criação de Batches")
    print("="*60)
    
    # Criar sentenças de teste
    sentences = []
    for i in range(20):
        sent = Sentence(
            text=f"This is test sentence number {i}. It contains some words.",
            index=i,
            paragraph_index=i // 5,
            chapter_index=0
        )
        # Marcar algumas para tradução
        sent.should_translate = (i % 3 == 0)  # Traduzir a cada 3
        sentences.append(sent)
    
    to_translate = [s for s in sentences if s.should_translate]
    print(f"\nTotal de sentenças: {len(sentences)}")
    print(f"Sentenças para traduzir: {len(to_translate)}")
    
    # Criar engine e batches
    engine = TranslationEngine(source_lang="en", target_lang="pt")
    batches = engine._create_batches(sentences, to_translate)
    
    print(f"Batches criados: {len(batches)}")
    
    for i, batch in enumerate(batches):
        print(f"\n  Batch {i+1}:")
        print(f"    Sentenças a traduzir: {len(batch.sentences_to_translate)}")
        print(f"    Sentenças de contexto: {len(batch.context_sentences)}")
        print(f"    Tokens estimados: {batch.estimated_tokens}")
        
        # Mostrar IDs
        trans_ids = [s.index for s in batch.sentences_to_translate]
        context_ids = [s.index for s in batch.context_sentences]
        print(f"    IDs traduzir: {trans_ids}")
        print(f"    IDs contexto: {context_ids}")
    
    print("\n✅ Teste de criação de batches concluído!")


def test_prompt_building():
    """Testa construção do prompt"""
    print("\n" + "="*60)
    print("Teste de Construção do Prompt")
    print("="*60)
    
    # Criar sentenças de teste
    sentences = [
        Sentence(text="The sun was setting.", index=0, paragraph_index=0, chapter_index=0),
        Sentence(text="She walked along the path.", index=1, paragraph_index=0, chapter_index=0),
        Sentence(text="Birds were singing.", index=2, paragraph_index=0, chapter_index=0),
        Sentence(text="It was peaceful.", index=3, paragraph_index=0, chapter_index=0),
        Sentence(text="She smiled.", index=4, paragraph_index=0, chapter_index=0),
    ]
    
    # Marcar algumas para tradução
    sentences[1].should_translate = True
    sentences[3].should_translate = True
    
    to_translate = [s for s in sentences if s.should_translate]
    context = [s for s in sentences if not s.should_translate]
    
    # Criar engine e prompt
    engine = TranslationEngine(source_lang="en", target_lang="pt")
    prompt = engine._build_prompt(to_translate, context)
    
    print("\n📝 Prompt gerado:")
    print("-" * 50)
    print(prompt)
    print("-" * 50)
    
    print("\n✅ Teste de construção do prompt concluído!")


def test_with_epub(epub_path: str, user_level: str = "B1", max_sentences: int = 10):
    """
    Testa tradução com um arquivo EPUB real.
    
    Args:
        epub_path: Caminho para o arquivo EPUB
        user_level: Nível CEFR do usuário
        max_sentences: Número máximo de sentenças a traduzir (para teste)
    """
    print("\n" + "="*60)
    print(f"Teste de Tradução com EPUB")
    print("="*60)
    
    # Parse EPUB
    print(f"\n📖 Carregando: {epub_path}")
    structure = parse_epub(epub_path)
    
    print(f"  Título: {structure.title}")
    print(f"  Autor: {structure.author}")
    print(f"  Idioma: {structure.language}")
    print(f"  Capítulos: {structure.chapter_count}")
    print(f"  Sentenças: {structure.total_sentences}")
    
    # Analisar dificuldade
    print(f"\n📊 Analisando dificuldade (nível {user_level})...")
    level = CEFRLevel.from_string(user_level)
    stats = analyze_difficulty(structure, level, structure.language)
    
    print(f"  Sentenças para traduzir: {stats['sentences_to_translate']}")
    print(f"  Porcentagem: {stats['translation_percentage']:.1f}%")
    
    # Limitar número de sentenças para teste
    all_sentences = structure.get_all_sentences()
    to_translate = [s for s in all_sentences if s.should_translate][:max_sentences]
    
    # Resetar todas e marcar apenas as selecionadas
    for s in all_sentences:
        s.should_translate = False
    for s in to_translate:
        s.should_translate = True
    
    print(f"\n🔄 Traduzindo {len(to_translate)} sentenças (limitado para teste)...")
    
    # Callback de progresso
    def progress(value: float, message: str):
        bar_length = 30
        filled = int(bar_length * value)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r  [{bar}] {value*100:.0f}% - {message}", end="", flush=True)
    
    # Traduzir
    try:
        trans_stats = translate_epub_structure(
            structure,
            source_lang=structure.language,
            target_lang="pt",
            progress_callback=progress
        )
        print()  # Nova linha após barra de progresso
        
        print(f"\n📈 Estatísticas da tradução:")
        print(f"  Total de sentenças: {trans_stats.total_sentences}")
        print(f"  Sentenças traduzidas: {trans_stats.translated_sentences}")
        print(f"  Sentenças com falha: {trans_stats.failed_sentences}")
        print(f"  Batches processados: {trans_stats.total_batches}")
        print(f"  Tempo total: {trans_stats.total_time:.1f}s")
        
        if trans_stats.errors:
            print(f"\n⚠️ Erros:")
            for error in trans_stats.errors:
                print(f"  - {error}")
        
        # Mostrar exemplos de traduções
        print(f"\n📝 Exemplos de traduções:")
        print("-" * 70)
        
        translated = [s for s in all_sentences if s.translated_text and s.translated_text != s.text][:5]
        
        for sent in translated:
            print(f"\n  [Original] {sent.text}")
            print(f"  [Tradução] {sent.translated_text}")
        
    except Exception as e:
        print(f"\n❌ Erro durante tradução: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n" + "="*60)
    print("✅ Teste de tradução com EPUB concluído!")
    print("="*60)


def test_response_parsing():
    """Testa parsing de respostas do Gemini"""
    print("\n" + "="*60)
    print("Teste de Parsing de Respostas")
    print("="*60)
    
    # Criar sentenças de teste
    sentences = [
        Sentence(text="Hello world.", index=1, paragraph_index=0, chapter_index=0),
        Sentence(text="How are you?", index=3, paragraph_index=0, chapter_index=0),
        Sentence(text="Goodbye.", index=5, paragraph_index=0, chapter_index=0),
    ]
    
    # Simular resposta do Gemini
    mock_response = """
1: Olá mundo.
3: Como você está?
5: Adeus.
"""
    
    engine = TranslationEngine(source_lang="en", target_lang="pt")
    engine._parse_translations(mock_response, sentences)
    
    print("\n📝 Resultados do parsing:")
    for sent in sentences:
        status = "✓" if sent.translated_text else "✗"
        print(f"  [{status}] {sent.index}: '{sent.text}' → '{sent.translated_text}'")
    
    # Testar com formato diferente
    sentences2 = [
        Sentence(text="Test one.", index=10, paragraph_index=0, chapter_index=0),
        Sentence(text="Test two.", index=20, paragraph_index=0, chapter_index=0),
    ]
    
    mock_response2 = """
10:Teste um.
20: Teste dois.
"""
    
    engine._parse_translations(mock_response2, sentences2)
    
    print("\n📝 Resultados com formato variado:")
    for sent in sentences2:
        status = "✓" if sent.translated_text else "✗"
        print(f"  [{status}] {sent.index}: '{sent.text}' → '{sent.translated_text}'")
    
    print("\n✅ Teste de parsing de respostas concluído!")


if __name__ == "__main__":
    # Testes que não precisam de API
    test_batch_creation()
    test_prompt_building()
    test_response_parsing()
    
    # Testes que usam a API (podem falhar sem chave válida)
    print("\n" + "="*60)
    print("Testes com API do Gemini")
    print("="*60)
    
    try:
        test_single_translation()
    except Exception as e:
        print(f"\n⚠️ Teste de tradução simples falhou: {e}")
        print("   (Verifique se a API key está configurada corretamente)")
    
    # Se um arquivo EPUB foi passado, testar com ele
    if len(sys.argv) > 1:
        epub_path = sys.argv[1]
        if Path(epub_path).exists():
            # Nível opcional como segundo argumento
            level = sys.argv[2] if len(sys.argv) > 2 else "B1"
            # Limite opcional como terceiro argumento
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            
            try:
                test_with_epub(epub_path, level, limit)
            except Exception as e:
                print(f"\n❌ Teste com EPUB falhou: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"\n❌ Arquivo não encontrado: {epub_path}")
    else:
        print("\n" + "-"*60)
        print("NOTA: Para testar com um arquivo EPUB real, execute:")
        print("  python tests/test_translation.py caminho/livro.epub [nivel] [limite]")
        print("  Exemplo: python tests/test_translation.py livro.epub B1 10")
        print("-"*60)
