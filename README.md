# BusDetection

Архитектура разделена на **два независимых процесса**, которые пишут в **одну SQLite БД**:

1. **Монитор веб-интерфейса** (`RC_monitor/monitor.py`) — опрашивает контроллер и сохраняет состояния петлевых детекторов.
2. **Детектор** (`Detector/detector.py`) — читает RTSP поток, определяет автобус, сохраняет результат и кадр.

Оба процесса используют общий модуль БД: `Common/storage.py`.

## Переменные окружения

Создайте `.env`:

```dotenv
# Общие
DB_PATH=data/detections.sqlite3

# Loop monitor
CONTROLLER_HOST=192.168.1.10
BROWSER_COOKIES=PHPSESSID=...; other_cookie=...
LOOP_POLL_INTERVAL_SEC=1

# Bus detector
RTSP_URL=rtsp://user:password@camera_ip:554/stream
MODEL_PATH=Model/best_effnet_b0.pth
IMAGES_DIR=data/images
POLL_INTERVAL_SEC=2
BUS_CONFIDENCE_THRESHOLD=0.5
```

## Запуск компонентов

В двух разных терминалах (или через systemd/docker-compose):

```bash
python RC_monitor/monitor.py
python Detector/detector.py
```

## Схема БД

### `loop_events`
- `ts_utc` — время опроса.
- `source_host` — адрес контроллера.
- `active_count` — число активных петель.
- `values_json` — JSON со статусами всех детекторов.

### `bus_events`
- `ts_utc` — время детекции.
- `bus_detected` — бинарный результат модели (`0/1`).
- `confidence` — уверенность модели.
- `image_path` — путь к сохраненному кадру.
- `meta_json` — технические параметры (например, порог).

## Важно по модели

`Detector/detector.py` ожидает, что `torch.load(MODEL_PATH)` возвращает `nn.Module`.
Если у вас хранится `state_dict`, адаптируйте загрузку в `BusPredictor`.
