import re
from typing import Optional, Tuple


def parse_amount_and_description(text: str) -> Optional[Tuple[float, str]]:
    """
    Парсить текст повідомлення користувача, витягуючи суму та опис.
    Приклади:
      '150 кава' -> (150.0, 'кава')
      'кава 150.50' -> (150.50, 'кава')
      '1 500 грн подарунок' -> (1500.0, 'подарунок')
      '350' -> (350.0, '')
    """
    if not text:
        return None

    cleaned_text = text.strip()

    # Заміна чисел з пробілами тисяч (наприклад: "10 000" -> "10000", але не "10 20")
    cleaned_text = re.sub(r'(\d+)\s+(\d{3})(?!\d)', r'\1\2', cleaned_text)

    # Видаляємо позначення валюти для легшого парсингу
    cleaned_text_no_currency = re.sub(r'(?i)\b(грн|uah|usd|eur|євро|\$|€)\b', '', cleaned_text)

    # Шукаємо число (ціле або дробове з крапкою чи комою)
    # Шаблон знаходить: наприклад 150, 150.50, 150,50
    match = re.search(r'(?<!\S)(\d+(?:[.,]\d+)?)(?!\S)', cleaned_text_no_currency)
    
    if not match:
        # Спробуємо знайти число, навіть якщо воно прилягає до літер, наприклад "150грн"
        match = re.search(r'(\d+(?:[.,]\d+)?)', cleaned_text)
        if not match:
            return None

    raw_amount = match.group(1).replace(',', '.')
    try:
        amount = float(raw_amount)
        if amount <= 0 or amount > 100_000_000:
            return None
    except ValueError:
        return None

    # Витягуємо опис: все, окрім знайденого числа та зайвих символів
    # Знаходимо початок та кінець входження числа в оригінальному cleaned_text
    start, end = match.span()
    description = (cleaned_text[:start] + " " + cleaned_text[end:]).strip()
    
    # Вичищаємо залишки валюти та зайві пробіли/розділові знаки
    description = re.sub(r'(?i)\b(грн|uah|usd|eur|євро|\$|€)\b', '', description)
    description = re.sub(r'^[,\-–—:\s]+|[,\-–—:\s]+$', '', description)
    description = re.sub(r'\s+', ' ', description).strip()

    return round(amount, 2), description

