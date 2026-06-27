# مشاهده‌پذیری: لاگ‌گیری و ترِیس (Observability)

> این سند الزامات و پیاده‌سازی **logging** و **tracing** پروژه را تعریف می‌کند.
> مشاهده‌پذیری یک قید درجه‌یک پروژه است و در فاز ۰ پایه‌ریزی می‌شود.

سه ستون مشاهده‌پذیری در نظر گرفته می‌شود:

1. **Logs** — لاگ ساختاریافته (structured) با هم‌بستگی (correlation).
2. **Traces** — ردگیری توزیع‌شده با OpenTelemetry.
3. **Metrics** — (فاز بعد) از طریق همان OpenTelemetry SDK.

---

## ۱. لاگ‌گیری ساختاریافته (Structured Logging)

- کتابخانه: **structlog** روی pipeline استاندارد `logging` پایتون.
- خروجی: در production **JSON** (برای جمع‌آوری در ELK/Loki/…)، در development خوانا و رنگی.
- پیکربندی متمرکز در `backend/config/logging.py` و فعال‌سازی در `config/settings/base.py`.
- کنترل با متغیرهای محیطی: `DJANGO_LOG_LEVEL`، `DJANGO_JSON_LOGS`.

### فیلدهای استاندارد هر لاگ
- `timestamp` (ISO)، `level`، `logger`، `event`.
- `request_id` — شناسه‌ی هم‌بستگی هر درخواست (پایین را ببینید).
- `trace_id` و `span_id` — هنگام فعال‌بودن ترِیس، برای پیوند log↔trace.

### قاعده‌ها (الزامی)
- همیشه از logger ساختاریافته استفاده شود:
  ```python
  import structlog
  logger = structlog.get_logger(__name__)
  logger.info("order_placed", order_id=order.id, channel=channel.code)
  ```
- نام رویداد (event) یک رشته‌ی کوتاه snake_case است؛ داده‌ها به‌صورت key/value پاس داده می‌شوند، نه داخل پیام.
- **هیچ‌وقت** داده‌ی حساس (PII، توکن، رمز، شماره کارت) لاگ نشود.
- پیام/کامنت لاگ‌ها انگلیسی است (مطابق قانون پروژه: بدون فارسی در کد).

---

## ۲. هم‌بستگی درخواست (Request Correlation)

- میدل‌ور `backend/config/middleware.py::RequestIDMiddleware`:
  - مقدار هدر ورودی `X-Request-ID` را می‌خواند؛ اگر نبود یک id جدید می‌سازد.
  - آن را به context لاگ (`structlog.contextvars`) بایند می‌کند تا همه‌ی لاگ‌های آن درخواست هم‌بسته شوند.
  - همان id را در هدر پاسخ برمی‌گرداند.
- تست `tests/integration/health/test_health_endpoint.py` این رفتار را پوشش می‌دهد.

---

## ۳. ترِیس توزیع‌شده (Distributed Tracing)

- استاندارد: **OpenTelemetry** (وابسته به vendor نیست).
- پیکربندی در `backend/config/observability.py::configure_tracing` و فراخوانی در `wsgi.py`/`asgi.py`.
- اختیاری و به‌صورت پیش‌فرض خاموش؛ با `OTEL_ENABLED=true` فعال می‌شود (تا تست/توسعه سبک بماند).
- اکسپورتر: **OTLP** به collector (مثلاً Jaeger/Tempo/Grafana) از طریق `OTEL_EXPORTER_OTLP_ENDPOINT`.
- ابزارگذاری خودکار (auto-instrumentation) برای: **Django، psycopg، Redis، Celery**.
- همه‌ی importها دفاعی‌اند؛ اگر اکستره‌ی `observability` نصب نباشد یا غیرفعال باشد، اپلیکیشن بدون تغییر کار می‌کند.

### فعال‌سازی محلی
```bash
# .env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```
و نصب اکستره:
```bash
cd backend && pip install -e ".[dev,observability]"
```

---

## ۴. پیوند سه ستون

با وجود `request_id` در لاگ‌ها و `trace_id`/`span_id` تزریق‌شده توسط پردازشگر
structlog، می‌توان از یک خط لاگ به ترِیس متناظرش و برعکس رسید. این پایه‌ی
دیباگ‌پذیری در همه‌ی فازهای بعدی است.

## ۵. کارهای فاز بعد
- افزودن **metrics** (OpenTelemetry Metrics) برای نرخ خطا/تأخیر/توان عملیاتی.
- داشبورد و alerting (Grafana).
- نمونه‌برداری (sampling) در production برای کنترل هزینه‌ی ترِیس.
- ابزارگذاری ترِیس سمت فرانت‌اند (browser → backend) برای ردگیری end-to-end.
