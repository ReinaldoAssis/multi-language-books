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
from src.translation_engine import TranslationEngine, BatchResult
from src.epub_generator import generate_epub, save_epub
from src.models import CEFRLevel, EpubStructure, ProcessingStats
from config.settings import SUPPORTED_LANGUAGES, CEFR_THRESHOLDS
from datetime import datetime

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
if 'lm_studio_url' not in st.session_state:
    st.session_state.lm_studio_url = "http://localhost:1234/v1"
if 'lm_studio_model' not in st.session_state:
    st.session_state.lm_studio_model = ""
if 'context_length' not in st.session_state:
    st.session_state.context_length = 128000
if 'llm_test_report' not in st.session_state:
    st.session_state.llm_test_report = None
if 'llm_test_filepath' not in st.session_state:
    st.session_state.llm_test_filepath = None

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


def save_epub_to_backend(epub_bytes: bytes, filename: str) -> tuple[bool, str]:
    """Salva o EPUB gerado no servidor/backend"""
    try:
        # Criar diretório de saída se não existir
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        # Adicionar timestamp para evitar conflitos
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(filename).stem
        final_filename = f"{base_name}_{timestamp}.epub"
        
        output_path = output_dir / final_filename
        output_path.write_bytes(epub_bytes)
        
        return True, str(output_path)
    except Exception as e:
        return False, str(e)


