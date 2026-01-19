"""
Analisador de Dificuldade para o Multi-Language Books

Responsabilidades:
- Analisar dificuldade de cada sentença usando wordfreq
- Classificar sentenças por nível CEFR (A1-C2+)
- Considerar múltiplos fatores: frequência das palavras, comprimento, estrutura
"""
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from wordfreq import zipf_frequency, word_frequency

from .models import Sentence, Paragraph, Chapter, EpubStructure, CEFRLevel


@dataclass
class DifficultyScore:
    """Score de dificuldade de uma sentença"""
    avg_zipf: float           # Média de Zipf frequency das palavras
    min_zipf: float           # Menor Zipf frequency (palavra mais difícil)
    unknown_ratio: float      # Proporção de palavras desconhecidas
    word_count: int           # Número de palavras
    avg_word_length: float    # Comprimento médio das palavras
    cefr_level: CEFRLevel     # Nível CEFR estimado
    
    @property
    def composite_score(self) -> float:
        """
        Score composto que considera múltiplos fatores.
        Quanto maior, mais fácil a sentença.
        """
        # Penalizar por palavras desconhecidas
        unknown_penalty = self.unknown_ratio * 2
        
        # Penalizar por palavras longas (média > 7 caracteres)
        length_penalty = max(0, (self.avg_word_length - 7) * 0.2)
        
        # Score base é a média de Zipf
        score = self.avg_zipf - unknown_penalty - length_penalty
        
        return max(0, score)


