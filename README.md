# AgentMemory для Codex на Windows

Приватная, полностью переносимая сборка рабочего AgentMemory. Репозиторий содержит:

- безопасный полный экспорт памяти `memory-export.json`;
- автоматические backup и restore через штатный AgentMemory API;
- Codex-плагин с шестью хуками автоматической записи;
- доработку дашборда `http://localhost:3113`, где можно проверить и сохранить ключ OpenRouter;
- установщик AgentMemory 0.9.29 и iii-engine 0.11.2 для Windows x64;
- полный исходный код AutoDev Orchestrator из `G:\agentmemory` в `source/autodev-orchestrator`.

Репозиторий должен оставаться **приватным**: экспорт памяти содержит личную историю запросов и работы. Секреты сюда не записываются. `.env`, API-ключи, GitHub-токены, логи, PID-файлы, бинарники и живые базы исключены.

## Быстрая установка на Windows

Требования:

- Windows 10/11 x64;
- Node.js 20 или новее;
- Git;
- Codex CLI, если нужна автоматическая память в Codex;
- GitHub CLI `gh`, авторизованный в аккаунте с доступом к этому приватному репозиторию.

Откройте PowerShell и выполните:

```powershell
gh auth login
git clone https://github.com/coolmorimer/agentmemory-backup.git
Set-Location agentmemory-backup
Set-ExecutionPolicy -Scope Process Bypass
.\installer\Install-AgentMemory.ps1
```

Установщик:

1. Установит `@agentmemory/agentmemory@0.9.29` через npm.
2. Загрузит iii-engine 0.11.2 и проверит SHA-256 архива.
3. Установит доработанный дашборд OpenRouter.
4. Добавит AgentMemory в автозагрузку Windows.
5. Установит локальный Codex-плагин.
6. Доверит только шесть хуков AgentMemory из этого репозитория.
7. Запустит сервис и дождётся состояния `healthy`.

Если Codex-плагин на этом ПК не нужен:

```powershell
.\installer\Install-AgentMemory.ps1 -SkipCodexPlugin
```

Если не нужна автозагрузка Windows:

```powershell
.\installer\Install-AgentMemory.ps1 -SkipAutostart
```

