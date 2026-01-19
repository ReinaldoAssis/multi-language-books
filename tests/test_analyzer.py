"""
Testes para o analisador de dificuldade
"""
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.difficulty_analyzer import (
    DifficultyAnalyzer, 
    DifficultyScore, 
    analyze_difficulty,
    get_sentence_difficulty
)
from src.models import Sentence, CEFRLevel
from src.epub_parser import parse_epub


def test_single_sentences():
    """Testa análise de sentenças individuais"""
    print("\n" + "="*60)
    print("Teste de Análise de Sentenças Individuais")
    print("="*60)
    
    # Sentenças de diferentes níveis de dificuldade
    test_sentences = [
        # A1 - Muito fácil
        ("I am a boy.", "A1 - Muito fácil"),
        ("The cat is on the table.", "A1 - Muito fácil"),
        ("She has a red car.", "A1 - Muito fácil"),
        
        # A2 - Fácil
        ("I like to eat pizza for dinner.", "A2 - Fácil"),
        ("They went to the store yesterday.", "A2 - Fácil"),
        
        # B1 - Intermediário
        ("The weather forecast predicted heavy rainfall.", "B1 - Intermediário"),
        ("She decided to pursue a career in medicine.", "B1 - Intermediário"),
        
        # B2 - Intermediário superior
        ("The economic implications of this policy remain uncertain.", "B2 - Int. Superior"),
        ("His philosophical arguments were thoroughly compelling.", "B2 - Int. Superior"),
        
        # C1 - Avançado
        ("The epistemological foundations of this theory are questionable.", "C1 - Avançado"),
        ("Notwithstanding the aforementioned circumstances, we shall proceed.", "C1 - Avançado"),
        
        # C2 - Proficiente
        ("The juxtaposition of ontological paradigms necessitates reconsideration.", "C2 - Proficiente"),
        ("Hermeneutical approaches to phenomenological exegesis remain contentious.", "C2 - Proficiente"),
    ]
    
    analyzer = DifficultyAnalyzer(language="en")
    
    print(f"\n{'Sentença':<60} {'Esperado':<15} {'CEFR':<6} {'Zipf':<6}")
    print("-" * 90)
    
    for text, expected in test_sentences:
        score = get_sentence_difficulty(text, "en")
        # Truncar sentença para exibição
        display_text = text[:57] + "..." if len(text) > 60 else text
        print(f"{display_text:<60} {expected:<15} {score.cefr_level.name:<6} {score.avg_zipf:.2f}")
    
    print("\n✅ Teste de sentenças individuais concluído!")


def test_cefr_classification():
    """Testa a classificação CEFR"""
    print("\n" + "="*60)
    print("Teste de Classificação CEFR")
    print("="*60)
    
    analyzer = DifficultyAnalyzer(language="en")
    
    # Testar diferentes scores Zipf
    test_cases = [
        (6.5, 6.0, 0.0, CEFRLevel.A1),  # Alta frequência
        (5.7, 5.0, 0.0, CEFRLevel.A2),  
        (5.2, 4.5, 0.0, CEFRLevel.B1),
        (4.7, 4.0, 0.0, CEFRLevel.B2),
        (4.2, 3.5, 0.0, CEFRLevel.C1),
        (3.5, 2.5, 0.0, CEFRLevel.C2_PLUS),
        (5.0, 4.5, 0.3, CEFRLevel.B2),  # Com palavras desconhecidas
    ]
    
    print(f"\n{'Avg Zipf':<10} {'Min Zipf':<10} {'Unknown':<10} {'Esperado':<10} {'Resultado':<10}")
    print("-" * 55)
    
    for avg_zipf, min_zipf, unknown_ratio, expected in test_cases:
        result = analyzer._classify_cefr(avg_zipf, min_zipf, unknown_ratio)
        status = "✓" if result == expected else "✗"
        print(f"{avg_zipf:<10.1f} {min_zipf:<10.1f} {unknown_ratio:<10.1f} {expected.name:<10} {result.name:<10} {status}")
    
    print("\n✅ Teste de classificação CEFR concluído!")


def test_should_translate():
    """Testa a lógica de decisão de tradução"""
    print("\n" + "="*60)
    print("Teste de Decisão de Tradução")
    print("="*60)
    
    analyzer = DifficultyAnalyzer(language="en")
    
    # Criar sentenças de diferentes níveis
    sentences = [
        ("The cat is big.", CEFRLevel.A1),
        ("She went to the store.", CEFRLevel.A2),
        ("The meeting was postponed.", CEFRLevel.B1),
        ("The implications are significant.", CEFRLevel.B2),
        ("The epistemological debate continues.", CEFRLevel.C1),
    ]
    
    user_level = CEFRLevel.B1
    
    print(f"\nNível do usuário: {user_level.name}")
    print(f"\nLógica: Traduzir sentenças FÁCEIS (≤ {user_level.name}), manter DIFÍCEIS no original")
    print(f"\n{'Sentença':<45} {'Nível':<6} {'Traduzir?':<10} {'Motivo':<20}")
    print("-" * 85)
    
    for text, level in sentences:
        sent = Sentence(text=text, index=0, paragraph_index=0, chapter_index=0)
        sent.cefr_level = level
        
        should_trans = analyzer.should_translate(sent, user_level)
        reason = "Fácil → traduzir" if should_trans else "Difícil → manter"
        status = "Sim ✓" if should_trans else "Não ✗"
        
        print(f"{text:<45} {level.name:<6} {status:<10} {reason:<20}")
    
    print("\n✅ Teste de decisão de tradução concluído!")