class DifficultyAnalyzer:
    """Analisador de dificuldade de texto baseado em frequência de palavras"""
    
    # Thresholds CEFR baseados em Zipf frequency
    # Ajustados empiricamente para refletir níveis de proficiência
    CEFR_THRESHOLDS = {
        CEFRLevel.A1: 6.0,      # Palavras muito comuns (top ~1000)
        CEFRLevel.A2: 5.5,      # Palavras comuns (top ~3000)
        CEFRLevel.B1: 5.0,      # Palavras frequentes (top ~10000)
        CEFRLevel.B2: 4.5,      # Vocabulário intermediário
        CEFRLevel.C1: 4.0,      # Vocabulário avançado
        CEFRLevel.C2_PLUS: 0.0, # Vocabulário raro/especializado
    }
    
    # Palavras funcionais que não devem influenciar muito a dificuldade
    FUNCTION_WORDS = {
        'en': {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
               'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 
               'would', 'could', 'should', 'may', 'might', 'must', 'shall',
               'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
               'as', 'into', 'through', 'during', 'before', 'after', 'above',
               'below', 'between', 'under', 'again', 'further', 'then', 'once',
               'and', 'but', 'or', 'nor', 'so', 'yet', 'both', 'either',
               'neither', 'not', 'only', 'own', 'same', 'than', 'too', 'very',
               'just', 'also', 'now', 'here', 'there', 'when', 'where', 'why',
               'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
               'other', 'some', 'such', 'no', 'any', 'i', 'me', 'my', 'myself',
               'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
               'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she',
               'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them',
               'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom',
               'this', 'that', 'these', 'those', 'am', "'s", "'re", "'ve", "'ll",
               "'d", "'m", "n't"},
        'pt': {'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'de', 'da',
               'do', 'das', 'dos', 'em', 'na', 'no', 'nas', 'nos', 'por',
               'para', 'com', 'sem', 'sob', 'sobre', 'entre', 'até', 'desde',
               'e', 'ou', 'mas', 'porém', 'contudo', 'todavia', 'entretanto',
               'que', 'se', 'como', 'quando', 'onde', 'porque', 'pois',
               'eu', 'tu', 'ele', 'ela', 'nós', 'vós', 'eles', 'elas',
               'me', 'te', 'se', 'nos', 'vos', 'lhe', 'lhes', 'meu', 'teu',
               'seu', 'nosso', 'vosso', 'minha', 'tua', 'sua', 'nossa', 'vossa',
               'este', 'esse', 'aquele', 'esta', 'essa', 'aquela', 'isto',
               'isso', 'aquilo', 'ser', 'estar', 'ter', 'haver', 'ir', 'vir',
               'fazer', 'poder', 'querer', 'dever', 'saber', 'ver', 'dar'},
        'es': {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de',
               'del', 'al', 'en', 'por', 'para', 'con', 'sin', 'sobre',
               'entre', 'hasta', 'desde', 'y', 'o', 'pero', 'sino', 'que',
               'si', 'como', 'cuando', 'donde', 'porque', 'pues', 'yo', 'tú',
               'él', 'ella', 'nosotros', 'vosotros', 'ellos', 'ellas', 'me',
               'te', 'se', 'nos', 'os', 'le', 'les', 'mi', 'tu', 'su',
               'nuestro', 'vuestro', 'este', 'ese', 'aquel', 'esta', 'esa',
               'aquella', 'esto', 'eso', 'aquello', 'ser', 'estar', 'tener',
               'haber', 'ir', 'hacer', 'poder', 'querer', 'deber', 'saber'},
        'fr': {'le', 'la', 'les', 'un', 'une', 'des', 'de', 'du', 'à', 'au',
               'aux', 'en', 'par', 'pour', 'avec', 'sans', 'sur', 'sous',
               'entre', 'vers', 'chez', 'et', 'ou', 'mais', 'donc', 'or',
               'ni', 'car', 'que', 'qui', 'quoi', 'dont', 'où', 'si', 'comme',
               'quand', 'parce', 'je', 'tu', 'il', 'elle', 'nous', 'vous',
               'ils', 'elles', 'me', 'te', 'se', 'lui', 'leur', 'mon', 'ton',
               'son', 'notre', 'votre', 'ma', 'ta', 'sa', 'mes', 'tes', 'ses',
               'ce', 'cette', 'ces', 'cet', 'être', 'avoir', 'faire', 'aller',
               'pouvoir', 'vouloir', 'devoir', 'savoir', 'voir', 'venir'},
        'de': {'der', 'die', 'das', 'ein', 'eine', 'einer', 'eines', 'einem',
               'einen', 'von', 'zu', 'zum', 'zur', 'in', 'im', 'an', 'am',
               'auf', 'für', 'mit', 'bei', 'nach', 'aus', 'über', 'unter',
               'zwischen', 'durch', 'gegen', 'ohne', 'um', 'und', 'oder',
               'aber', 'denn', 'weil', 'wenn', 'als', 'dass', 'ob', 'wie',
               'wo', 'wer', 'was', 'ich', 'du', 'er', 'sie', 'es', 'wir',
               'ihr', 'mich', 'dich', 'sich', 'uns', 'euch', 'ihm', 'ihr',
               'ihnen', 'mein', 'dein', 'sein', 'unser', 'euer', 'dieser',
               'diese', 'dieses', 'jener', 'jene', 'jenes', 'sein', 'haben',
               'werden', 'können', 'müssen', 'sollen', 'wollen', 'dürfen'},
    }
    
    def __init__(self, language: str = "en", 
                 custom_thresholds: Optional[Dict[CEFRLevel, float]] = None):
        """
        Inicializa o analisador.
        
        Args:
            language: Código ISO do idioma (ex: "en", "pt")
            custom_thresholds: Thresholds personalizados para CEFR
        """
        self.language = language[:2].lower()  # Normalizar para 2 caracteres
        
        if custom_thresholds:
            self.thresholds = custom_thresholds
        else:
            self.thresholds = self.CEFR_THRESHOLDS.copy()
        
        # Obter palavras funcionais para o idioma
        self.function_words = self.FUNCTION_WORDS.get(self.language, set())
    
    def analyze_sentence(self, sentence: Sentence) -> DifficultyScore:
        """
        Analisa a dificuldade de uma sentença.
        
        Args:
            sentence: Sentença a analisar
            
        Returns:
            DifficultyScore com métricas de dificuldade
        """
        # Extrair palavras (apenas alfabéticas)
        words = self._extract_words(sentence.text)
        
        if not words:
            # Retornar score padrão para sentenças sem palavras válidas
            return DifficultyScore(
                avg_zipf=6.0,
                min_zipf=6.0,
                unknown_ratio=0.0,
                word_count=0,
                avg_word_length=0.0,
                cefr_level=CEFRLevel.A1
            )
        
        # Calcular frequências Zipf
        zipf_scores = []
        unknown_count = 0
        content_words = []  # Palavras de conteúdo (não funcionais)
        
        for word in words:
            word_lower = word.lower()
            
            # Obter frequência Zipf
            zipf = zipf_frequency(word_lower, self.language)
            
            if zipf == 0:
                # Palavra desconhecida
                unknown_count += 1
                # Usar um valor baixo para palavras desconhecidas
                zipf = 2.0
            
            zipf_scores.append(zipf)
            
            # Separar palavras de conteúdo
            if word_lower not in self.function_words:
                content_words.append((word, zipf))
        
        # Calcular métricas
        avg_zipf = sum(zipf_scores) / len(zipf_scores)
        min_zipf = min(zipf_scores)
        unknown_ratio = unknown_count / len(words)
        avg_word_length = sum(len(w) for w in words) / len(words)
        
        # Se temos palavras de conteúdo, usar a média delas
        # (palavras funcionais são sempre comuns e não indicam dificuldade)
        if content_words:
            content_avg = sum(z for _, z in content_words) / len(content_words)
            content_min = min(z for _, z in content_words)
            # Ponderar: 70% palavras de conteúdo, 30% todas
            avg_zipf = content_avg * 0.7 + avg_zipf * 0.3
            min_zipf = min(content_min, min_zipf)
        
        # Classificar nível CEFR
        cefr_level = self._classify_cefr(avg_zipf, min_zipf, unknown_ratio)
        
        return DifficultyScore(
            avg_zipf=avg_zipf,
            min_zipf=min_zipf,
            unknown_ratio=unknown_ratio,
            word_count=len(words),
            avg_word_length=avg_word_length,
            cefr_level=cefr_level
        )
    
    def _extract_words(self, text: str) -> List[str]:
        """
        Extrai palavras de um texto.
        
        Args:
            text: Texto para extrair palavras
            
        Returns:
            Lista de palavras
        """
        # Remover pontuação e manter apenas palavras alfabéticas
        words = re.findall(r"\b[a-zA-ZÀ-ÿ]+(?:'[a-zA-Z]+)?\b", text)
        # Filtrar palavras muito curtas (1-2 caracteres) exceto pronomes comuns
        return [w for w in words if len(w) > 2 or w.lower() in {'i', 'a', 'o'}]
    
    def _classify_cefr(self, avg_zipf: float, min_zipf: float, 
                       unknown_ratio: float) -> CEFRLevel:
        """
        Classifica o nível CEFR baseado nas métricas.
        
        Args:
            avg_zipf: Média de Zipf frequency
            min_zipf: Mínimo de Zipf frequency
            unknown_ratio: Proporção de palavras desconhecidas
            
        Returns:
            CEFRLevel correspondente
        """
        # Penalizar por palavras desconhecidas
        # Muitas palavras desconhecidas = texto mais difícil
        effective_zipf = avg_zipf - (unknown_ratio * 1.5)
        
        # Também considerar a palavra mais difícil
        # Se há palavras muito raras, o texto é mais difícil
        if min_zipf < 3.0:
            effective_zipf = min(effective_zipf, avg_zipf - 0.5)
        
        # Classificar baseado nos thresholds
        for level in [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, 
                      CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2_PLUS]:
            threshold = self.thresholds[level]
            if effective_zipf >= threshold:
                return level
        
        return CEFRLevel.C2_PLUS
    
    def should_translate(self, sentence: Sentence, user_level: CEFRLevel) -> bool:
        """
        Determina se uma sentença deve ser traduzida baseado no nível do usuário.
        
        Lógica: Traduzir sentenças FÁCEIS (nível <= usuário)
        Manter no original sentenças DIFÍCEIS (nível > usuário)
        
        Isso força o usuário a ler no idioma original as partes desafiadoras,
        enquanto recebe suporte nas partes mais fáceis.
        
        Args:
            sentence: Sentença analisada
            user_level: Nível CEFR do usuário
            
        Returns:
            True se a sentença deve ser traduzida
        """
        if sentence.cefr_level is None:
            return False
        
        # Traduzir se o nível da sentença é igual ou menor que o do usuário
        return sentence.cefr_level <= user_level
    
    def analyze_structure(self, structure: EpubStructure, 
                          user_level: CEFRLevel,
                          progress_callback=None) -> Dict[str, any]:
        """
        Analisa toda a estrutura do EPUB e marca sentenças para tradução.
        
        Args:
            structure: Estrutura do EPUB parseada
            user_level: Nível CEFR do usuário
            progress_callback: Função callback para progresso (opcional)
            
        Returns:
            Dicionário com estatísticas da análise
        """
        stats = {
            'total_sentences': 0,
            'sentences_to_translate': 0,
            'cefr_distribution': {level.name: 0 for level in CEFRLevel},
            'avg_difficulty': 0.0,
        }
        
        all_sentences = structure.get_all_sentences()
        total = len(all_sentences)
        total_zipf = 0.0
        
        for i, sentence in enumerate(all_sentences):
            # Analisar dificuldade
            score = self.analyze_sentence(sentence)
            
            # Atualizar sentença
            sentence.difficulty_score = score.avg_zipf
            sentence.cefr_level = score.cefr_level
            sentence.should_translate = self.should_translate(sentence, user_level)
            
            # Atualizar estatísticas
            stats['total_sentences'] += 1
            stats['cefr_distribution'][score.cefr_level.name] += 1
            total_zipf += score.avg_zipf
            
            if sentence.should_translate:
                stats['sentences_to_translate'] += 1
            
            # Callback de progresso
            if progress_callback and i % 100 == 0:
                progress_callback(i / total)
        
        if total > 0:
            stats['avg_difficulty'] = total_zipf / total
        
        # Calcular porcentagem de tradução
        stats['translation_percentage'] = (
            stats['sentences_to_translate'] / stats['total_sentences'] * 100
            if stats['total_sentences'] > 0 else 0
        )
        
        return stats


def analyze_difficulty(structure: EpubStructure, 
                       user_level: CEFRLevel,
                       language: str = "en",
                       progress_callback=None) -> Dict[str, any]:
    """
    Função de conveniência para análise de dificuldade.
    
    Args:
        structure: Estrutura do EPUB parseada
        user_level: Nível CEFR do usuário (ou string como "B1")
        language: Código ISO do idioma
        progress_callback: Função callback para progresso
        
    Returns:
        Dicionário com estatísticas da análise
    """
    # Converter string para CEFRLevel se necessário
    if isinstance(user_level, str):
        user_level = CEFRLevel.from_string(user_level)
    
    analyzer = DifficultyAnalyzer(language=language)
    return analyzer.analyze_structure(structure, user_level, progress_callback)


def get_sentence_difficulty(text: str, language: str = "en") -> DifficultyScore:
    """
    Analisa a dificuldade de uma única sentença/texto.
    
    Args:
        text: Texto a analisar
        language: Código ISO do idioma
        
    Returns:
        DifficultyScore com métricas
    """
    analyzer = DifficultyAnalyzer(language=language)
    sentence = Sentence(text=text, index=0, paragraph_index=0, chapter_index=0)
    return analyzer.analyze_sentence(sentence)