После установки откройте [http://localhost:3113](http://localhost:3113). В верхнем блоке **«Настройки OpenRouter · только бесплатно»** вставьте свой ключ OpenRouter и нажмите **«Проверить и сохранить»**.

Ключ:

- проверяется запросом к OpenRouter перед сохранением;
- хранится только в `%USERPROFILE%\.agentmemory\.env`;
- не возвращается браузеру после сохранения;
- не входит в экспорт памяти и Git.

Сборка жёстко использует `openrouter/free`. Платный резервный маршрут не настроен. Доступность и лимиты бесплатных моделей зависят от OpenRouter.

Перезапустите открытые окна Codex и VS Code после первой установки, чтобы они загрузили плагин и хуки.

## Восстановление памяти

Сначала установите и запустите AgentMemory, затем в каталоге репозитория выполните:

```powershell
.\Restore-Memory.ps1
```

Или дважды щёлкните `restore.cmd`.

По умолчанию используется стратегия `merge`: данные из репозитория добавляются к локальной памяти без очистки уже существующих записей. После импорта скрипт проверяет, что поиск отвечает.

Чтобы сначала не выполнять `git pull`:

```powershell
.\Restore-Memory.ps1 -NoPull
```

Режим `replace` полностью заменяет локальные данные экспортом и поэтому используется только явно:

```powershell
.\Restore-Memory.ps1 -Strategy replace
```

## Резервное копирование памяти

Запустите:

```powershell
.\Backup-Memory.ps1
```

Или дважды щёлкните `backup.cmd`.

Скрипт:

1. Проверит здоровье AgentMemory на `http://localhost:3111`.
2. Получит полный экспорт через `/agentmemory/export`.
3. Удалит динамическое поле `exportedAt`, чтобы не создавать пустые коммиты.
4. Заблокирует отправку, если найдёт похожий на секрет ключ, пароль или приватный ключ.
5. Закоммитит только `memory-export.json` и `backup-meta.json`.
6. Отправит коммит в `origin/main`.

Экспорт включает сеансы, наблюдения, воспоминания, сводки, уроки и граф связей. Живая runtime-база напрямую не копируется.

Для локального экспорта без отправки в GitHub:

```powershell
.\Backup-Memory.ps1 -NoPush
```

## Почасовой автоматический backup

```powershell
.\Install-AutoBackup.ps1
```

Скрипт создаёт задачу Windows `AgentMemory GitHub Backup`. Она запускается каждый час, пока пользователь вошёл в Windows. Если память не изменилась, новый коммит не создаётся.

Проверить задачу:

```powershell
Get-ScheduledTask -TaskName 'AgentMemory GitHub Backup'
Get-ScheduledTaskInfo -TaskName 'AgentMemory GitHub Backup'
```

## Ручной запуск и проверка

Запуск:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.agentmemory\start-agentmemory.ps1"
```

Проверка API:

```powershell
Invoke-RestMethod http://localhost:3111/agentmemory/health
Invoke-RestMethod http://localhost:3111/agentmemory/config/flags
```

Адреса:

| Назначение | Адрес |
|---|---|
| REST API | `http://localhost:3111` |
| Поток событий | `ws://localhost:3112` |
| Дашборд | `http://localhost:3113` |
| iii-engine | `ws://localhost:49134` |

## Обновление установки

Получите изменения и повторно запустите установщик:

```powershell
git pull --ff-only
.\installer\Install-AgentMemory.ps1
```

Повторный запуск безопасен: он обновляет закреплённую npm-версию, повторно применяет доработку дашборда, обновляет плагин и проверяет сервис. После обновления npm-пакета доработка дашборда должна применяться повторно.

## Структура репозитория

```text
.agents/plugins/marketplace.json   локальный marketplace Codex
dashboard/                         форма настройки OpenRouter и перезапуск
installer/                         установка, патч дашборда, доверие к хукам
tests/                             проверки безопасного сохранения OpenRouter
source/codex-plugin/               полный AgentMemory-плагин для Codex
source/autodev-orchestrator/       полный исходный код AutoDev Orchestrator
Backup-Memory.ps1                  безопасный экспорт и push
Restore-Memory.ps1                 pull и импорт памяти
Install-AutoBackup.ps1             почасовая задача Windows
memory-export.json                 переносимый экспорт памяти
backup-meta.json                   версия и счётчики последнего backup
```

## Устранение проблем

Проверить установку:

```powershell
agentmemory status
agentmemory doctor
Get-Content "$env:USERPROFILE\.agentmemory\daemon.log" -Tail 100
```

Если дашборд не открывается, убедитесь, что порт 3111 отвечает, и перезапустите сервис повторным запуском установщика.

Если Codex видит инструменты AgentMemory, но новые сеансы не появляются, проверьте хуки командой `/hooks`. Все шесть хуков `agentmemory@agentmemory-backup` должны иметь статус `trusted`. Установщик делает это автоматически.

Если граф пуст, проверьте `http://localhost:3111/agentmemory/config/flags`: провайдер не должен быть `noop`, а `GRAPH_EXTRACTION_ENABLED` должен быть включён. Граф наполняется при обработке новых записей; старые данные можно перестроить кнопкой в разделе «Граф».

Бесплатный OpenRouter может временно отвечать ошибкой лимита или недоступности модели. Это не отключает основную запись сеансов: AgentMemory продолжает сохранять наблюдения в локальном режиме.

## Безопасность

- Никогда не добавляйте `%USERPROFILE%\.agentmemory\.env` в Git.
- Не вставляйте API-ключи в README, issue, commit message или команды терминала, которые попадут в историю.
- Перед каждым backup выполняется проверка экспорта на типичные форматы секретов.
- Репозиторий содержит историю работы и должен оставаться приватным.
- При переносе памяти используйте штатные `/agentmemory/export` и `/agentmemory/import`, а не копирование работающей базы iii-engine.

Перед ручным коммитом исходников запустите общую проверку репозитория:

```powershell
.\Test-NoSecrets.ps1
```

AgentMemory — проект Rohit Ghumare, лицензия Apache-2.0. Эта сборка фиксирует совместимую версию и добавляет Windows/Codex-интеграцию, backup/restore и локальный экран настройки OpenRouter.
