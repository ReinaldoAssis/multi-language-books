"""
Multi-Language Books - Streamlit Interface

Aplicativo para transformar livros EPUB em versões multi-idiomas
para estudo de línguas estrangeiras.
"""

import streamlit as st
import tempfile
import os
import time
from pathlib import Path
from typing import Optional

# Importar módulos do projeto
from src.epub_parser import parse_epub, EpubParser
from src.difficulty_analyzer import DifficultyAnalyzer
from src.translation_engine import TranslationEngine
from src.epub_generator import generate_epub, save_epub
from src.models import CEFRLevel, EpubStructure, ProcessingStats
from config.settings import SUPPORTED_LANGUAGES, CEFR_THRESHOLDS

# =============================================================================
# Configuração da Página
# =============================================================================

st.set_page_config(
    page_title="Multi-Language Books",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CSS Customizado
# =============================================================================

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1a5276;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #566573;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stats-box {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .stProgress > div > div > div > div {
        background-color: #1a5276;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Estado da Sessão
# =============================================================================

if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'translation_complete' not in st.session_state:
    st.session_state.translation_complete = False
if 'epub_bytes' not in st.session_state:
    st.session_state.epub_bytes = None
if 'stats' not in st.session_state:
    st.session_state.stats = None
if 'output_filename' not in st.session_state:
    st.session_state.output_filename = None
if 'structure' not in st.session_state:
    st.session_state.structure = None
if 'tmp_path' not in st.session_state:
    st.session_state.tmp_path = None
if 'gemini_api_key' not in st.session_state:
    # Tentar carregar do arquivo de configuração local
    api_key_file = Path(".gemini_api_key")
    if api_key_file.exists():
        st.session_state.gemini_api_key = api_key_file.read_text().strip()
    else:
        st.session_state.gemini_api_key = ""

# =============================================================================
# Funções Auxiliares
# =============================================================================

def get_cefr_description(level: str) -> str:
    """Retorna descrição do nível CEFR"""
    descriptions = {
        "A1": "Iniciante - Vocabulário básico (top 1000 palavras)",
        "A2": "Elementar - Vocabulário comum (top 3000 palavras)",
        "B1": "Intermediário - Vocabulário frequente (top 10000 palavras)",
        "B2": "Intermediário Superior - Vocabulário expandido",
        "C1": "Avançado - Vocabulário sofisticado",
        "C2+": "Proficiente - Todo vocabulário"
    }
    return descriptions.get(level, "")


def save_api_key(api_key: str) -> bool:
    """Salva a chave API em arquivo local"""
    try:
        api_key_file = Path(".gemini_api_key")
        api_key_file.write_text(api_key.strip())
        return True
    except Exception:
        return False


def analyze_epub(
    uploaded_file,
    source_lang: str,
    user_level: str,
    translation_mode: str,
    progress_callback
) -> tuple[Optional[EpubStructure], Optional[dict], Optional[str]]:
    """
    Analisa o EPUB sem traduzir - apenas parsing e análise de dificuldade
    
    Returns:
        Tuple[estrutura do EPUB, estatísticas, caminho temporário]
    """
    stats = {
        "total_chapters": 0,
        "total_sentences": 0,
        "sentences_analyzed": 0,
        "sentences_to_translate": 0,
        "sentences_kept_original": 0,
        "cefr_distribution": {}
    }
    
    try:
        # Salvar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        # =====================================================================
        # Fase 1: Parsing
        # =====================================================================
        progress_callback(0.10, "📖 Lendo EPUB...")
        
        structure = parse_epub(tmp_path)
        stats["total_chapters"] = structure.chapter_count
        stats["total_sentences"] = structure.total_sentences
        
        progress_callback(0.30, f"✓ {structure.chapter_count} capítulos encontrados")
        
        # =====================================================================
        # Fase 2: Análise de Dificuldade
        # =====================================================================
        progress_callback(0.35, "🔍 Analisando dificuldade das sentenças...")
        
        analyzer = DifficultyAnalyzer(language=source_lang)
        user_cefr = CEFRLevel[user_level.replace("+", "_PLUS")]
        
        sentences_to_translate = []
        all_sentences = structure.get_all_sentences()
        
        # Contadores por nível
        level_counts = {level: 0 for level in CEFRLevel}
        
        for i, sentence in enumerate(all_sentences):
            # Analisar sentença
            analyzed = analyzer.analyze_sentence(sentence)
            sentence.difficulty = analyzed.avg_zipf
            sentence.cefr_level = analyzed.cefr_level
            
            # Contar por nível
            level_counts[analyzed.cefr_level] = level_counts.get(analyzed.cefr_level, 0) + 1
            
            # Verificar se deve traduzir baseado no modo selecionado
            sentence_level = analyzed.cefr_level
            
            if translation_mode == 'above':
                should_translate = sentence_level > user_cefr
            else:
                should_translate = sentence_level <= user_cefr
            
            if should_translate:
                sentence.should_translate = True
                sentences_to_translate.append(sentence)
            else:
                sentence.should_translate = False
            
            # Atualizar progresso
            if i % 100 == 0:
                pct = 0.35 + (0.60 * i / len(all_sentences))
                progress_callback(pct, f"🔍 Analisando: {i}/{len(all_sentences)} sentenças")
        
        stats["sentences_analyzed"] = len(all_sentences)
        stats["sentences_to_translate"] = len(sentences_to_translate)
        stats["sentences_kept_original"] = len(all_sentences) - len(sentences_to_translate)
        stats["cefr_distribution"] = {level.name: count for level, count in level_counts.items()}
        
        progress_callback(1.0, "✅ Análise concluída!")
        
        return structure, stats, tmp_path
        
    except Exception as e:
        progress_callback(0, f"❌ Erro: {str(e)}")
        raise e


def translate_and_generate(
    structure: EpubStructure,
    source_lang: str,
    target_lang: str,
    api_key: str,
    highlight_translated: bool,
    style_type: str,
    progress_callback
) -> tuple[Optional[bytes], Optional[dict]]:
    """
    Traduz as sentenças marcadas e gera o EPUB final
    
    Returns:
        Tuple[bytes do EPUB, estatísticas de tradução]
    """
    stats = {}
    start_time = time.time()
    
    try:
        sentences_to_translate = [s for s in structure.get_all_sentences() if s.should_translate]
        
        # =====================================================================
        # Fase 1: Tradução
        # =====================================================================
        if sentences_to_translate:
            progress_callback(0.05, "🌐 Iniciando tradução com Gemini...")
            
            engine = TranslationEngine(
                api_key=api_key,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            def translation_progress(progress_pct, message):
                pct = 0.05 + (0.75 * progress_pct)
                progress_callback(pct, f"🌐 {message}")
            
            translation_stats = engine.translate_structure(
                structure=structure,
                progress_callback=translation_progress
            )
            
            stats["sentences_translated"] = translation_stats.translated_sentences
            stats["translation_errors"] = translation_stats.failed_sentences
            
            progress_callback(0.80, f"✓ {translation_stats.translated_sentences} sentenças traduzidas")
        else:
            stats["sentences_translated"] = 0
            progress_callback(0.80, "ℹ️ Nenhuma sentença para traduzir")
        
        # =====================================================================
        # Fase 2: Geração do EPUB
        # =====================================================================
        progress_callback(0.85, "📝 Gerando novo EPUB...")
        
        epub_bytes = generate_epub(
            structure=structure,
            highlight_translated=highlight_translated,
            style_type=style_type
        )
        
        stats["processing_time"] = time.time() - start_time
        
        progress_callback(1.0, "✅ EPUB gerado com sucesso!")
        
        return epub_bytes, stats
        
    except Exception as e:
        progress_callback(0, f"❌ Erro: {str(e)}")
        raise e


# =============================================================================
# Interface Principal
# =============================================================================

def main():
    # Header
    st.markdown('<p class="main-header">📚 Multi-Language Books</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Transforme livros EPUB em ferramentas de estudo de idiomas</p>',
        unsafe_allow_html=True
    )
    
    # Sidebar - Configurações
    with st.sidebar:
        st.header("⚙️ Configurações")
        
        # =================================================================
        # API Key Configuration
        # =================================================================
        st.subheader("🔑 Chave API Gemini")
        
        api_key_input = st.text_input(
            "API Key",
            value=st.session_state.gemini_api_key,
            type="password",
            help="Sua chave da API do Google Gemini"
        )
        
        col_save, col_status = st.columns([1, 1])
        with col_save:
            if st.button("💾 Salvar", use_container_width=True):
                if api_key_input:
                    st.session_state.gemini_api_key = api_key_input
                    if save_api_key(api_key_input):
                        st.success("✓ Salva!")
                    else:
                        st.warning("Salva na sessão")
                else:
                    st.error("Vazia!")
        
        with col_status:
            if st.session_state.gemini_api_key:
                st.success("✓ Configurada")
            else:
                st.error("✗ Não configurada")
        
        st.divider()
        
        # =================================================================
        # Idiomas
        # =================================================================
        st.subheader("🌍 Idiomas")
        
        source_lang = st.selectbox(
            "Idioma do livro (origem)",
            options=list(SUPPORTED_LANGUAGES.keys()),
            format_func=lambda x: f"{SUPPORTED_LANGUAGES[x]} ({x})",
            index=0,
            help="O idioma original do livro EPUB"
        )
        
        target_lang = st.selectbox(
            "Seu idioma nativo (destino)",
            options=list(SUPPORTED_LANGUAGES.keys()),
            format_func=lambda x: f"{SUPPORTED_LANGUAGES[x]} ({x})",
            index=1,
            help="O idioma para o qual as sentenças selecionadas serão traduzidas"
        )
        
        if source_lang == target_lang:
            st.warning("⚠️ Idioma de origem e destino são iguais!")
        
        # =================================================================
        # Nível CEFR
        # =================================================================
        st.subheader("📊 Nível de Proficiência")
        
        user_level = st.select_slider(
            "Seu nível no idioma do livro",
            options=["A1", "A2", "B1", "B2", "C1", "C2+"],
            value="B1",
            help="Define o ponto de corte para decidir o que traduzir"
        )
        
        st.caption(get_cefr_description(user_level))
        
        # =================================================================
        # Modo de tradução
        # =================================================================
        st.subheader("🔄 Modo de Tradução")
        
        translation_mode = st.radio(
            "O que traduzir?",
            options=["above", "below"],
            format_func=lambda x: {
                "above": "📈 Traduzir ACIMA do nível (difícil → seu idioma)",
                "below": "📉 Traduzir ABAIXO do nível (fácil → seu idioma)"
            }.get(x, x),
            index=0,
            help="Escolha quais sentenças serão traduzidas para seu idioma nativo"
        )
        
        if translation_mode == "above":
            st.info("💡 Sentenças difíceis serão traduzidas. Você lerá no original o que já domina.")
        else:
            st.info("💡 Sentenças fáceis serão traduzidas. Você será desafiado pelo vocabulário avançado.")
        
        # =================================================================
        # Estilização
        # =================================================================
        st.subheader("🎨 Estilização")
        
        highlight_translated = st.checkbox(
            "Destacar texto traduzido",
            value=True,
            help="Aplica estilo visual diferente ao texto traduzido"
        )
        
        style_type = st.radio(
            "Tipo de destaque",
            options=["default", "subtle", "none"],
            format_func=lambda x: {
                "default": "Padrão (itálico + cor)",
                "subtle": "Sutil (apenas cor)",
                "none": "Sem destaque"
            }.get(x, x),
            disabled=not highlight_translated,
            help="Escolha como o texto traduzido será destacado"
        )
        
        # =================================================================
        # Informações
        # =================================================================
        st.divider()
        st.subheader("ℹ️ Como funciona")
        st.markdown("""
        1. **Upload** do arquivo EPUB
        2. **Analisar** → veja a distribuição de dificuldade
        3. **Traduzir** → confirme e inicie a tradução
        4. **Download** do novo EPUB multi-idioma
        """)
    
    # =========================================================================
    # Área Principal
    # =========================================================================
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📤 Upload do EPUB")
        
        uploaded_file = st.file_uploader(
            "Escolha um arquivo EPUB",
            type=["epub"],
            help="Faça upload do livro que deseja processar"
        )
        
        if uploaded_file:
            st.success(f"✅ Arquivo carregado: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")
            
            # =================================================================
            # Botão de Análise
            # =================================================================
            if st.button("🔍 Analisar EPUB", type="secondary", use_container_width=True):
                # Reset estado
                st.session_state.analysis_complete = False
                st.session_state.translation_complete = False
                st.session_state.epub_bytes = None
                st.session_state.structure = None
                st.session_state.stats = None
                
                progress_container = st.container()
                
                with progress_container:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    def update_progress(pct: float, message: str):
                        progress_bar.progress(pct)
                        status_text.markdown(f"**{message}**")
                    
                    try:
                        structure, stats, tmp_path = analyze_epub(
                            uploaded_file=uploaded_file,
                            source_lang=source_lang,
                            user_level=user_level,
                            translation_mode=translation_mode,
                            progress_callback=update_progress
                        )
                        
                        # Salvar no estado
                        st.session_state.analysis_complete = True
                        st.session_state.structure = structure
                        st.session_state.stats = stats
                        st.session_state.tmp_path = tmp_path
                        
                        # Nome do arquivo de saída
                        original_name = Path(uploaded_file.name).stem
                        st.session_state.output_filename = f"{original_name}_multilanguage.epub"
                        
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Erro durante a análise: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
            
            # =================================================================
            # Área de Confirmação e Tradução (após análise)
            # =================================================================
            if st.session_state.analysis_complete and not st.session_state.translation_complete:
                st.divider()
                st.subheader("📋 Resumo da Análise")
                
                stats = st.session_state.stats
                
                # Mostrar resumo
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    st.metric("📚 Capítulos", stats["total_chapters"])
                with col_r2:
                    st.metric("📝 Sentenças", stats["total_sentences"])
                with col_r3:
                    pct_translate = (stats["sentences_to_translate"] / stats["total_sentences"] * 100) if stats["total_sentences"] > 0 else 0
                    st.metric("🌐 A traduzir", f"{stats['sentences_to_translate']} ({pct_translate:.1f}%)")
                
                # Aviso sobre API key
                if not st.session_state.gemini_api_key:
                    st.error("⚠️ Configure sua chave API do Gemini na barra lateral antes de traduzir!")
                    translate_disabled = True
                else:
                    translate_disabled = False
                
                # Botão de tradução
                st.markdown("---")
                if st.button(
                    "🚀 Confirmar e Traduzir", 
                    type="primary", 
                    use_container_width=True,
                    disabled=translate_disabled
                ):
                    progress_container = st.container()
                    
                    with progress_container:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(pct: float, message: str):
                            progress_bar.progress(pct)
                            status_text.markdown(f"**{message}**")
                        
                        try:
                            epub_bytes, translation_stats = translate_and_generate(
                                structure=st.session_state.structure,
                                source_lang=source_lang,
                                target_lang=target_lang,
                                api_key=st.session_state.gemini_api_key,
                                highlight_translated=highlight_translated,
                                style_type=style_type if highlight_translated else "none",
                                progress_callback=update_progress
                            )
                            
                            # Atualizar estado
                            st.session_state.translation_complete = True
                            st.session_state.epub_bytes = epub_bytes
                            st.session_state.stats.update(translation_stats)
                            
                            # Limpar arquivo temporário
                            if st.session_state.tmp_path and os.path.exists(st.session_state.tmp_path):
                                os.unlink(st.session_state.tmp_path)
                                st.session_state.tmp_path = None
                            
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Erro durante a tradução: {str(e)}")
                            import traceback
                            st.code(traceback.format_exc())
    
    with col2:
        st.header("📊 Estatísticas")
        
        if st.session_state.stats:
            stats = st.session_state.stats
            
            # Status
            if st.session_state.translation_complete:
                st.success("✅ Tradução concluída!")
            elif st.session_state.analysis_complete:
                st.info("🔍 Análise concluída - aguardando confirmação")
            
            # Métricas principais
            st.metric("📚 Capítulos", stats["total_chapters"])
            st.metric("📝 Sentenças totais", stats["total_sentences"])
            
            col_a, col_b = st.columns(2)
            with col_a:
                label = "🌐 A traduzir" if not st.session_state.translation_complete else "🌐 Traduzidas"
                value = stats.get("sentences_translated", stats.get("sentences_to_translate", 0))
                st.metric(label, value)
            with col_b:
                st.metric("📖 Originais", stats.get("sentences_kept_original", 0))
            
            # Tempo de processamento
            if "processing_time" in stats:
                st.metric("⏱️ Tempo", f"{stats['processing_time']:.1f}s")
            
            # Distribuição CEFR
            if "cefr_distribution" in stats and stats["cefr_distribution"]:
                st.subheader("📈 Distribuição por Nível")
                
                dist = stats["cefr_distribution"]
                total = sum(dist.values())
                
                for level in ["A1", "A2", "B1", "B2", "C1", "C2_PLUS"]:
                    count = dist.get(level, 0)
                    pct = (count / total * 100) if total > 0 else 0
                    display_level = level.replace("_PLUS", "+")
                    st.progress(pct / 100, text=f"{display_level}: {count} ({pct:.1f}%)")
        else:
            st.info("As estatísticas aparecerão após a análise")
    
    # =========================================================================
    # Área de Download
    # =========================================================================
    if st.session_state.translation_complete and st.session_state.epub_bytes:
        st.divider()
        
        st.markdown('<div class="success-box">', unsafe_allow_html=True)
        st.header("✅ EPUB Pronto para Download!")
        
        col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
        
        with col_dl2:
            st.download_button(
                label="📥 Baixar EPUB Multi-Idioma",
                data=st.session_state.epub_bytes,
                file_name=st.session_state.output_filename,
                mime="application/epub+zip",
                type="primary",
                use_container_width=True
            )
            
            st.caption(f"Arquivo: {st.session_state.output_filename}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.divider()
    st.markdown(
        """
        <div style="text-align: center; color: #888; font-size: 0.9rem;">
            Multi-Language Books • Powered by Gemini AI & wordfreq
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
