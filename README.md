# Аким на 5 часов

Основной интерфейс проекта — Streamlit-симулятор Astana Innovations в `astana_simulator/`. Он открывается на редакционном стартовом экране, поддерживает каталог из 14 мероприятий и дополнительный режим распределения бюджета.

## Запуск основного симулятора

Требуется Python 3.12 или новее.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Set-Location astana_simulator
python -m streamlit run streamlit_app.py
```

Откройте <http://127.0.0.1:8501>. Для расчёта бюджета и Score API-ключ не нужен. В VS Code конфигурация **Run Akim Streamlit app** запускает этот же интерфейс.

## Советник OpenAI (необязательно)

Чтобы запрашивать AI-разбор, скопируйте `astana_simulator/.env.example` в `astana_simulator/.env` и укажите там `OPENAI_API_KEY`. Ключ остаётся на сервере; не добавляйте `.env` в Git.

## Структура проекта

- `astana_simulator/streamlit_app.py` — основной интерфейс и сценарии.
- `astana_simulator/src/model.py` — расчёт Score и проверка правил.
- `astana_simulator/src/catalogue.py` — каталог мероприятий.
- `astana_simulator/assets/` — стиль стартового экрана и рабочего интерфейса.
- Корневой `app.py` и `calculator.py` сохранены как отдельный исходный вариант.

Полное описание модели и синтетического датасета — в [README симулятора](astana_simulator/README.md).
