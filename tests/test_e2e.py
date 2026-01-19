"""
Teste End-to-End do Multi-Language Books

Testa todo o fluxo: parsing → análise → tradução → geração de EPUB
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.epub_parser import parse_epub
from src.difficulty_analyzer import analyze_difficulty
from src.translation_engine import translate_epub_structure
from src.epub_generator import generate_epub, save_epub
from src.models import CEFRLevel, EpubStructure


def test_full_pipeline(epub_path: str, 
                       user_level: str = "B1",
                       max_chapters: int = None,
                       max_sentences: int = None,
                       target_lang: str = "pt",
                       highlight: bool = True,
                       output_path: str = None):
    """
    Testa o pipeline completo de processamento.
    
    Args:
        epub_path: Caminho para o arquivo EPUB
        user_level: Nível CEFR do usuário (A1, A2, B1, B2, C1, C2+)
        max_chapters: Número máximo de capítulos a processar (None = todos)
        max_sentences: Número máximo de sentenças a traduzir (None = todas)
        target_lang: Idioma de destino da tradução
        highlight: Se True, destaca texto traduzido
        output_path: Caminho para salvar o EPUB (None = gera nome automático)
    """
    print("\n" + "="*70)
    print("🚀 TESTE END-TO-END: Multi-Language Books")
    print("="*70)
    
    start_time = datetime.now()
    
    # =========================================================================
    # ETAPA 1: Parsing do EPUB
    # =========================================================================
    print("\n📖 ETAPA 1: Parsing do EPUB")
    print("-" * 50)
    
    print(f"  Carregando: {epub_path}")
    structure = parse_epub(epub_path)
    
    print(f"  ✓ Título: {structure.title}")
    print(f"  ✓ Autor: {structure.author}")
    print(f"  ✓ Idioma: {structure.language}")
    print(f"  ✓ Capítulos: {structure.chapter_count}")
    print(f"  ✓ Sentenças: {structure.total_sentences}")
    
    # Limitar capítulos se especificado
    if max_chapters and max_chapters < structure.chapter_count:
        print(f"\n  ⚠️ Limitando a {max_chapters} capítulos para teste")
        structure.chapters = structure.chapters[:max_chapters]
        
        # Recalcular sentenças
        total_after_limit = structure.total_sentences
        print(f"  ✓ Sentenças após limite: {total_after_limit}")
    
    # =========================================================================
    # ETAPA 2: Análise de Dificuldade
    # =========================================================================
    print(f"\n📊 ETAPA 2: Análise de Dificuldade (Nível: {user_level})")
    print("-" * 50)
    
    level = CEFRLevel.from_string(user_level)
    
    def analysis_progress(value):
        bar_length = 30
        filled = int(bar_length * value)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r  Analisando: [{bar}] {value*100:.0f}%", end="", flush=True)
    
    stats = analyze_difficulty(structure, level, structure.language, analysis_progress)
    print()  # Nova linha
    
    print(f"\n  ✓ Total de sentenças: {stats['total_sentences']}")
    print(f"  ✓ Sentenças para traduzir: {stats['sentences_to_translate']}")
    print(f"  ✓ Porcentagem: {stats['translation_percentage']:.1f}%")
    
    # Distribuição CEFR
    print(f"\n  Distribuição por nível:")
    for level_name, count in stats['cefr_distribution'].items():
        pct = (count / stats['total_sentences'] * 100) if stats['total_sentences'] > 0 else 0
        bar = "█" * int(pct / 3)
        print(f"    {level_name:<8} {count:>5} ({pct:>5.1f}%) {bar}")
    
    # Limitar sentenças se especificado
    if max_sentences:
        all_sentences = structure.get_all_sentences()
        to_translate = [s for s in all_sentences if s.should_translate][:max_sentences]
        
        # Resetar todas e marcar apenas as selecionadas
        for s in all_sentences:
            s.should_translate = False
        for s in to_translate:
            s.should_translate = True
        
        print(f"\n  ⚠️ Limitando a {len(to_translate)} sentenças para teste")
    
    # =========================================================================
    # ETAPA 3: Tradução via Gemini API
    # =========================================================================
    sentences_to_translate = len([s for s in structure.get_all_sentences() if s.should_translate])
    
    print(f"\n🔄 ETAPA 3: Tradução ({structure.language} → {target_lang})")
    print("-" * 50)
    print(f"  Sentenças a traduzir: {sentences_to_translate}")
    
    def translation_progress(value: float, message: str):
        bar_length = 30
        filled = int(bar_length * value)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r  [{bar}] {value*100:.0f}% - {message[:40]:<40}", end="", flush=True)
    
    try:
        trans_stats = translate_epub_structure(
            structure,
            source_lang=structure.language,
            target_lang=target_lang,
            progress_callback=translation_progress
        )
        print()  # Nova linha
        
        print(f"\n  ✓ Sentenças traduzidas: {trans_stats.translated_sentences}")
        print(f"  ✓ Falhas: {trans_stats.failed_sentences}")
        print(f"  ✓ Batches: {trans_stats.total_batches}")
        print(f"  ✓ Tempo: {trans_stats.total_time:.1f}s")
        
        if trans_stats.errors:
            print(f"\n  ⚠️ Erros encontrados:")
            for error in trans_stats.errors[:3]:  # Mostrar apenas 3
                print(f"    - {error[:60]}...")
    
    except Exception as e:
        print(f"\n  ❌ Erro na tradução: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # =========================================================================
    # ETAPA 4: Geração do EPUB
    # =========================================================================
    print(f"\n📚 ETAPA 4: Geração do EPUB")
    print("-" * 50)
    
    # Gerar nome do arquivo de saída
    if not output_path:
        base_name = Path(epub_path).stem
        output_path = f"output/{base_name}_multilang_{user_level}_{target_lang}.epub"
    
    # Criar diretório de saída se não existir
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"  Gerando: {output_path}")
    print(f"  Destacar traduções: {'Sim' if highlight else 'Não'}")
    
    try:
        style_type = "default" if highlight else "none"
        save_epub(structure, output_path, highlight_translated=highlight, style_type=style_type)
        
        # Verificar tamanho do arquivo
        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)
        
        print(f"\n  ✓ EPUB gerado com sucesso!")
        print(f"  ✓ Tamanho: {file_size_mb:.2f} MB")
        print(f"  ✓ Salvo em: {output_path}")
        
    except Exception as e:
        print(f"\n  ❌ Erro na geração: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # =========================================================================
    # RESUMO FINAL
    # =========================================================================
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    print(f"\n" + "="*70)
    print("✅ PROCESSAMENTO CONCLUÍDO")
    print("="*70)
    
    print(f"\n📊 Resumo:")
    print(f"  • Livro: {structure.title}")
    print(f"  • Capítulos processados: {structure.chapter_count}")
    print(f"  • Sentenças analisadas: {stats['total_sentences']}")
    print(f"  • Sentenças traduzidas: {trans_stats.translated_sentences}")
    print(f"  • Nível do usuário: {user_level}")
    print(f"  • Idiomas: {structure.language} → {target_lang}")
    print(f"  • Tempo total: {total_time:.1f}s")
    print(f"  • Arquivo de saída: {output_path}")
    
    # Mostrar exemplos
    print(f"\n📝 Exemplos de traduções:")
    print("-" * 70)
    
    all_sentences = structure.get_all_sentences()
    translated = [s for s in all_sentences if s.translated_text and s.translated_text != s.text][:5]
    
    for sent in translated:
        orig = sent.text[:60] + "..." if len(sent.text) > 60 else sent.text
        trans = sent.translated_text[:60] + "..." if len(sent.translated_text) > 60 else sent.translated_text
        print(f"\n  [Original]  {orig}")
        print(f"  [Tradução]  {trans}")
    
    print(f"\n" + "="*70)
    print(f"📖 Abra o arquivo '{output_path}' em um leitor de EPUB para verificar!")
    print("="*70)


def print_usage():
    """Mostra instruções de uso"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                   Multi-Language Books - Teste E2E                    ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  Uso:                                                                ║
