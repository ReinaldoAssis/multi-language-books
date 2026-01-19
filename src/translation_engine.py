"""
Motor de Tradução para o Multi-Language Books

Responsabilidades:
- Preparar batches de sentenças para tradução
- Manter contexto ao redor das sentenças a traduzir
- Comunicar com Gemini API
- Processar respostas e mapear traduções
"""
import re
import time
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from .models import (
    Sentence, Paragraph, Chapter, EpubStructure, 
    TranslationRequest, TranslationResult, CEFRLevel
)

# Importar configurações
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import GEMINI_API_KEY, GEMINI_MODEL, SUPPORTED_LANGUAGES


@dataclass
class TranslationBatch:
    """Um batch de sentenças para tradução"""
    sentences_to_translate: List[Sentence]
    context_sentences: List[Sentence]
    prompt_text: str
    estimated_tokens: int = 0


@dataclass
class TranslationStats:
    """Estatísticas de tradução"""
    total_sentences: int = 0
    translated_sentences: int = 0
    failed_sentences: int = 0
    total_batches: int = 0
    total_tokens_used: int = 0
    total_time: float = 0.0
    errors: List[str] = field(default_factory=list)


class TranslationEngine:
    """Motor de tradução usando Gemini API"""
    
    # Número máximo de caracteres por batch (conservador para segurança)
    MAX_CHARS_PER_BATCH = 80000
    
    # Número de sentenças de contexto antes/depois
    CONTEXT_WINDOW = 2
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # segundos
    
    def __init__(self, 
                 api_key: str = GEMINI_API_KEY,
                 model: str = GEMINI_MODEL,
                 source_lang: str = "en",
                 target_lang: str = "pt"):
        """
        Inicializa o motor de tradução.
        
        Args:
            api_key: Chave da API do Gemini
            model: Nome do modelo a usar
            source_lang: Código do idioma de origem
            target_lang: Código do idioma de destino
        """
        self.api_key = api_key
        self.model = model
        self.source_lang = source_lang
        self.target_lang = target_lang
        
        # Inicializar cliente Gemini
        self.client = genai.Client(api_key=api_key)
        
        # Nomes completos dos idiomas
        self.source_lang_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
        self.target_lang_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        
        # Estatísticas
        self.stats = TranslationStats()
    
    def translate_structure(self, 
                           structure: EpubStructure,
                           progress_callback: Optional[Callable[[float, str], None]] = None
                           ) -> TranslationStats:
        """
        Traduz todas as sentenças marcadas em uma estrutura EPUB.
        
        Args:
            structure: Estrutura do EPUB com sentenças marcadas
            progress_callback: Função callback(progress, message) para progresso
            
        Returns:
            TranslationStats com estatísticas da tradução
        """
        start_time = time.time()
        self.stats = TranslationStats()
        
        # Obter todas as sentenças
        all_sentences = structure.get_all_sentences()
        sentences_to_translate = [s for s in all_sentences if s.should_translate]
        
        self.stats.total_sentences = len(sentences_to_translate)
        
        if not sentences_to_translate:
            if progress_callback:
                progress_callback(1.0, "Nenhuma sentença para traduzir")
            return self.stats
        
        # Criar batches
        batches = self._create_batches(all_sentences, sentences_to_translate)
        self.stats.total_batches = len(batches)
        
        if progress_callback:
            progress_callback(0.0, f"Preparados {len(batches)} batches para tradução")
        
        # Processar cada batch
        for i, batch in enumerate(batches):
            if progress_callback:
                progress = (i / len(batches))
                progress_callback(progress, f"Traduzindo batch {i+1}/{len(batches)}...")
            
            try:
                self._translate_batch(batch)
            except Exception as e:
                error_msg = f"Erro no batch {i+1}: {str(e)}"
                self.stats.errors.append(error_msg)
                print(f"⚠️ {error_msg}")
        
        self.stats.total_time = time.time() - start_time
        
        if progress_callback:
            progress_callback(1.0, f"Tradução concluída: {self.stats.translated_sentences}/{self.stats.total_sentences}")
        
        return self.stats
    
    def _create_batches(self, 
                        all_sentences: List[Sentence],
                        sentences_to_translate: List[Sentence]
                        ) -> List[TranslationBatch]:
        """
        Cria batches de sentenças para tradução, incluindo contexto.
        
        Args:
            all_sentences: Todas as sentenças do livro
            sentences_to_translate: Sentenças marcadas para tradução
            
        Returns:
            Lista de TranslationBatch
        """
        batches = []
        current_batch_sentences = []
        current_batch_context = set()
        current_chars = 0
        
        # Criar índice para acesso rápido
        sentence_index = {s.index: s for s in all_sentences}
        
        for sentence in sentences_to_translate:
            # Calcular contexto necessário
            context_indices = self._get_context_indices(sentence.index, len(all_sentences))
            context_sentences = [sentence_index[i] for i in context_indices if i in sentence_index]
            
            # Estimar tamanho
            sentence_size = len(sentence.text) + 20  # overhead para marcadores
            context_size = sum(len(s.text) + 20 for s in context_sentences if s.index not in current_batch_context)
            total_size = sentence_size + context_size
            
            # Verificar se cabe no batch atual
            if current_chars + total_size > self.MAX_CHARS_PER_BATCH and current_batch_sentences:
                # Finalizar batch atual
                batch = self._finalize_batch(current_batch_sentences, 
                                            [sentence_index[i] for i in current_batch_context if i in sentence_index])
                batches.append(batch)
                
                # Resetar para novo batch
                current_batch_sentences = []
                current_batch_context = set()
                current_chars = 0
            
            # Adicionar ao batch
            current_batch_sentences.append(sentence)
            current_batch_context.update(context_indices)
            current_chars += total_size
        
        # Finalizar último batch
        if current_batch_sentences:
            batch = self._finalize_batch(current_batch_sentences,
                                        [sentence_index[i] for i in current_batch_context if i in sentence_index])
            batches.append(batch)
        
        return batches
    
    def _get_context_indices(self, sentence_index: int, total_sentences: int) -> List[int]:
        """Obtém índices das sentenças de contexto"""
        context = []
        
        # Contexto anterior
        for i in range(1, self.CONTEXT_WINDOW + 1):
            idx = sentence_index - i
            if idx >= 0:
                context.append(idx)
        
        # Contexto posterior
        for i in range(1, self.CONTEXT_WINDOW + 1):
            idx = sentence_index + i
            if idx < total_sentences:
                context.append(idx)
        
        return sorted(context)
    
    def _finalize_batch(self, 
                       sentences_to_translate: List[Sentence],
                       context_sentences: List[Sentence]) -> TranslationBatch:
        """Cria um TranslationBatch finalizado com prompt"""
        # Construir prompt
        prompt_text = self._build_prompt(sentences_to_translate, context_sentences)
        
        # Estimar tokens (aproximação: 1 token ≈ 4 caracteres)
        estimated_tokens = len(prompt_text) // 4
        
        return TranslationBatch(
            sentences_to_translate=sentences_to_translate,
            context_sentences=context_sentences,
            prompt_text=prompt_text,
            estimated_tokens=estimated_tokens
        )
    
    def _build_prompt(self, 
                     sentences_to_translate: List[Sentence],
                     context_sentences: List[Sentence]) -> str:
        """
        Constrói o prompt para o Gemini.
        
        Args:
            sentences_to_translate: Sentenças a traduzir
            context_sentences: Sentenças de contexto
            
        Returns:
            Prompt formatado
        """
        # Combinar todas as sentenças e ordenar por índice
        all_sentences = sentences_to_translate + context_sentences
        all_sentences_sorted = sorted(all_sentences, key=lambda s: s.index)
        
        # Remover duplicatas mantendo ordem
        seen = set()
        unique_sentences = []
        for s in all_sentences_sorted:
            if s.index not in seen:
                seen.add(s.index)
                unique_sentences.append(s)
        
        # Set de índices a traduzir
        translate_indices = {s.index for s in sentences_to_translate}
        
        # Construir linhas do input
        input_lines = []
        for s in unique_sentences:
            marker = "[TRANSLATE]" if s.index in translate_indices else "[CONTEXT]"
            input_lines.append(f"{marker} {s.index}: {s.text}")
        
        # Prompt completo
        prompt = f"""You are a professional translator helping create a bilingual learning book.

**Task:** Translate ONLY the sentences marked with [TRANSLATE] from {self.source_lang_name} to {self.target_lang_name}.

**Important Rules:**
1. Keep the exact sentence numbering in your response
2. Only translate sentences marked with [TRANSLATE]
3. Maintain the same tone, style, and register
4. Preserve proper nouns unless they have well-known translations
5. Keep punctuation consistent with the target language conventions
6. Do NOT translate sentences marked with [CONTEXT] - they are only for reference
7. Return ONLY the translations in the exact format: "ID: translated text"

**Input:**
{chr(10).join(input_lines)}

**Expected Output Format (translate ONLY [TRANSLATE] sentences):**
"""
        # Adicionar exemplos do formato esperado
        example_ids = [s.index for s in sentences_to_translate[:3]]
        for idx in example_ids:
            prompt += f"\n{idx}: [tradução aqui]"
        
        prompt += "\n\n**Your translations:**"
        
        return prompt
    
    def _translate_batch(self, batch: TranslationBatch) -> None:
        """
        Traduz um batch de sentenças.
        
        Args:
            batch: Batch a traduzir
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                # Chamar API do Gemini
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=batch.prompt_text,
                    config=types.GenerateContentConfig(
                        temperature=0.3,  # Baixa temperatura para traduções consistentes
                        max_output_tokens=batch.estimated_tokens * 2,  # Margem para resposta
                    )
                )
                
                # Processar resposta
                if response.text:
                    self._parse_translations(response.text, batch.sentences_to_translate)
                    return
                else:
                    raise Exception("Resposta vazia do Gemini")
                    
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    print(f"  Tentativa {attempt + 1} falhou: {e}. Retentando em {self.RETRY_DELAY}s...")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))  # Backoff exponencial
                else:
                    raise Exception(f"Falha após {self.MAX_RETRIES} tentativas: {e}")
    
    def _parse_translations(self, 
                           response_text: str, 
                           sentences: List[Sentence]) -> None:
        """
        Faz o parsing das traduções da resposta do Gemini.
        
        Args:
            response_text: Texto da resposta
            sentences: Sentenças originais para mapear
        """
        # Criar mapa de índice para sentença
        sentence_map = {s.index: s for s in sentences}
        
        # Regex para encontrar traduções no formato "ID: texto"
        # Suporta números com ou sem espaços
        pattern = r'^(\d+)\s*:\s*(.+)$'
        
        lines = response_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            match = re.match(pattern, line)
            if match:
                idx = int(match.group(1))
                translation = match.group(2).strip()
                
                if idx in sentence_map:
                    sentence_map[idx].translated_text = translation
                    self.stats.translated_sentences += 1
        
        # Verificar sentenças não traduzidas
        for sentence in sentences:
            if sentence.translated_text is None:
                self.stats.failed_sentences += 1
                # Usar texto original como fallback
                sentence.translated_text = sentence.text
    
    def translate_single(self, text: str) -> str:
        """
        Traduz um único texto.
        
        Args:
            text: Texto a traduzir
            
        Returns:
            Texto traduzido
        """
        prompt = f"""Translate the following text from {self.source_lang_name} to {self.target_lang_name}.