def run_llm_translation_test(
    structure: 'EpubStructure',
    source_lang: str,
    target_lang: str,
    lm_studio_url: str,
    lm_studio_model: str,
    max_sentences: int = 5
) -> tuple[str, str]:
    """
    Executa um teste de tradução com o LM Studio usando um batch de amostra.
    
    Args:
        structure: Estrutura do EPUB analisado
        source_lang: Idioma de origem
        target_lang: Idioma de destino
        lm_studio_url: URL do LM Studio
        lm_studio_model: Modelo a usar
        max_sentences: Número máximo de sentenças para o teste
        
    Returns:
        Tuple[relatório em texto, caminho do arquivo salvo]
    """
    import requests
    import re
    import json
    from datetime import datetime
    
    def is_good_test_sentence(text: str) -> bool:
        """Verifica se a sentença é boa para teste (não é nome próprio, tem conteúdo real)"""
        # Muito curta
        if len(text) < 20:
            return False
        
        # Contém pelo menos um verbo comum ou palavras funcionais
        # (indica que é uma frase real, não apenas nomes)
        words = text.lower().split()
        if len(words) < 4:
            return False
        
        # Se tem pontuação de frase (. , ! ?) provavelmente é texto real
        if any(p in text for p in ['.', ',', '!', '?', ';', ':']):
            return True
        
        return len(words) >= 5
    
    def normalize_text(text: str) -> str:
        """Normaliza texto para comparação"""
        return re.sub(r'\s+', ' ', text.lower().strip())
    
    def calculate_similarity(original: str, translated: str) -> float:
        """Calcula similaridade entre original e tradução (0-1, onde 1 = idênticos)"""
        orig_norm = normalize_text(original)
        trans_norm = normalize_text(translated)
        
        if orig_norm == trans_norm:
            return 1.0
        
        # Calcular Jaccard similarity baseado em palavras
        orig_words = set(orig_norm.split())
        trans_words = set(trans_norm.split())
        
        if not orig_words or not trans_words:
            return 0.0
        
        intersection = len(orig_words & trans_words)
        union = len(orig_words | trans_words)
        
        return intersection / union if union > 0 else 0.0
    
    # Iniciar relatório
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("RELATÓRIO DE TESTE - LM STUDIO TRANSLATION")
    report_lines.append("=" * 80)
    report_lines.append(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"URL LM Studio: {lm_studio_url}")
    report_lines.append(f"Modelo: {lm_studio_model or 'default'}")
    report_lines.append(f"Idioma origem: {source_lang} ({SUPPORTED_LANGUAGES.get(source_lang, source_lang)})")
    report_lines.append(f"Idioma destino: {target_lang} ({SUPPORTED_LANGUAGES.get(target_lang, target_lang)})")
    report_lines.append("")
    
    # Obter sentenças para tradução
    all_sentences_to_translate = [s for s in structure.get_all_sentences() if s.should_translate]
    
    if not all_sentences_to_translate:
        report_lines.append("❌ ERRO: Nenhuma sentença marcada para tradução!")
        report_lines.append("Certifique-se de analisar o livro primeiro.")
        report_text = "\n".join(report_lines)
        return report_text, ""
    
    # FILTRAR sentenças boas para teste (não nomes próprios, texto real)
    good_sentences = [s for s in all_sentences_to_translate if is_good_test_sentence(s.text)]
    
    report_lines.append("-" * 80)
    report_lines.append("FILTRAGEM DE SENTENÇAS PARA TESTE")
    report_lines.append("-" * 80)
    report_lines.append(f"Total de sentenças marcadas no livro: {len(all_sentences_to_translate)}")
    report_lines.append(f"Sentenças adequadas para teste (>20 chars, frases reais): {len(good_sentences)}")
    
    if not good_sentences:
        report_lines.append("")
        report_lines.append("⚠️ AVISO: Nenhuma sentença adequada encontrada!")
        report_lines.append("Usando as primeiras sentenças disponíveis...")
        good_sentences = all_sentences_to_translate
    
    # Selecionar sentenças para teste
    test_sentences = good_sentences[:max_sentences]
    
    report_lines.append(f"Sentenças selecionadas para teste: {len(test_sentences)}")
    report_lines.append("")
    
    for i, sentence in enumerate(test_sentences, 1):
        cefr_val = sentence.cefr_level.value if sentence.cefr_level else 'N/A'
        report_lines.append(f"[{i}] ID={sentence.index} | CEFR={cefr_val} | Chars={len(sentence.text)}")
        report_lines.append(f"    Texto: {sentence.text[:100]}{'...' if len(sentence.text) > 100 else ''}")
    report_lines.append("")
    
    # Construir prompt simplificado para JSON output
    source_lang_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
    target_lang_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
    
    # Lista de sentenças para o prompt
    sentences_list = [f"ID {s.index}: {s.text}" for s in test_sentences]
    
    prompt = f"""Translate these sentences from {source_lang_name} to {target_lang_name}.
You MUST translate - do NOT return the original text.

{chr(10).join(sentences_list)}"""
    
    report_lines.append("-" * 80)
    report_lines.append("PROMPT ENVIADO")
    report_lines.append("-" * 80)
    report_lines.append(prompt)
    report_lines.append("")
    
    # JSON Schema para structured output
    sentence_ids = [s.index for s in test_sentences]
    translation_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "translations",
            "schema": {
                "type": "object",
                "properties": {
                    "translations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "integer",
                                    "description": "The sentence ID"
                                },
                                "text": {
                                    "type": "string",
                                    "description": "The translated text"
                                }
                            },
                            "required": ["id", "text"]
                        }
                    }
                },
                "required": ["translations"]
            }
        }
    }
    
    # Fazer chamada ao LM Studio
    report_lines.append("-" * 80)
    report_lines.append("CHAMADA À API (JSON Structured Output)")
    report_lines.append("-" * 80)
    
    url = f"{lm_studio_url.rstrip('/')}/chat/completions"
    
    payload = {
        "model": lm_studio_model if lm_studio_model else "local-model",
        "messages": [
            {
                "role": "system",
                "content": f"You are an expert translator from {source_lang_name} to {target_lang_name}. Always provide actual translations, never return the original text unchanged. Be accurate and natural."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": len(prompt) * 2,
        "stream": False,
        "response_format": translation_schema
    }
    
    report_lines.append(f"URL: {url}")
    report_lines.append(f"Payload (resumido):")
    report_lines.append(f"  model: {payload['model']}")
    report_lines.append(f"  temperature: {payload['temperature']}")
    report_lines.append(f"  max_tokens: {payload['max_tokens']}")
    report_lines.append("")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=120)
        elapsed_time = time.time() - start_time
        
        report_lines.append(f"Status Code: {response.status_code}")
        report_lines.append(f"Tempo de resposta: {elapsed_time:.2f}s")
        report_lines.append("")
        
        if response.status_code != 200:
            report_lines.append(f"❌ ERRO HTTP: {response.status_code}")
            report_lines.append(f"Resposta: {response.text[:500]}")
        else:
            result = response.json()
            
            report_lines.append("-" * 80)
            report_lines.append("RESPOSTA RAW DA API")
            report_lines.append("-" * 80)
            
            raw_json = json.dumps(result, indent=2, ensure_ascii=False)
            if len(raw_json) > 2000:
                report_lines.append(raw_json[:2000] + "\n... [truncado]")
            else:
                report_lines.append(raw_json)
            report_lines.append("")
            
            if "choices" in result and len(result["choices"]) > 0:
                llm_output = result["choices"][0]["message"]["content"]
                
                report_lines.append("-" * 80)
                report_lines.append("OUTPUT DO LLM (JSON)")
                report_lines.append("-" * 80)
                report_lines.append(llm_output)
                report_lines.append("")
                
                # Parsear traduções do JSON
                report_lines.append("-" * 80)
                report_lines.append("PARSING DAS TRADUÇÕES (JSON)")
                report_lines.append("-" * 80)
                
                translations_found = {}
                
                try:
                    data = json.loads(llm_output)
                    translations = data.get("translations", [])
                    
                    for item in translations:
                        idx = item.get("id")
                        text = item.get("text", "").strip()
                        
                        if idx is not None and text:
                            translations_found[idx] = text
                            report_lines.append(f"✓ ID {idx}: {text[:70]}{'...' if len(text) > 70 else ''}")
                    
                    report_lines.append("")
                    report_lines.append(f"✅ JSON parseado com sucesso!")
                    
                except json.JSONDecodeError as e:
                    report_lines.append(f"⚠️ Erro ao parsear JSON: {e}")
                    report_lines.append("Tentando fallback com parsing de texto...")
                    report_lines.append("")
                    
                    # Fallback: parsing de texto
                    pattern = r'^(?:ID:?\s*)?(\d+)\s*:\s*(.+)$'
                    for line in llm_output.strip().split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        match = re.match(pattern, line)
                        if match:
                            idx = int(match.group(1))
                            translation = match.group(2).strip()
                            if translation:
                                translations_found[idx] = translation
                                report_lines.append(f"✓ ID {idx} (fallback): {translation[:70]}{'...' if len(translation) > 70 else ''}")
                
                report_lines.append("")
                report_lines.append(f"Total de traduções parseadas: {len(translations_found)}")
                report_lines.append(f"Esperado: {len(test_sentences)}")
                
                if len(translations_found) == len(test_sentences):
                    report_lines.append("✅ PARSING: Todas as traduções foram extraídas!")
                elif len(translations_found) > 0:
                    report_lines.append("⚠️ PARSING PARCIAL: Algumas traduções não foram encontradas")
                else:
                    report_lines.append("❌ PARSING FALHOU: Nenhuma tradução foi parseada")
                
                # ============================================================
                # ANÁLISE DE QUALIDADE DA TRADUÇÃO
                # ============================================================
                report_lines.append("")
                report_lines.append("-" * 80)
                report_lines.append("🔍 ANÁLISE DE QUALIDADE DA TRADUÇÃO")
                report_lines.append("-" * 80)
                
                quality_issues = []
                good_translations = []
                
                for sentence in test_sentences:
                    original = sentence.text
                    translated = translations_found.get(sentence.index, None)
                    
                    report_lines.append(f"\n📝 Sentence ID: {sentence.index}")
                    report_lines.append(f"   Original ({source_lang}):  {original[:70]}{'...' if len(original) > 70 else ''}")
                    
                    if translated is None:
                        report_lines.append(f"   Tradução ({target_lang}): ❌ NÃO ENCONTRADA")
                        quality_issues.append(f"ID {sentence.index}: Tradução não retornada")
                    else:
                        report_lines.append(f"   Tradução ({target_lang}): {translated[:70]}{'...' if len(translated) > 70 else ''}")
                        
                        # Calcular similaridade
                        similarity = calculate_similarity(original, translated)
                        
                        if similarity >= 0.9:
                            report_lines.append(f"   ⚠️ PROBLEMA: Similaridade {similarity:.0%} - Texto quase idêntico ao original!")
                            report_lines.append(f"      → A LLM provavelmente NÃO traduziu esta sentença")
                            quality_issues.append(f"ID {sentence.index}: Não traduzido (similaridade {similarity:.0%})")
                        elif similarity >= 0.6:
                            report_lines.append(f"   ⚠️ AVISO: Similaridade {similarity:.0%} - Tradução pode estar incompleta")
                            quality_issues.append(f"ID {sentence.index}: Tradução suspeita (similaridade {similarity:.0%})")
                        else:
                            report_lines.append(f"   ✅ OK: Similaridade {similarity:.0%} - Texto foi modificado")
                            good_translations.append(sentence.index)
                
                # Resumo da qualidade
                report_lines.append("")
                report_lines.append("-" * 80)
                report_lines.append("📊 RESUMO DA QUALIDADE")
                report_lines.append("-" * 80)
                
                total = len(test_sentences)
                good = len(good_translations)
                bad = len(quality_issues)
                
                report_lines.append(f"Total testadas: {total}")
                report_lines.append(f"✅ Traduções OK: {good} ({good/total*100:.0f}%)")
                report_lines.append(f"⚠️ Problemas: {bad} ({bad/total*100:.0f}%)")
                report_lines.append("")
                
                if bad == 0:
                    report_lines.append("🎉 EXCELENTE! Todas as traduções parecem válidas.")
                    report_lines.append("   A LLM está traduzindo corretamente.")
                elif good == 0:
                    report_lines.append("❌ CRÍTICO! Nenhuma tradução válida detectada.")
                    report_lines.append("   POSSÍVEIS CAUSAS:")
                    report_lines.append("   1. O modelo não suporta bem o par de idiomas")
                    report_lines.append("   2. O modelo é muito pequeno para tradução")
                    report_lines.append("   3. O prompt precisa de ajustes para este modelo")
                    report_lines.append("")
                    report_lines.append("   RECOMENDAÇÕES:")
                    report_lines.append("   - Tente um modelo maior (7B+ parâmetros)")
                    report_lines.append("   - Use um modelo treinado para tradução")
                    report_lines.append("   - Considere usar a API do Gemini")
                else:
                    report_lines.append(f"⚠️ PARCIAL: {good}/{total} traduções válidas.")
                    report_lines.append("   O modelo está traduzindo algumas sentenças.")
                    report_lines.append("   Considere usar um modelo maior para melhor qualidade.")
                
                if quality_issues:
                    report_lines.append("")
                    report_lines.append("Problemas encontrados:")
                    for issue in quality_issues:
                        report_lines.append(f"   - {issue}")
                
                # ============================================================
                # ESTIMATIVA DE TEMPO PARA TRADUÇÃO COMPLETA
                # ============================================================
                report_lines.append("")
                report_lines.append("-" * 80)
                report_lines.append("⏱️ ESTIMATIVA DE TEMPO PARA TRADUÇÃO COMPLETA")
                report_lines.append("-" * 80)
                
                # Obter métricas do teste
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens_test = usage.get("total_tokens", prompt_tokens + completion_tokens)
                
                # Calcular velocidade de processamento
                if elapsed_time > 0 and total_tokens_test > 0:
                    tokens_per_second = total_tokens_test / elapsed_time
                    
                    # Estimar tokens totais para o livro completo
                    total_sentences_book = len(all_sentences_to_translate)
                    tested_sentences = len(test_sentences)
                    
                    # Chars médios por sentença testada
                    avg_chars_per_sentence = sum(len(s.text) for s in test_sentences) / tested_sentences if tested_sentences > 0 else 50
                    
                    # Chars totais do livro
                    total_chars_book = sum(len(s.text) for s in all_sentences_to_translate)
                    
                    # Estimar tokens totais (prompt + completion) baseado na proporção do teste
                    # O teste usa X sentenças e gera Y tokens, então para N sentenças...
                    tokens_per_sentence = total_tokens_test / tested_sentences if tested_sentences > 0 else 50
                    estimated_total_tokens = total_sentences_book * tokens_per_sentence
                    
                    # Tempo estimado
                    estimated_seconds = estimated_total_tokens / tokens_per_second
                    estimated_minutes = estimated_seconds / 60
                    estimated_hours = estimated_minutes / 60
                    
                    report_lines.append(f"📊 Métricas do teste:")
                    report_lines.append(f"   Sentenças testadas: {tested_sentences}")
                    report_lines.append(f"   Tokens de prompt: {prompt_tokens:,}")
                    report_lines.append(f"   Tokens de resposta: {completion_tokens:,}")
                    report_lines.append(f"   Tokens totais: {total_tokens_test:,}")
                    report_lines.append(f"   Tempo de resposta: {elapsed_time:.2f}s")
                    report_lines.append(f"   Velocidade: {tokens_per_second:.1f} tokens/s")
                    report_lines.append("")
                    report_lines.append(f"📖 Dados do livro completo:")
                    report_lines.append(f"   Total de sentenças a traduzir: {total_sentences_book:,}")
                    report_lines.append(f"   Total de caracteres: {total_chars_book:,}")
                    report_lines.append(f"   Tokens estimados: {estimated_total_tokens:,.0f}")
                    report_lines.append("")
                    report_lines.append(f"⏱️ Tempo estimado para tradução completa:")
                    
                    if estimated_hours >= 1:
                        report_lines.append(f"   🕐 {estimated_hours:.1f} horas ({estimated_minutes:.0f} minutos)")
                    elif estimated_minutes >= 1:
                        report_lines.append(f"   🕐 {estimated_minutes:.1f} minutos ({estimated_seconds:.0f} segundos)")
                    else:
                        report_lines.append(f"   🕐 {estimated_seconds:.0f} segundos")
                    
                    report_lines.append("")
                    report_lines.append(f"   ⚠️ Esta é uma estimativa aproximada.")
                    report_lines.append(f"   O tempo real pode variar dependendo do tamanho dos batches,")
                    report_lines.append(f"   carga do sistema e complexidade do texto.")
                else:
                    report_lines.append("   ⚠️ Não foi possível calcular a estimativa de tempo.")
                    report_lines.append("   (Dados de tokens ou tempo insuficientes)")
                
            else:
                report_lines.append("❌ ERRO: Formato de resposta inesperado")
                report_lines.append("Não foi possível encontrar 'choices' na resposta")
                
    except requests.exceptions.ConnectionError:
        report_lines.append("❌ ERRO DE CONEXÃO")
        report_lines.append("Não foi possível conectar ao LM Studio.")
        report_lines.append("Verifique se o servidor está rodando.")
    except requests.exceptions.Timeout:
        report_lines.append("❌ TIMEOUT")
        report_lines.append("A requisição excedeu o tempo limite de 120s.")
    except Exception as e:
        report_lines.append(f"❌ ERRO: {type(e).__name__}")
        report_lines.append(str(e))
        import traceback
        report_lines.append(traceback.format_exc())
    
    # Finalizar relatório
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("FIM DO RELATÓRIO")
    report_lines.append("=" * 80)
    
    report_text = "\n".join(report_lines)
    
    # Salvar arquivo
    try:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"llm_test_{timestamp}.txt"
        filepath = output_dir / filename
        filepath.write_text(report_text, encoding="utf-8")
        
        return report_text, str(filepath)
    except Exception as e:
        return report_text, f"Erro ao salvar: {e}"


def analyze_epub(
    uploaded_file,
    source_lang: str,
    user_level: str,
    translation_mode: str,
    progress_callback,
    log_callback=None
) -> tuple[Optional[EpubStructure], Optional[dict], Optional[str]]:
    """
    Analisa o EPUB sem traduzir - apenas parsing e análise de dificuldade
    
    Returns:
        Tuple[estrutura do EPUB, estatísticas, caminho temporário]
    """
    def log(message: str):
        if log_callback:
            log_callback(message)
    
    stats = {
        "total_chapters": 0,
        "total_sentences": 0,
        "sentences_analyzed": 0,
        "sentences_to_translate": 0,
        "sentences_kept_original": 0,
        "cefr_distribution": {},
        "analysis_time": 0
    }
    
    start_time = time.time()
    
    try:
        # Salvar arquivo temporário
        log("💾 Salvando arquivo temporário...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        log(f"✓ Arquivo salvo: {tmp_path}")
        
        # =====================================================================
        # Fase 1: Parsing
        # =====================================================================
        progress_callback(0.05, "📖 Iniciando parsing do EPUB...")
        log("📖 Iniciando parsing do EPUB...")
        
        structure = parse_epub(tmp_path)
        stats["total_chapters"] = structure.chapter_count
        stats["total_sentences"] = structure.total_sentences
        
        log(f"✓ Título: {structure.title}")
        log(f"✓ Autor: {structure.author}")
        log(f"✓ Capítulos: {structure.chapter_count}")
        log(f"✓ Sentenças extraídas: {structure.total_sentences}")
        
        progress_callback(0.20, f"✓ {structure.chapter_count} capítulos, {structure.total_sentences} sentenças")
        
        # =====================================================================
        # Fase 2: Análise de Dificuldade
        # =====================================================================
        progress_callback(0.25, "🔍 Iniciando análise de dificuldade...")
        log(f"🔍 Analisando dificuldade com wordfreq (idioma: {source_lang})...")
        
        analyzer = DifficultyAnalyzer(language=source_lang)
        user_cefr = CEFRLevel[user_level.replace("+", "_PLUS")]
        log(f"📊 Nível do usuário: {user_level}")
        log(f"🔄 Modo: {'Traduzir ACIMA do nível' if translation_mode == 'above' else 'Traduzir ABAIXO do nível'}")
        
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
            # Usar .value para comparar numericamente os níveis CEFR
            sentence_level = analyzed.cefr_level
            
            if translation_mode == 'above':
                # Traduz o que está ACIMA do nível (exclui o nível do usuário)
                should_translate = sentence_level.value > user_cefr.value
            else:
                # Traduz o que está ABAIXO do nível (exclui o nível do usuário)
                should_translate = sentence_level.value < user_cefr.value
            
            if should_translate:
                sentence.should_translate = True
                sentences_to_translate.append(sentence)
            else:
                sentence.should_translate = False
            
            # Atualizar progresso e log a cada 500 sentenças
            if i % 500 == 0 and i > 0:
                pct = 0.25 + (0.70 * i / len(all_sentences))
                progress_callback(pct, f"🔍 Analisando: {i}/{len(all_sentences)} sentenças")
                log(f"   Progresso: {i}/{len(all_sentences)} sentenças analisadas...")
        
        stats["sentences_analyzed"] = len(all_sentences)
        stats["sentences_to_translate"] = len(sentences_to_translate)
        stats["sentences_kept_original"] = len(all_sentences) - len(sentences_to_translate)
        stats["cefr_distribution"] = {level.name: count for level, count in level_counts.items()}
        stats["analysis_time"] = time.time() - start_time
        
        # Log da distribuição
        log("📈 Distribuição por nível CEFR:")
        for level_name, count in stats["cefr_distribution"].items():
            pct = (count / len(all_sentences) * 100) if all_sentences else 0
            log(f"   {level_name.replace('_PLUS', '+')}: {count} ({pct:.1f}%)")
        
        log(f"✓ Sentenças a traduzir: {stats['sentences_to_translate']}")
        log(f"✓ Sentenças originais: {stats['sentences_kept_original']}")
        log(f"⏱️ Tempo de análise: {stats['analysis_time']:.1f}s")
        
        progress_callback(1.0, "✅ Análise concluída!")
        log("✅ Análise concluída com sucesso!")
        
        return structure, stats, tmp_path
        
    except Exception as e:
        log(f"❌ ERRO: {str(e)}")
        progress_callback(0, f"❌ Erro: {str(e)}")
        raise e


def translate_and_generate(
    structure: EpubStructure,
    source_lang: str,
    target_lang: str,
    api_key: str,
    highlight_translated: bool,
    style_type: str,
    save_to_backend: bool,
    output_filename: str,
    progress_callback,
    log_callback=None,
    llm_backend: str = "gemini",
    lm_studio_url: str = "http://localhost:1234/v1",
    lm_studio_model: str = "",
    context_length: int = 128000
) -> tuple[Optional[bytes], Optional[dict]]:
    """
    Traduz as sentenças marcadas e gera o EPUB final
    
    Returns:
        Tuple[bytes do EPUB, estatísticas de tradução]
    """
    # =========================================================================
    # Setup do Log em Arquivo
    # =========================================================================
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"translation_{timestamp}.txt"
    log_filepath = log_dir / log_filename
    
    def log(message: str):
        """Log para callback e arquivo em tempo real"""
        timestamped_msg = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        
        # Log para callback (UI)
        if log_callback:
            log_callback(message)
        
        # Log para arquivo em tempo real
        try:
            with open(log_filepath, "a", encoding="utf-8") as f:
                f.write(timestamped_msg + "\n")
                f.flush()  # Garantir escrita imediata
        except Exception:
            pass  # Não interromper por erro de log
    
    stats = {
        "batches_total": 0,
        "batches_success": 0,
        "batches_failed": 0,
        "backend_saved": False,
        "backend_path": None,
        "log_filepath": str(log_filepath)
    }
    start_time = time.time()
    
    # Header do log
    log("=" * 70)
    log("MULTI-LANGUAGE BOOKS - LOG DE TRADUÇÃO")
    log("=" * 70)
    log(f"Arquivo de saída: {output_filename}")
    log(f"Log salvo em: {log_filepath}")
    log("")
    
    try:
        sentences_to_translate = [s for s in structure.get_all_sentences() if s.should_translate]
        
        # =====================================================================
        # Fase 1: Tradução
        # =====================================================================
        if sentences_to_translate:
            backend_name = "Gemini API" if llm_backend == "gemini" else "LM Studio"
            progress_callback(0.02, f"🌐 Conectando com {backend_name}...")
            log(f"🌐 Iniciando tradução com {backend_name}...")
            log(f"   Idioma origem: {source_lang} ({SUPPORTED_LANGUAGES.get(source_lang, source_lang)})")
            log(f"   Idioma destino: {target_lang} ({SUPPORTED_LANGUAGES.get(target_lang, target_lang)})")
            log(f"   Sentenças a traduzir: {len(sentences_to_translate)}")
            log(f"   Context length: {context_length:,} tokens")
            log("")
            
            engine = TranslationEngine(
                api_key=api_key,
                source_lang=source_lang,
                target_lang=target_lang,
                backend=llm_backend,
                lm_studio_url=lm_studio_url,
                lm_studio_model=lm_studio_model if lm_studio_model else None,
                context_length=context_length
            )
            
            log(f"✓ Conexão com {backend_name} estabelecida")
            log(f"   Max chars por batch: {engine.max_chars_per_batch:,}")
            log("")
            
            # Variáveis para tracking de tempo e estimativa
            batch_times = []
            total_batches = [0]  # Será atualizado no primeiro callback
            
            def translation_progress(progress_pct, message):
                pct = 0.05 + (0.70 * progress_pct)
                progress_callback(pct, f"🌐 {message}")
            
            def batch_complete_callback(batch_result: BatchResult):
                """Callback chamado após cada batch"""
                nonlocal batch_times, total_batches
                
                total_batches[0] = batch_result.total_batches
                batch_times.append(batch_result.elapsed_time)
                
                # Calcular estatísticas
                avg_time = sum(batch_times) / len(batch_times)
                remaining_batches = batch_result.total_batches - batch_result.batch_number
                estimated_remaining = avg_time * remaining_batches
                
                # Formatar tempo restante
                if estimated_remaining >= 60:
                    time_str = f"{estimated_remaining / 60:.1f} min"
                else:
                    time_str = f"{estimated_remaining:.0f}s"
                
                # Log do batch
                log("-" * 50)
                log(f"📦 BATCH {batch_result.batch_number}/{batch_result.total_batches}")
                log(f"   Tempo: {batch_result.elapsed_time:.1f}s")
                log(f"   Sentenças no batch: {batch_result.sentences_in_batch}")
                log(f"   Traduzidas com sucesso: {batch_result.sentences_translated}")
                
                if batch_result.success:
                    log(f"   Status: ✓ Sucesso")
                    stats["batches_success"] = stats.get("batches_success", 0) + 1
                else:
                    log(f"   Status: ✗ Falha - {batch_result.error_message}")
                    stats["batches_failed"] = stats.get("batches_failed", 0) + 1
                
                # Mostrar traduções do batch
                if batch_result.translations:
                    log("")
                    log("   📝 Traduções realizadas:")
                    for sent_id, (original, translated) in batch_result.translations.items():
                        # Truncar textos longos
                        orig_short = original[:60] + "..." if len(original) > 60 else original
                        trans_short = translated[:60] + "..." if len(translated) > 60 else translated
                        log(f"      [{sent_id}]")
                        log(f"         Original:  {orig_short}")
                        log(f"         Tradução:  {trans_short}")
                
                # Estimativa de tempo restante
                if remaining_batches > 0:
                    log("")
                    log(f"   ⏱️ Tempo médio por batch: {avg_time:.1f}s")
                    log(f"   ⏳ Estimativa restante: {time_str} ({remaining_batches} batches)")
                
                # Atualizar progresso com estimativa
                pct = 0.05 + (0.70 * (batch_result.batch_number / batch_result.total_batches))
                if remaining_batches > 0:
                    progress_callback(pct, f"🌐 Batch {batch_result.batch_number}/{batch_result.total_batches} | ⏳ ~{time_str} restantes")
                else:
                    progress_callback(pct, f"🌐 Batch {batch_result.batch_number}/{batch_result.total_batches} concluído!")
            
            log("📦 Iniciando processamento de batches...")
            log("")
            
            translation_stats = engine.translate_structure(
                structure=structure,
                progress_callback=translation_progress,
                batch_callback=batch_complete_callback
            )
            
            stats["sentences_translated"] = translation_stats.translated_sentences
            stats["translation_errors"] = translation_stats.failed_sentences
            stats["batches_total"] = translation_stats.total_batches
            
            log("")
            log("=" * 50)
            log("📊 RESUMO DA TRADUÇÃO")
            log("=" * 50)
            log(f"   Sentenças traduzidas: {translation_stats.translated_sentences}")
            log(f"   Sentenças com erro: {translation_stats.failed_sentences}")
            log(f"   Total de batches: {translation_stats.total_batches}")
            log(f"   Batches com sucesso: {stats.get('batches_success', 0)}")
            log(f"   Batches com falha: {stats.get('batches_failed', 0)}")
            log(f"   Tempo total de tradução: {translation_stats.total_time:.1f}s")
            
            if batch_times:
                log(f"   Tempo médio por batch: {sum(batch_times) / len(batch_times):.1f}s")
            
            if translation_stats.errors:
                log("")
                log("⚠️ Erros encontrados:")
                for error in translation_stats.errors[:10]:
                    log(f"   - {error}")
            
            log("")
            progress_callback(0.78, f"✓ {translation_stats.translated_sentences} sentenças traduzidas")
        else:
            stats["sentences_translated"] = 0
            log("ℹ️ Nenhuma sentença marcada para tradução")
            progress_callback(0.78, "ℹ️ Nenhuma sentença para traduzir")
        
        # =====================================================================
        # Fase 2: Geração do EPUB
        # =====================================================================
        progress_callback(0.80, "📝 Gerando novo EPUB...")
        log("")
        log("📝 Gerando arquivo EPUB...")
        
        epub_bytes = generate_epub(
            structure=structure,
            highlight_translated=highlight_translated,
            style_type=style_type
        )
        
        log(f"✓ EPUB gerado: {len(epub_bytes) / 1024:.1f} KB")
        
        # =====================================================================
        # Fase 3: Salvar no backend (se solicitado)
        # =====================================================================
        if save_to_backend:
            progress_callback(0.92, "💾 Salvando no servidor...")
            log("💾 Salvando cópia no servidor...")
            
            success, path_or_error = save_epub_to_backend(epub_bytes, output_filename)
            
            if success:
                stats["backend_saved"] = True
                stats["backend_path"] = path_or_error
                log(f"✓ Salvo em: {path_or_error}")
            else:
                log(f"⚠️ Falha ao salvar no backend: {path_or_error}")
        
        stats["processing_time"] = time.time() - start_time
        
        log("")
        log("=" * 70)
        log(f"✅ PROCESSO CONCLUÍDO COM SUCESSO")
        log(f"   Tempo total: {stats['processing_time']:.1f}s")
        log(f"   Log salvo em: {log_filepath}")
        log("=" * 70)
        
        progress_callback(1.0, "✅ EPUB gerado com sucesso!")
        
        return epub_bytes, stats
        
    except Exception as e:
        log("")
        log("=" * 70)
        log(f"❌ ERRO DURANTE A TRADUÇÃO")
        log(f"   {str(e)}")
        log("=" * 70)
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
        # Seletor de Backend LLM
        # =================================================================
        st.subheader("🤖 Backend de Tradução")
        
        llm_backend = st.radio(
            "Selecione o LLM",
            options=["gemini", "lm_studio"],
            format_func=lambda x: {
                "gemini": "🌐 Gemini API (Google)",
                "lm_studio": "💻 LM Studio (Local)"
            }.get(x, x),
            index=0,
            help="Escolha entre usar a API do Gemini ou um LLM local via LM Studio"
        )
        
        if llm_backend == "gemini":
            # =================================================================
            # API Key Configuration (Gemini)
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
        
        else:
            # =================================================================
            # LM Studio Configuration
            # =================================================================
            st.subheader("💻 Configuração LM Studio")
            
            lm_studio_url = st.text_input(
                "URL do LM Studio",
                value=st.session_state.lm_studio_url,
                help="URL da API do LM Studio (geralmente http://localhost:1234/v1)"
            )
            st.session_state.lm_studio_url = lm_studio_url
            
            lm_studio_model = st.text_input(
                "Nome do Modelo (opcional)",
                value=st.session_state.lm_studio_model,
                help="Nome do modelo carregado no LM Studio. Deixe vazio para usar o modelo ativo."
            )
            st.session_state.lm_studio_model = lm_studio_model
            
            # Context Length
            context_length = st.number_input(
                "Context Length (tokens)",
                min_value=1000,
                max_value=1000000,
                value=st.session_state.context_length,
                step=1000,
                help="Tamanho máximo do contexto do modelo em tokens. Usado para calcular o tamanho dos batches."
            )
            st.session_state.context_length = context_length
            
            # Mostrar estimativa de caracteres
            estimated_chars = int(context_length * 3.5)  # ~3.5 chars por token
            st.caption(f"≈ {estimated_chars:,} caracteres por batch")
            
            # Botão para testar conexão
            if st.button("🔌 Testar Conexão", use_container_width=True):
                try:
                    import requests
                    response = requests.get(f"{lm_studio_url}/models", timeout=5)
                    if response.status_code == 200:
                        models_data = response.json()
                        if "data" in models_data and len(models_data["data"]) > 0:
                            model_name = models_data["data"][0].get("id", "unknown")
                            st.success(f"✓ Conectado! Modelo: {model_name}")
                            if not lm_studio_model:
                                st.session_state.lm_studio_model = model_name
                        else:
                            st.success("✓ Conectado!")
                    else:
                        st.error(f"✗ Erro: Status {response.status_code}")
                except requests.exceptions.ConnectionError:
                    st.error("✗ Não foi possível conectar. Verifique se o LM Studio está rodando.")
                except Exception as e:
                    st.error(f"✗ Erro: {str(e)}")
            
            st.caption("💡 Certifique-se de que o LM Studio está rodando e a API está habilitada.")
            
            # Botão para rodar teste de tradução
            st.markdown("---")
            if st.button("🧪 Rodar Teste de Tradução", use_container_width=True, 
                        help="Testa a tradução com um batch de amostra do livro"):
                if not st.session_state.structure:
                    st.error("❌ Carregue e analise um EPUB primeiro!")
                elif not lm_studio_url:
                    st.error("❌ Configure a URL do LM Studio!")
                else:
                    with st.spinner("Executando teste de tradução..."):
                        # Obter idiomas selecionados (valores padrão se não configurados ainda)
                        test_source = st.session_state.get('test_source_lang', 'en')
                        test_target = st.session_state.get('test_target_lang', 'pt')
                        
                        report, filepath = run_llm_translation_test(
                            structure=st.session_state.structure,
                            source_lang=test_source,
                            target_lang=test_target,
                            lm_studio_url=lm_studio_url,
                            lm_studio_model=lm_studio_model
                        )
                        
                        st.session_state.llm_test_report = report
                        st.session_state.llm_test_filepath = filepath
                        st.success(f"✓ Teste concluído! Arquivo salvo em: {filepath}")
        
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
        st.session_state.test_source_lang = source_lang
        
        target_lang = st.selectbox(
            "Seu idioma nativo (destino)",
            options=list(SUPPORTED_LANGUAGES.keys()),
            format_func=lambda x: f"{SUPPORTED_LANGUAGES[x]} ({x})",
            index=1,
            help="O idioma para o qual as sentenças selecionadas serão traduzidas"
        )
        st.session_state.test_target_lang = target_lang
        
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
        # Opções de Salvamento
        # =================================================================
        st.subheader("💾 Salvamento")
        
        save_to_backend = st.checkbox(
            "Salvar cópia no servidor",
            value=True,
            help="Salva o EPUB no servidor como backup. Útil caso o navegador entre em modo sleep."
        )
        
        if save_to_backend:
            st.caption("📁 EPUBs serão salvos na pasta `output/`")
        
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
                log_container = st.container()
                
                # Lista para armazenar logs
                log_messages = []
                
                with progress_container:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    def update_progress(pct: float, message: str):
                        progress_bar.progress(pct)
                        status_text.markdown(f"**{message}**")
                    
                    # Área de log expansível
                    with log_container:
                        log_expander = st.expander("📋 Log de Análise", expanded=True)
                        log_placeholder = log_expander.empty()
                        
                        def add_log(message: str):
                            log_messages.append(f"`{time.strftime('%H:%M:%S')}` {message}")
                            log_placeholder.markdown("\n\n".join(log_messages))
                    
                    try:
                        structure, stats, tmp_path = analyze_epub(
                            uploaded_file=uploaded_file,
                            source_lang=source_lang,
                            user_level=user_level,
                            translation_mode=translation_mode,
                            progress_callback=update_progress,
                            log_callback=add_log
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
                
                # Recalcular sentenças a traduzir baseado no nível e modo atuais
                # (permite ajustar após a análise sem reanalisar)
                if st.session_state.structure:
                    user_cefr = CEFRLevel[user_level.replace("+", "_PLUS")]
                    sentences_to_translate_count = 0
                    
                    for sentence in st.session_state.structure.get_all_sentences():
                        if sentence.cefr_level:
                            if translation_mode == 'above':
                                should_translate = sentence.cefr_level.value > user_cefr.value
                            else:
                                should_translate = sentence.cefr_level.value < user_cefr.value
                            
                            sentence.should_translate = should_translate
                            if should_translate:
                                sentences_to_translate_count += 1
                    
                    # Atualizar stats dinâmicos
                    stats["sentences_to_translate"] = sentences_to_translate_count
                    stats["sentences_kept_original"] = stats["total_sentences"] - sentences_to_translate_count
                
                # Mostrar resumo
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    st.metric("📚 Capítulos", stats["total_chapters"])
                with col_r2:
                    st.metric("📝 Sentenças", stats["total_sentences"])
                with col_r3:
                    pct_translate = (stats["sentences_to_translate"] / stats["total_sentences"] * 100) if stats["total_sentences"] > 0 else 0
                    st.metric("🌐 A traduzir", f"{stats['sentences_to_translate']} ({pct_translate:.1f}%)")
                
                # Tempo de análise
                if "analysis_time" in stats:
                    st.caption(f"⏱️ Tempo de análise: {stats['analysis_time']:.1f}s")
                
                # Aviso sobre configuração do backend
                translate_disabled = False
                if llm_backend == "gemini":
                    if not st.session_state.gemini_api_key:
                        st.error("⚠️ Configure sua chave API do Gemini na barra lateral antes de traduzir!")
                        translate_disabled = True
                else:  # lm_studio
                    if not st.session_state.lm_studio_url:
                        st.error("⚠️ Configure a URL do LM Studio na barra lateral antes de traduzir!")
                        translate_disabled = True
                
                # Botão de tradução
                st.markdown("---")
                if st.button(
                    "🚀 Confirmar e Traduzir", 
                    type="primary", 
                    use_container_width=True,
                    disabled=translate_disabled
                ):
                    progress_container = st.container()
                    log_container = st.container()
                    
                    # Lista para armazenar logs
                    log_messages = []
                    
                    with progress_container:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(pct: float, message: str):
                            progress_bar.progress(pct)
                            status_text.markdown(f"**{message}**")
                        
                        # Área de log expansível
                        with log_container:
                            log_expander = st.expander("📋 Log de Tradução", expanded=True)
                            log_placeholder = log_expander.empty()
                            
                            def add_log(message: str):
                                log_messages.append(f"`{time.strftime('%H:%M:%S')}` {message}")
                                log_placeholder.markdown("\n\n".join(log_messages))
                        
                        try:
                            epub_bytes, translation_stats = translate_and_generate(
                                structure=st.session_state.structure,
                                source_lang=source_lang,
                                target_lang=target_lang,
                                api_key=st.session_state.gemini_api_key,
                                highlight_translated=highlight_translated,
                                style_type=style_type if highlight_translated else "none",
                                save_to_backend=save_to_backend,
                                output_filename=st.session_state.output_filename,
                                progress_callback=update_progress,
                                log_callback=add_log,
                                llm_backend=llm_backend,
                                lm_studio_url=st.session_state.lm_studio_url,
                                lm_studio_model=st.session_state.lm_studio_model,
                                context_length=st.session_state.context_length
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
        
        # Mostrar info de salvamento no backend se aplicável
        stats = st.session_state.stats
        if stats.get("backend_saved"):
            st.success(f"💾 Cópia salva no servidor: `{stats.get('backend_path')}`")
        
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
            
            # Estatísticas finais
            if "processing_time" in stats:
                st.caption(f"⏱️ Tempo de tradução: {stats['processing_time']:.1f}s")
            if "sentences_translated" in stats:
                st.caption(f"🌐 Sentenças traduzidas: {stats['sentences_translated']}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # =========================================================================
    # Relatório de Teste LLM (se disponível)
    # =========================================================================
    if st.session_state.llm_test_report:
        st.divider()
        st.header("🧪 Relatório de Teste LLM")
        
        col_test1, col_test2 = st.columns([3, 1])
        
        with col_test2:
            # Botão para limpar o relatório
            if st.button("🗑️ Limpar Relatório", use_container_width=True):
                st.session_state.llm_test_report = None
                st.session_state.llm_test_filepath = None
                st.rerun()
            
            # Botão para download do relatório
            if st.session_state.llm_test_filepath:
                st.download_button(
                    label="📥 Baixar TXT",
                    data=st.session_state.llm_test_report,
                    file_name=Path(st.session_state.llm_test_filepath).name if st.session_state.llm_test_filepath else "llm_test.txt",
                    mime="text/plain",
                    use_container_width=True
                )
                st.caption(f"📁 {st.session_state.llm_test_filepath}")
        
        with col_test1:
            # Exibir o relatório em um expander
            with st.expander("📄 Ver Relatório Completo", expanded=True):
                st.code(st.session_state.llm_test_report, language=None)
    
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