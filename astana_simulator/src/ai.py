"""OpenAI urbanist report; only explicit UI actions call this module.

The deterministic calculation remains authoritative. Credentials never enter
scenario payloads, exports, session caches, logs, or exception messages.
"""

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv
from openai import (
    APIConnectionError, APIError, APIStatusError, APITimeoutError,
    AsyncOpenAI, AuthenticationError, PermissionDeniedError, RateLimitError,
)

ROOT = Path(__file__).resolve().parents[1]
OPENAI_MODEL = "gpt-4o-mini"
DEADLINE_SECONDS = 55.0


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.openai.com/v1"


@dataclass
class AIReport:
    provider: str
    model: str
    text: str = ""
    error: str = ""
    warning: str = ""
    seconds: float = 0

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error


def load_providers() -> list[Provider]:
    # Only this project's .env is loaded; deployment environment takes priority.
    load_dotenv(ROOT / ".env", override=False, interpolate=False)
    value = (os.getenv("OPENAI_API_KEY") or "").strip()
    if value.lower() in {"", "your_key_here", "replace_me", "sk-..."}:
        value = ""
    return [Provider("OpenAI", OPENAI_MODEL, value)]


COMMON_PROMPT = """Ты эксперт учебного AI-симулятора «Аким на 5 часов».
Отвечай только по-русски. Данные синтетические, это не реальные городские сведения.
Используй только переданный JSON. Итоговый Score, дельты и эффекты уже рассчитаны Python:
не пересчитывай и не придумывай числа, население, события, статистику или причинность.
Числа округляй максимум до двух знаков. Различай mode allocation (авторская непрерывная
модель) и measures (каталог кейса). Не выдавай допущения одного режима за правила другого.
Рекомендации — гипотезы, их новый Score неизвестен до нового расчета. Учитывай остаток
бюджета, критические показатели <40 и самый слабый район. Не предлагай превышать бюджет.
В режиме measures решений ровно пять: предлагай ЗАМЕНУ меры, а не шестую меру.
Не используй HTML, изображения или внешние ссылки. Не пиши ход внутренних рассуждений.
"""
URBANIST_PROMPT = """Подготовь краткий экспертный отчет урбаниста (до 400 слов).
Используй четыре раздела Markdown: «Сильные стороны», «Скрытые риски»,
«Что скорректировать», «Вердикт для акима». Объясни главные компромиссы,
включая разрыв между районами, и привяжи выводы к данным. Не называй сценарий
оптимальным без сравнения. В вердикте приведи переданный итоговый Score.
"""


async def _request(provider: Provider, payload: dict) -> tuple[str, str]:
    kwargs = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": COMMON_PROMPT + URBANIST_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "stream": False,
        "temperature": .35,
        "max_completion_tokens": 1800,
        "store": False,
    }
    async with AsyncOpenAI(
        api_key=provider.api_key, base_url=provider.base_url,
        timeout=25.0, max_retries=1,
    ) as client:
        response = await client.chat.completions.create(**kwargs)
    if not response.choices:
        raise ValueError("empty choices")
    choice = response.choices[0]
    if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
        return "", "Модель отказалась от ответа. Попробуйте другой сценарий."
    content = choice.message.content
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty content")
    content = content.strip()
    warning = "Ответ сокращен по лимиту длины." if choice.finish_reason == "length" else ""
    return content, warning


async def assess(provider: Provider, payload: dict) -> AIReport:
    report = AIReport(provider.name, provider.model)
    if not provider.api_key:
        report.error = f"Добавьте {provider.name.upper()}_API_KEY в .env. AI-отчет еще не создан."
        return report
    started = monotonic()
    try:
        report.text, report.warning = await asyncio.wait_for(
            _request(provider, payload), timeout=DEADLINE_SECONDS,
        )
        if not report.text:
            report.error, report.warning = report.warning, ""
    except (AuthenticationError, PermissionDeniedError):
        report.error = "Ключ не принят или доступ запрещен. Проверьте ключ и права на модель."
    except RateLimitError:
        report.error = "Достигнут лимит запросов или квота. Проверьте баланс и повторите позже."
    except (APITimeoutError, asyncio.TimeoutError):
        report.error = "Сервис не ответил вовремя. Повторите запрос позже."
    except APIConnectionError:
        report.error = "Не удалось подключиться к API. Проверьте интернет и доступность сервиса."
    except APIStatusError as exc:
        if exc.status_code == 404:
            report.error = "Модель недоступна. Проверьте доступ к модели и ее идентификатор."
        elif exc.status_code >= 500:
            report.error = "Ошибка на стороне AI-сервиса. Повторите запрос позже."
        else:
            report.error = f"API отклонил запрос (HTTP {exc.status_code}). Проверьте настройки модели."
    except (APIError, ValueError, TypeError, AttributeError, IndexError):
        report.error = "Сервис вернул пустой или некорректный ответ. Повторите запрос."
    except Exception:
        # Do not leak SDK exception strings (which may include headers or secrets).
        report.error = "Не удалось получить AI-отчет. Проверьте настройки и повторите запрос."
    report.seconds = round(monotonic() - started, 1)
    return report


async def generate_reports(providers: list[Provider], payload: dict) -> dict[str, AIReport]:
    if len(providers) != 1 or providers[0].name != "OpenAI":
        raise ValueError("Exactly one OpenAI provider is required")
    report = await assess(providers[0], payload)
    return {report.provider: report}