def test_with_epub(epub_path: str):
    """Testa a análise com um arquivo EPUB real"""
    print("\n" + "="*60)
    print(f"Teste com EPUB: {epub_path}")
    print("="*60)
    
    # Parser o EPUB
    structure = parse_epub(epub_path)
    
    print(f"\n📖 Livro: {structure.title}")
    print(f"✍️  Autor: {structure.author}")
    print(f"🌐 Idioma: {structure.language}")
    print(f"📝 Total de sentenças: {structure.total_sentences}")
    
    # Testar com diferentes níveis de usuário
    test_levels = [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2_PLUS]
    
    print(f"\n{'Nível':<6} {'Total':<10} {'Traduzir':<12} {'Manter':<12} {'% Tradução':<12}")
    print("-" * 55)
    
    for level in test_levels:
        # Analisar com este nível
        stats = analyze_difficulty(structure, level, structure.language)
        
        to_translate = stats['sentences_to_translate']
        to_keep = stats['total_sentences'] - to_translate
        percentage = stats['translation_percentage']
        
        print(f"{level.name:<6} {stats['total_sentences']:<10} {to_translate:<12} {to_keep:<12} {percentage:.1f}%")
    
    # Mostrar distribuição CEFR
    stats = analyze_difficulty(structure, CEFRLevel.B1, structure.language)
    
    print(f"\n📊 Distribuição CEFR das sentenças:")
    print("-" * 40)
    
    total = stats['total_sentences']
    for level in CEFRLevel:
        count = stats['cefr_distribution'][level.name]
        percentage = (count / total * 100) if total > 0 else 0
        bar = "█" * int(percentage / 2)
        print(f"  {level.name:<6} {count:>5} ({percentage:>5.1f}%) {bar}")
    
    # Mostrar exemplos de sentenças por nível
    print(f"\n📝 Exemplos de sentenças por nível:")
    print("-" * 60)
    
    all_sentences = structure.get_all_sentences()
    
    for level in CEFRLevel:
        sentences_at_level = [s for s in all_sentences if s.cefr_level == level][:2]
        if sentences_at_level:
            print(f"\n{level.name}:")
            for sent in sentences_at_level:
                preview = sent.text[:70] + "..." if len(sent.text) > 70 else sent.text
                print(f"  • {preview}")
    
    print(f"\n" + "="*60)
    print("✅ Análise completa!")
    print("="*60)


def test_multilang():
    """Testa suporte a múltiplos idiomas"""
    print("\n" + "="*60)
    print("Teste de Múltiplos Idiomas")
    print("="*60)
    
    test_cases = [
        ("en", "The cat is on the table."),
        ("en", "Epistemological considerations notwithstanding."),
        ("pt", "O gato está na mesa."),
        ("pt", "Considerações epistemológicas não obstante."),
        ("es", "El gato está en la mesa."),
        ("es", "Las implicaciones filosóficas son profundas."),
        ("fr", "Le chat est sur la table."),
        ("fr", "Les considérations épistémologiques persistent."),
        ("de", "Die Katze ist auf dem Tisch."),
        ("de", "Die erkenntnistheoretischen Überlegungen bleiben."),
    ]
    
    print(f"\n{'Idioma':<8} {'Sentença':<50} {'CEFR':<6} {'Zipf':<6}")
    print("-" * 75)
    
    for lang, text in test_cases:
        score = get_sentence_difficulty(text, lang)
        display_text = text[:47] + "..." if len(text) > 50 else text
        print(f"{lang:<8} {display_text:<50} {score.cefr_level.name:<6} {score.avg_zipf:.2f}")
    
    print("\n✅ Teste de múltiplos idiomas concluído!")


if __name__ == "__main__":
    # Executar testes básicos
    test_single_sentences()
    test_cefr_classification()
    test_should_translate()
    test_multilang()
    
    # Se um arquivo EPUB foi passado, testar com ele
    if len(sys.argv) > 1:
        epub_path = sys.argv[1]
        if Path(epub_path).exists():
            test_with_epub(epub_path)
        else:
            print(f"\n❌ Arquivo não encontrado: {epub_path}")
    else:
        print("\n" + "="*60)
        print("NOTA: Para testar com um arquivo EPUB real, execute:")
        print("  python tests/test_analyzer.py caminho/para/livro.epub")
        print("="*60)
