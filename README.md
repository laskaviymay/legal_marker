# Legal Marker

Локальный инструмент для редакции СМИ: принимает текст, ищет в нем упоминания сущностей из юридически значимых реестров, добавляет маркировки и формирует блок пояснений.

## Что умеет

- маркировать текст по реестрам:
  - иноагенты;
  - террористы и экстремисты;
  - нежелательные организации;
  - экстремистские материалы;
- поддерживать ручные алиасы и словоформы;
- обновлять рабочую базу из файлов;
- экспортировать базу в `zip`-bundle для GitHub и Telegram-бота;
- запускаться как Windows-приложение и как Telegram-бот на одном и том же matcher-ядре.

## Установка

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

## Обновление локальной базы

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py --update
```

Пути к исходникам можно переопределить:

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py --update `
  --foreign-agents C:\path\export.xlsx `
  --undesirable "C:\path\export (1).xlsx" `
  --rosfinmonitoring "C:\path\РОСФИНМОНИТОРИНГ.docx" `
  --extremist-materials C:\path\exportfsm.docx
```

## Проверка текста через CLI

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py --text "Мария Певчих дала комментарий."
```

Или из файла:

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py --input article.txt
```

## Экспорт базы для GitHub и Telegram-бота

Собрать bundle:

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py `
  --export-db .\dist\legal-marker-db.zip `
  --db-version 2026-04-23.1
```

В архив попадают:

- `agents.json`
- `aliases.json`
- `forms.json`
- `sources.json`
- `manifest.json`

## Telegram-бот

### Переменные окружения

```text
TELEGRAM_BOT_TOKEN=...
LEGAL_MARKER_DB_URL=https://github.com/<owner>/<repo>/releases/latest/download/legal-marker-db.zip
LEGAL_MARKER_DB_DIR=.\bot_runtime\db
LEGAL_MARKER_ADMIN_IDS=123456789
LEGAL_MARKER_POLL_TIMEOUT=20
```

### Запуск

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run_telegram_bot.py
```

### Команды бота

- `/start`
- `/help`
- `/version`
- `/db_version`
- `/update_db`

Команда `/update_db` доступна только `chat_id`, перечисленным в `LEGAL_MARKER_ADMIN_IDS`.

## Windows GUI

Обычный запуск:

```text
C:\Users\Nikita\Desktop\LegalMarker.exe
```

Если нужен запуск из исходников:

```text
run_gui.bat
```

## Тесты

```powershell
& "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests
```