║    python tests/test_e2e.py <epub> [nivel] [max_caps] [max_sent]     ║
║                                                                      ║
║  Argumentos:                                                         ║
║    epub      - Caminho para o arquivo EPUB                           ║
║    nivel     - Nível CEFR: A1, A2, B1, B2, C1, C2+ (padrão: B1)     ║
║    max_caps  - Máximo de capítulos (padrão: todos)                  ║
║    max_sent  - Máximo de sentenças a traduzir (padrão: todas)       ║
║                                                                      ║
║  Exemplos:                                                           ║
║    python tests/test_e2e.py livro.epub                               ║
║    python tests/test_e2e.py livro.epub B2                            ║
║    python tests/test_e2e.py livro.epub B1 5                          ║
║    python tests/test_e2e.py livro.epub B1 3 50                       ║
║                                                                      ║
║  O arquivo de saída será salvo em:                                   ║
║    output/<nome>_multilang_<nivel>_pt.epub                           ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    epub_path = sys.argv[1]
    
    if not Path(epub_path).exists():
        print(f"\n❌ Arquivo não encontrado: {epub_path}")
        sys.exit(1)
    
    # Argumentos opcionais
    user_level = sys.argv[2] if len(sys.argv) > 2 else "B1"
    max_chapters = int(sys.argv[3]) if len(sys.argv) > 3 else None
    max_sentences = int(sys.argv[4]) if len(sys.argv) > 4 else None
    
    try:
        test_full_pipeline(
            epub_path=epub_path,
            user_level=user_level,
            max_chapters=max_chapters,
            max_sentences=max_sentences,
            target_lang="pt",
            highlight=True
        )
    except KeyboardInterrupt:
        print("\n\n⚠️ Processamento cancelado pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
