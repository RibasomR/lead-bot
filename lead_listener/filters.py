"""
## Фильтры для обнаружения лидов
Содержит логику фильтрации сообщений по ключевым словам, языку и стеку технологий.
"""

import re
from typing import List, Optional, Set
from loguru import logger

from config import settings


## Класс для фильтрации и анализа сообщений
class LeadFilter:
    """
    Фильтрует сообщения по ключевым словам и извлекает метаданные.
    """
    
    # Регулярки для определения языка
    CYRILLIC_PATTERN = re.compile(r'[а-яА-ЯёЁ]')
    LATIN_PATTERN = re.compile(r'[a-zA-Z]')
    
    # Стек технологий для распознавания
    TECH_STACK = {
        # Языки программирования
        'python', 'javascript', 'typescript', 'java', 'kotlin', 'swift',
        'go', 'golang', 'rust', 'php', 'ruby', 'c#', 'c++',
        
        # Фреймворки и библиотеки
        'django', 'flask', 'fastapi', 'react', 'vue', 'angular', 'next.js',
        'nextjs', 'nuxt', 'svelte', 'express', 'nest.js', 'nestjs',
        
        # Telegram боты
        'aiogram', 'python-telegram-bot', 'telethon', 'pyrogram',
        'telegraf', 'grammy', 'node-telegram-bot-api',
        
        # Базы данных
        'postgresql', 'postgres', 'mysql', 'mongodb', 'redis', 'sqlite',
        'clickhouse', 'elasticsearch',
        
        # Блокчейн и крипта
        'ethereum', 'bitcoin', 'solana', 'web3', 'blockchain', 'nft',
        'smart contract', 'defi', 'trading', 'binance', 'bybit',
        
        # Облачные сервисы
        'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'vercel', 'heroku',
        
        # Другие технологии
        'api', 'rest', 'graphql', 'websocket', 'grpc', 'microservices',
        'machine learning', 'ml', 'ai', 'neural network',
    }
    
    def __init__(self):
        # Загружаем ключевые слова из конфига
        self.keywords = self._load_keywords()
        logger.info(f"📋 Загружено {len(self.keywords)} ключевых слов для фильтрации")
        
    def _load_keywords(self) -> Set[str]:
        """
        Загрузить ключевые слова из конфигурации.
        
        Returns:
            Множество ключевых слов в lowercase
        """
        keywords = set()
        
        for keyword in settings.keywords_list:
            # Добавляем само ключевое слово
            keywords.add(keyword.lower())
            
            # Добавляем варианты без пробелов (например, "телеграм бот" -> "телеграмбот")
            if ' ' in keyword:
                keywords.add(keyword.lower().replace(' ', ''))
                
        return keywords
        
    def matches_keywords(self, text: str) -> bool:
        """
        Проверить, содержит ли текст ключевые слова.
        
        Args:
            text: Текст сообщения
            
        Returns:
            True если найдено хотя бы одно ключевое слово
        """
        if not text:
            return False
            
        text_lower = text.lower()
        
        for keyword in self.keywords:
            if keyword in text_lower:
                logger.debug(f"✅ Найдено ключевое слово: '{keyword}'")
                return True
                
        return False
        
    def detect_language(self, text: str) -> str:
        """
        Определить язык текста (ru/en/other).
        
        Args:
            text: Текст для анализа
            
        Returns:
            Код языка: 'ru', 'en', 'other'
        """
        if not text:
            return 'other'
            
        # Подсчёт символов
        cyrillic_count = len(self.CYRILLIC_PATTERN.findall(text))
        latin_count = len(self.LATIN_PATTERN.findall(text))
        
        total_letters = cyrillic_count + latin_count
        
        if total_letters == 0:
            return 'other'
            
        # Определяем преобладающий язык
        cyrillic_ratio = cyrillic_count / total_letters
        
        if cyrillic_ratio > 0.5:
            return 'ru'
        elif latin_count > cyrillic_count:
            return 'en'
        else:
            return 'other'
            
    def extract_stack(self, text: str) -> Optional[str]:
        """
        Извлечь упоминания технологий из текста.
        
        Args:
            text: Текст для анализа
            
        Returns:
            Строка с технологиями через запятую или None
        """
        if not text:
            return None
            
        text_lower = text.lower()
        found_technologies = set()
        
        for tech in self.TECH_STACK:
            # Ищем целые слова (с границами слов)
            pattern = r'\b' + re.escape(tech) + r'\b'
            if re.search(pattern, text_lower):
                found_technologies.add(tech)
                
        if found_technologies:
            # Сортируем для консистентности
            return ', '.join(sorted(found_technologies))
            
        return None
        
    def is_spam(self, text: str) -> bool:
        """
        Проверить, является ли сообщение спамом.
        На данный момент заглушка, но архитектура позволяет расширить.
        
        Args:
            text: Текст для проверки
            
        Returns:
            True если сообщение похоже на спам
        """
        # TODO: Реализовать более сложную логику определения спама
        # Например:
        # - Слишком много эмодзи
        # - Слишком много заглавных букв
        # - Подозрительные ссылки
        # - Повторяющиеся фразы
        
        return False
        
    def should_ignore_sender(self, sender_username: Optional[str]) -> bool:
        """
        Проверить, нужно ли игнорировать отправителя.
        
        Args:
            sender_username: Username отправителя
            
        Returns:
            True если отправителя нужно игнорировать
        """
        if not sender_username:
            return False
            
        # Игнорируем ботов (заканчиваются на 'bot')
        if sender_username.lower().endswith('bot'):
            return True
            
        # TODO: Можно добавить чёрный список пользователей
        
        return False