Keep the same tone and style. Only return the translation, nothing else.

Text: {text}

Translation:"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=len(text) * 3,
                )
            )
            
            if response.text:
                return response.text.strip()
            return text
            
        except Exception as e:
            print(f"Erro na tradução: {e}")
            return text


def translate_epub_structure(structure: EpubStructure,
                            source_lang: str = "en",
                            target_lang: str = "pt",
                            api_key: str = GEMINI_API_KEY,
                            progress_callback: Optional[Callable[[float, str], None]] = None
                            ) -> TranslationStats:
    """
    Função de conveniência para traduzir uma estrutura EPUB.
    
    Args:
        structure: Estrutura do EPUB com sentenças marcadas (should_translate=True)
        source_lang: Código do idioma de origem
        target_lang: Código do idioma de destino
        api_key: Chave da API do Gemini
        progress_callback: Função callback(progress, message)
        
    Returns:
        TranslationStats com estatísticas
    """
    engine = TranslationEngine(
        api_key=api_key,
        source_lang=source_lang,
        target_lang=target_lang
    )
    
    return engine.translate_structure(structure, progress_callback)


def translate_text(text: str,
                  source_lang: str = "en",
                  target_lang: str = "pt",
                  api_key: str = GEMINI_API_KEY) -> str:
    """
    Função de conveniência para traduzir um texto simples.
    
    Args:
        text: Texto a traduzir
        source_lang: Código do idioma de origem
        target_lang: Código do idioma de destino
        api_key: Chave da API do Gemini
        
    Returns:
        Texto traduzido
    """
    engine = TranslationEngine(
        api_key=api_key,
        source_lang=source_lang,
        target_lang=target_lang
    )
    
    return engine.translate_single(text)
