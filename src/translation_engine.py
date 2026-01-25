"""
Motor de Tradução para o Multi-Language Books

Responsabilidades:
- Preparar batches de sentenças para tradução
- Manter contexto ao redor das sentenças a traduzir
- Comunicar com Gemini API ou LM Studio (OpenAI-compatible)
- Processar respostas e mapear traduções
"""
import re
import time
import requests
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


# Configurações padrão do LM Studio
LM_STUDIO_DEFAULT_URL = "http://localhost:1234/v1"
LM_STUDIO_DEFAULT_MODEL = "local-model"


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


@dataclass
class BatchResult:
    """Resultado de um batch de tradução"""
    batch_number: int
    total_batches: int
    sentences_in_batch: int
    sentences_translated: int
    translations: Dict[int, tuple]  # {sentence_id: (original, translated)}
    elapsed_time: float
    success: bool
    error_message: Optional[str] = None


class TranslationEngine:
    """Motor de tradução usando Gemini API ou LM Studio"""
    
    # Número de sentenças de contexto antes/depois
    CONTEXT_WINDOW = 1
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # segundos
    
    # Fator de conversão tokens -> caracteres (conservador)
    CHARS_PER_TOKEN = 3.5
    
    # Margem de segurança para o prompt (deixar espaço para resposta)
    # Para JSON output, precisamos de mais espaço para a resposta
    CONTEXT_USAGE_RATIO = 0.25  # Usar 25% do contexto para input (mais conservador para JSON)
    
    # Máximo de sentenças por batch (para evitar JSON muito grande)
    MAX_SENTENCES_PER_BATCH = 30
    
    def __init__(self, 
                 api_key: str = GEMINI_API_KEY,
                 model: str = GEMINI_MODEL,
                 source_lang: str = "en",
                 target_lang: str = "pt",
                 backend: str = "gemini",
                 lm_studio_url: str = LM_STUDIO_DEFAULT_URL,
                 lm_studio_model: str = LM_STUDIO_DEFAULT_MODEL,
                 context_length: int = 128000):
        """
        Inicializa o motor de tradução.
        
        Args:
            api_key: Chave da API do Gemini (ignorado se backend='lm_studio')
            model: Nome do modelo Gemini a usar
            source_lang: Código do idioma de origem
            target_lang: Código do idioma de destino
            backend: 'gemini' ou 'lm_studio'
            lm_studio_url: URL base do LM Studio (ex: http://localhost:1234/v1)
            lm_studio_model: Nome do modelo no LM Studio
            context_length: Tamanho do contexto do modelo em tokens
        """
        self.api_key = api_key
        self.model = model
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.backend = backend
        self.lm_studio_url = lm_studio_url.rstrip('/')
        self.lm_studio_model = lm_studio_model
        self.context_length = context_length
        
        # Calcular tamanho máximo de caracteres por batch
        # Usar apenas uma fração do contexto para deixar espaço para a resposta
        max_input_tokens = int(context_length * self.CONTEXT_USAGE_RATIO)
        self.max_chars_per_batch = int(max_input_tokens * self.CHARS_PER_TOKEN)
        
        # Inicializar cliente baseado no backend
        if backend == "gemini":
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None  # LM Studio usa requests diretamente
        
        # Nomes completos dos idiomas
        self.source_lang_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
        self.target_lang_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        
        # Estatísticas
        self.stats = TranslationStats()
    
    def translate_structure(self, 
                           structure: EpubStructure,
                           progress_callback: Optional[Callable[[float, str], None]] = None,
                           batch_callback: Optional[Callable[['BatchResult'], None]] = None
                           ) -> TranslationStats:
        """
        Traduz todas as sentenças marcadas em uma estrutura EPUB.
        
        Args:
            structure: Estrutura do EPUB com sentenças marcadas
            progress_callback: Função callback(progress, message) para progresso
            batch_callback: Função callback(BatchResult) chamada após cada batch
            
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
            
            batch_start_time = time.time()
            batch_result = BatchResult(
                batch_number=i + 1,
                total_batches=len(batches),
                sentences_in_batch=len(batch.sentences_to_translate),
                sentences_translated=0,
                translations={},
                elapsed_time=0,
                success=False
            )
            
            try:
                # Guardar textos originais antes da tradução
                original_texts = {s.index: s.text for s in batch.sentences_to_translate}
                
                self._translate_batch(batch)
                
                # Coletar traduções realizadas
                for sentence in batch.sentences_to_translate:
                    if sentence.translated_text:
                        batch_result.translations[sentence.index] = (
                            original_texts[sentence.index],
                            sentence.translated_text
                        )
                        batch_result.sentences_translated += 1
                
                batch_result.success = True
                
            except Exception as e:
                error_msg = f"Erro no batch {i+1}: {str(e)}"
                self.stats.errors.append(error_msg)
                batch_result.error_message = str(e)
                print(f"⚠️ {error_msg}")
            
            batch_result.elapsed_time = time.time() - batch_start_time
            
            # Chamar callback do batch
            if batch_callback:
                batch_callback(batch_result)
        
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
            # Limitar por tamanho OU por número de sentenças (para JSON não ficar muito grande)
            batch_full = (current_chars + total_size > self.max_chars_per_batch or 
                         len(current_batch_sentences) >= self.MAX_SENTENCES_PER_BATCH)
            
            if batch_full and current_batch_sentences:
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
        
        # Estimar tokens de OUTPUT necessários para JSON
        # Cada tradução no JSON: {"id": N, "text": "..."} + texto traduzido
        # Overhead JSON por sentença: ~40 chars (~10 tokens)
        # Texto traduzido: assumir tamanho similar ao original
        total_text_chars = sum(len(s.text) for s in sentences_to_translate)
        json_overhead = len(sentences_to_translate) * 40  # {"id": N, "text": ""}, 
        estimated_output_chars = total_text_chars + json_overhead + 50  # +50 para { "translations": [...] }
        estimated_tokens = estimated_output_chars // 3  # ~3 chars per token para output
        
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
        Constrói o prompt para tradução.
        
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
        
        # Construir lista de sentenças para o prompt
        sentences_list = []
        for s in unique_sentences:
            if s.index in translate_indices:
                sentences_list.append(f"TRANSLATE ID {s.index}: {s.text}")
            else:
                sentences_list.append(f"CONTEXT: {s.text}")
        
        # Prompt simplificado para JSON output
        prompt = f"""Translate the sentences marked with TRANSLATE from {self.source_lang_name} to {self.target_lang_name}.
