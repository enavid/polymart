# Polymart

پلتفرم فروشگاهی چندمنظوره و **White-Label**: یک زیرساخت بک‌اند headless مبتنی بر
Django با معماری تمیز (Clean Architecture) + یک ویترین React/Next بازاسکین‌پذیر که
فقط با تغییر تم و پیکربندی می‌تواند هر کالایی را بفروشد (قهوه، لوازم آرایشی،
لوازم خودرو و …).

## نقشه‌ی مستندات

- [منابع و لینک‌های تحقیق](01-research-links.md)
- [گزارش ویژگی‌ها](02-features-report.md)
- [نقشه‌ی راه فازبندی‌شده](03-roadmap.md)
- [مشاهده‌پذیری: لاگ و ترِیس](04-observability.md)
- [تصمیم‌های معماری (ADR)](adr/0001-record-architecture-decisions.md)

## شروع سریع (توسعه)

```bash
cp .env.example .env
make build
make up
make migrate
# backend:  http://localhost:8000/api/v1/health/
# API docs: http://localhost:8000/api/docs/
# frontend: http://localhost:3000
```

برای اجرای دروازه‌ی کیفیت (همان چیزی که CI اجرا می‌کند):

```bash
make ci
```
