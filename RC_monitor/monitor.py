import requests
from bs4 import BeautifulSoup
import urllib3
from dotenv import load_dotenv
import os
import time
from datetime import datetime

def parse_cookies_from_browser(cookie_string):
    """Парсим куки из строки браузера"""
    cookies = {}
    
    # Разделяем по точке с запятой
    cookie_parts = cookie_string.split(';')
    
    # Первая часть - это сама кука name=value
    if cookie_parts and '=' in cookie_parts[0]:
        name, value = cookie_parts[0].strip().split('=', 1)
        cookies[name] = value
    
    # Ищем другие куки в оставшихся частях
    for part in cookie_parts[1:]:
        part = part.strip()
        if '=' in part:
            name, value = part.split('=', 1)
            # Добавляем только если это не атрибуты (Expires, Path, HttpOnly и т.д.)
            if name.lower() not in ['expires', 'path', 'domain', 'httponly', 'secure', 'samesite']:
                cookies[name] = value
    
    return cookies

def get_detectors_status(ip, session):
    """Получаем статус детекторов"""
    try:
        response = session.get(f"https://{ip}/detectors/status", verify=False, timeout=5)
        
        if response.status_code == 200 and "Авторизация" not in response.text:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Находим таблицу с детекторами
            detectors_table = soup.find('tbody', {'id': 'table_detectors'})
            if not detectors_table:
                return None
            
            detectors = []
            rows = detectors_table.find_all('tr')
            
            for row in rows:
                # Извлекаем данные из строки таблицы
                cells = row.find_all('td')
                if len(cells) >= 5:
                    # Номер детектора
                    det_number = cells[0].get_text(strip=True)
                    # Номер входа
                    input_number = cells[1].get_text(strip=True)
                    # Тип детектора
                    det_type = cells[2].get_text(strip=True)
                    # Статус
                    status_span = cells[3].find('span', {'id': 'det_status'})
                    status = status_span.get_text(strip=True) if status_span else "N/A"
                    # Класс статуса (определяет цвет)
                    status_class = status_span.get('class', []) if status_span else []
                    
                    # Режим установки
                    state_select = cells[4].find('select', {'name': 'state[]'})
                    state_text = "N/A"
                    if state_select:
                        selected_option = state_select.find('option', selected=True)
                        if selected_option:
                            state_text = selected_option.get_text(strip=True)
                    
                    detectors.append({
                        'number': det_number,
                        'input': input_number,
                        'type': det_type,
                        'status': status,
                        'status_class': status_class,
                        'state': state_text
                    })
            
            return detectors
        else:
            return None
            
    except Exception as e:
        print(f"Ошибка получения статуса: {e}")
        return None

def write_to_log(message):
    """Запись сообщения в лог-файл"""
    log_entry = f"{message}\n"
    
    # Создаем папку для логов если ее нет
    log_dir = "logs_https"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Имя файла с датой
    log_filename = f"{log_dir}/detectors_log_{datetime.now().strftime('%Y%m%d')}.txt"
    
    # Записываем в файл
    with open(log_filename, "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)

def format_detectors_for_log(detectors):
    """Форматируем данные детекторов для лога в формате DT X = EMOJI STATUS"""
    if not detectors:
        return "Нет данных"
    
    # Сортируем детекторы по номеру
    sorted_detectors = sorted(detectors, key=lambda x: int(x['number']))
    
    log_entries = []
    for det in sorted_detectors:
        # Определяем эмодзи статуса
        if det['status'] == '1':
            status_emoji = "🟢"
        elif det['status'] == '0':
            status_emoji = "⚪"
        else:
            status_emoji = "❓"
        
        log_entries.append(f"DT {det['number']} = {status_emoji} {det['status']}")
    
    return " , ".join(log_entries)

def monitor_detectors(ip):
    """Мониторинг детекторов - следующий запрос сразу после получения ответа"""
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    session = requests.Session()
    
    # Получаем куки из .env файла
    browser_cookies = os.getenv('BROWSER_COOKIES')
    if not browser_cookies:
        print("❌ BROWSER_COOKIES не найдены в .env файле")
        write_to_log("❌ BROWSER_COOKIES не найдены в .env файле")
        return
    
    stolen_cookies = parse_cookies_from_browser(browser_cookies)
    
    for name, value in stolen_cookies.items():
        session.cookies.set(name, value)
    
    # Заголовки как в браузере
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    })
    
    print("🚦 МОНИТОРИНГ ДЕТЕКТОРОВ (непрерывный режим)")
    print("=" * 60)
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            
            # Фиксируем время начала запроса
            request_time = datetime.now()
            request_timestamp = request_time.strftime("%H:%M:%S.%f")[:-3]
            
            detectors = get_detectors_status(ip, session)
            
            # Фиксируем время получения ответа
            response_time = datetime.now()
            response_timestamp = response_time.strftime("%H:%M:%S.%f")[:-3]
            
            # Вычисляем время выполнения запроса в миллисекундах
            request_duration_ms = (response_time - request_time).total_seconds() * 1000
            
            if detectors:
                print(f"\n[{request_timestamp}] Запрос #{iteration}")
                print(f"[{response_timestamp}] Ответ #{iteration} - Время: {request_duration_ms:.0f} мс")
                print(f"Найдено детекторов: {len(detectors)}")
                print("-" * 60)
                
                # Выводим детекторы в терминал в старом формате
                for det in detectors:
                    # Определяем эмодзи статуса
                    if det['status'] == '1':
                        status_emoji = "🟢"
                    elif det['status'] == '0':
                        status_emoji = "⚪"
                    else:
                        status_emoji = "❓"
                    
                    print(f"Детектор {det['number']:>3} | Вход {det['input']:>2} | Статус: {status_emoji} {det['status']}")
                
                # Форматируем для лога в новом формате
                log_message = f"Запрос: {request_timestamp}, Ответ: {response_timestamp}, Время: {request_duration_ms:.0f} мс - {format_detectors_for_log(detectors)}"
                write_to_log(log_message)
                
            else:
                print(f"\n[{request_timestamp}] Запрос #{iteration}")
                print(f"[{response_timestamp}] Ответ #{iteration} - Время: {request_duration_ms:.0f} мс")
                print("❌ Не удалось получить данные детекторов")
                log_message = f"Запрос: {request_timestamp}, Ответ: {response_timestamp}, Время: {request_duration_ms:.0f} мс - ❌ Не удалось получить данные детекторов"
                write_to_log(log_message)
            
            # Следующий запрос отправляется сразу после получения ответа
            # Нет задержки между запросами
            
    except KeyboardInterrupt:
        print("\n⏹️ Мониторинг остановлен")
        write_to_log("⏹️ Мониторинг остановлен")

if __name__ == "__main__":
    load_dotenv()
    ip = os.getenv('IP')
    
    if not ip:
        print("❌ IP не найден в .env файле")
        exit(1)
    
    print("🔍 Запуск мониторинга детекторов (непрерывный режим)...")
    monitor_detectors(ip)