Ignore sentences marked with CONTEXT (they are only for reference).
You MUST translate - do NOT return the original text.

{chr(10).join(sentences_list)}"""
        
        return prompt
    
    def _translate_batch(self, batch: TranslationBatch) -> None:
        """
        Traduz um batch de sentenças.
        
        Args:
            batch: Batch a traduzir
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                if self.backend == "gemini":
                    response_text = self._call_gemini(batch)
                else:
                    response_text = self._call_lm_studio(batch)
                
                # Processar resposta
                if response_text:
                    self._parse_translations(response_text, batch.sentences_to_translate)
                    return
                else:
                    raise Exception("Resposta vazia do LLM")
                    
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    print(f"  Tentativa {attempt + 1} falhou: {e}. Retentando em {self.RETRY_DELAY}s...")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))  # Backoff exponencial
                else:
                    raise Exception(f"Falha após {self.MAX_RETRIES} tentativas: {e}")
    
    def _call_gemini(self, batch: TranslationBatch) -> str:
        """Chama a API do Gemini"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=batch.prompt_text,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=batch.estimated_tokens * 2,
            )
        )
        return response.text if response.text else ""
    
    def _get_translation_schema(self, sentence_ids: List[int]) -> dict:
        """Gera o JSON schema para as traduções esperadas"""
        return {
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
    
    def _call_lm_studio(self, batch: TranslationBatch) -> str:
        """Chama a API do LM Studio (OpenAI-compatible) com JSON structured output"""
        url = f"{self.lm_studio_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Obter IDs das sentenças a traduzir
        sentence_ids = [s.index for s in batch.sentences_to_translate]
        
        payload = {
            "model": self.lm_studio_model,
            "messages": [
                {
                    "role": "system",
                    "content": f"You are an expert translator from {self.source_lang_name} to {self.target_lang_name}. Always provide actual translations, never return the original text unchanged. Be accurate and natural."
                },
                {
                    "role": "user",
                    "content": batch.prompt_text
                }
            ],
            "temperature": 0.3,
            "max_tokens": max(batch.estimated_tokens * 3, 2000),  # Garantir mínimo de 2000 tokens
            "stream": False,
            "response_format": self._get_translation_schema(sentence_ids)
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        
        return ""
    
    def _parse_translations(self, 
                           response_text: str, 
                           sentences: List[Sentence]) -> None:
        """
        Faz o parsing das traduções da resposta JSON.
        
        Args:
            response_text: Texto da resposta (JSON)
            sentences: Sentenças originais para mapear
        """
        import json
        
        # Criar mapa de índice para sentença
        sentence_map = {s.index: s for s in sentences}
        expected_count = len(sentences)
        expected_ids = set(sentence_map.keys())
        
        print(f"  [DEBUG] IDs esperados no batch: {sorted(list(expected_ids))[:10]}... (total: {len(expected_ids)})")
        
        try:
            # Parsear JSON
            data = json.loads(response_text)
            
            # Extrair traduções
            translations = data.get("translations", [])
            actual_count = len(translations)
            received_ids = {item.get("id") for item in translations if item.get("id") is not None}
            
            print(f"  [DEBUG] IDs recebidos do LLM: {sorted(list(received_ids))[:10]}... (total: {len(received_ids)})")
            
            # Verificar se recebemos todas as traduções
            if actual_count < expected_count:
                print(f"  ⚠️ JSON incompleto: recebidas {actual_count}/{expected_count} traduções")
            
            # Verificar quais IDs coincidem
            matching_ids = expected_ids & received_ids
            missing_ids = expected_ids - received_ids
            extra_ids = received_ids - expected_ids
            
            print(f"  [DEBUG] IDs coincidentes: {len(matching_ids)}")
            if missing_ids:
                print(f"  [DEBUG] IDs faltando: {sorted(list(missing_ids))[:10]}...")
            if extra_ids:
                print(f"  [DEBUG] IDs extras (não esperados): {sorted(list(extra_ids))[:10]}...")
            
            for item in translations:
                idx = item.get("id")
                text = item.get("text", "").strip()
                
                if idx is not None and text and idx in sentence_map:
                    sentence_map[idx].translated_text = text
                    self.stats.translated_sentences += 1
                elif idx is not None and idx not in sentence_map:
                    print(f"  [DEBUG] ID {idx} não encontrado no sentence_map!")
                    
        except json.JSONDecodeError as e:
            print(f"  ⚠️ Erro ao parsear JSON: {e}")
            print(f"  Tentando fallback com parsing de texto...")
            # Fallback para parsing de texto se JSON falhar
            self._parse_translations_fallback(response_text, sentences)
            return
        
        # Verificar sentenças não traduzidas
        for sentence in sentences:
            if sentence.translated_text is None:
                self.stats.failed_sentences += 1
                # Usar texto original como fallback
                sentence.translated_text = sentence.text
    
    def _parse_translations_fallback(self, 
                                     response_text: str, 
                                     sentences: List[Sentence]) -> None:
        """
        Fallback: parsing de texto quando JSON falha.
        
        Args:
            response_text: Texto da resposta
            sentences: Sentenças originais para mapear
        """
        sentence_map = {s.index: s for s in sentences}
        
        # Limpar markdown e formatação
        clean_text = response_text
        clean_text = re.sub(r'\*\*', '', clean_text)
        clean_text = re.sub(r'---+', '', clean_text)
        
        # Padrão: "ID: texto" ou "N: texto"
        pattern = r'^(?:ID:?\s*)?(\d+)\s*:\s*(.+)$'
        
        for line in clean_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            match = re.match(pattern, line)
            if match:
                idx = int(match.group(1))
                translation = match.group(2).strip()
                
                if translation and idx in sentence_map:
                    sentence_map[idx].translated_text = translation
                    self.stats.translated_sentences += 1
        
        # Verificar sentenças não traduzidas
        for sentence in sentences:
            if sentence.translated_text is None:
                self.stats.failed_sentences += 1
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
            if self.backend == "gemini":
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
            else:
                # LM Studio
                url = f"{self.lm_studio_url}/chat/completions"
                
                payload = {
                    "model": self.lm_studio_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are a professional translator. Translate from {self.source_lang_name} to {self.target_lang_name}."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": len(text) * 3,
                    "stream": False
                }
                
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                result = response.json()
                
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"].strip()
            
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
