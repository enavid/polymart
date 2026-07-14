# مرحله ۳ — نقشه‌ی راه فازبندی‌شده (Roadmap)

> این نقشه‌ی راه بر پایه‌ی [`02-features-report.md`](./02-features-report.md) تنظیم شده و قیدهای مهندسی خواسته‌شده را رعایت می‌کند:
> **TDD (اول تست بعد کد)، Clean Architecture کامل (Uncle Bob)، Docker، unit + integration test، Makefile، مستندسازی، CI/CD روی GitHub، بدون کامنت فارسی در کد.**
>
> تاریخ: ۲۰۲۶-۰۶-۲۷ · بازنگری: ۲۰۲۶-۰۶-۲۹ (توزیعِ UI در همهٔ فازها).
>
> **بازنگریِ UI:** پیش از این همهٔ ویترین در فاز ۸ متمرکز بود و تا انتهای کار هیچ
> چیزی به‌صورت بیزنسی قابلِ بررسیِ چشمی نبود. در این بازنگری، **هر فاز یک بخشِ
> UI/ویترینِ خودش را دارد** تا خروجیِ هر فاز در عمل دیده و تأیید شود. بنیادِ تم/توکن
> و i18n/RTL و کلاینتِ API تایپ‌دار به **فاز ۰** منتقل شد؛ صفحاتِ هر قابلیت به فازِ
> همان قابلیت رفت؛ و **فاز ۸** به لایهٔ بلوغ و تم‌پذیریِ White-Label تغییرِ نقش داد
> (هیچ‌چیز حذف نشد، فقط جابه‌جا شد).

## اصول حاکم بر همه‌ی فازها

این قواعد در **هر** فاز و **هر** تسک رعایت می‌شوند (تعریف «Done»):

1. **TDD:** برای هر قابلیت اول تست نوشته می‌شود (red → green → refactor). هیچ کدی بدون تست merge نمی‌شود.
2. **Clean Architecture:** قاعده‌ی وابستگی رو به داخل. دامنه هرگز Django/DRF/ORM را import نمی‌کند.
3. **پوشش تست:** آستانه‌ی coverage در CI اجباری (هدف ≥ ۹۰٪ روی لایه‌ی دامنه/use-case).
4. **Docker:** هر چیز در کانتینر اجرا می‌شود؛ توسعه با `docker compose`.
5. **Makefile:** همه‌ی دستورات پرتکرار پشت `make` (و CI همان `make`ها را صدا می‌زند).
6. **مستندسازی:** هر فاز مستندات خودش (ADR + API docs + README بخش) را به‌روز می‌کند.
7. **بدون کامنت فارسی در کد** (کامنت/نام‌گذاری انگلیسی؛ مستندات می‌تواند فارسی باشد).
8. **CI سبز شرط merge:** lint + type-check + test + security scan باید پاس شوند.
9. **مشاهده‌پذیری اجباری:** هر قابلیت باید لاگ ساختاریافته و قابلیت ترِیس داشته باشد (جزئیات در [`04-observability.md`](./04-observability.md)).
10. **UI همراهِ هر فاز:** هر فاز علاوه بر بک‌اند یک **بخشِ UI/ویترین** دارد تا خروجی به‌صورت بیزنسی قابلِ تأیید باشد. فرانت TDD خودش را دارد (Vitest + React Testing Library + MSW؛ e2e با Playwright)، روی **لایهٔ API تایپ‌دارِ تولیدشده از OpenAPI** کار می‌کند و از **بنیادِ توکنِ سه‌لایهٔ** فاز ۰ استفاده می‌کند (هیچ مقداردهیِ تمِ سخت‌کدشده).

> راهبرد کلی: نزدیک‌ترین نقشه‌ی مرجع، **Saleor** (همین استک) است؛ الگوی Clean Architecture را از **Medusa**، مدل RBAC را از **Vendure + Saleor** و انضباط دامنه را از **Sylius/Cosmic Python** وام می‌گیریم.

---

## فاز ۰ — پایه‌ریزی و داربست مهندسی (Foundation)

> هدف: زیرساختی که از روز اول TDD و Clean Architecture و CI/CD را تحمیل کند. **قبل از هر قابلیت کسب‌وکاری.**

- راه‌اندازی مونوریپو: `backend/` (Django) + `frontend/` (React/Next) + `docs/` + `infra/`.
- اسکلت Clean Architecture در بک‌اند: پوشه‌های `domain/`, `application/`, `infrastructure/`, `interface/` + یک composition root برای DI.
- ابزار کیفیت بک‌اند: `ruff` (lint+format)، `mypy` (type)، `pytest` + `pytest-django` + `factory_boy` + `pytest-cov`.
- ابزار کیفیت فرانت: ESLint + Prettier + `tsc` + Vitest + React Testing Library + MSW + Playwright.
- Docker: Dockerfile چندمرحله‌ای برای back و front + `docker-compose` (web, db=Postgres16, redis, worker=Celery, beat, frontend, nginx).
- **Makefile** (native-first) با هدف‌های: `help, setup, install, env, infra-up, infra-down, up, down, restart, logs, ps, migrate, makemigrations, seed, shell, superuser, lint, format, type, test, test-unit, test-integration, coverage, security, check, fe-lint, fe-type, fe-test, fe-build, e2e, docker-build, docker-up, docker-down, ci, docs`.
- **CI/CD (GitHub Actions):** jobهای موازی lint / test (با Postgres+Redis به‌عنوان service) / security (bandit، pip-audit) / build؛ least-privilege permissions، concurrency، cache.
- **مشاهده‌پذیری (logging + tracing):** structlog (لاگ ساختاریافته JSON/console) + میدل‌ور request-id + OpenTelemetry (اختیاری، auto-instrumentation برای Django/psycopg/Redis/Celery) + پیوند log↔trace.
- اسکلت مستندات: MkDocs Material + `drf-spectacular` (OpenAPI) + پوشه‌ی ADR.
- یک «walking skeleton»: یک endpoint بی‌اهمیت با تست unit (با fake repo) + integration (با DB) که کل مسیر TDD→CI→Docker را اثبات کند.
- نوشتن `CLAUDE.md` (راهنمای کار با کدبیس برای عامل‌ها/توسعه‌دهنده‌ها).

**بخش UI/ویترینِ فاز ۰ — بنیادِ فرانت (منتقل‌شده از فاز ۸):** ✅ تحویل شد همراهِ
UIِ فاز ۱ (توکنِ سه‌لایه، shadcn/ui، next-intl + RTL + Vazirmatn + جلالی، و کلاینتِ
API تایپ‌دار با کوکیِ JWT). تنها موردِ معوق: تولیدِ خودکارِ تایپ از OpenAPI (فعلاً
ماژول‌های تایپ‌دارِ دستی) و چیدنِ تم‌های نمونه که به فاز ۸ تعلق دارد.
- داربستِ Next.js (App Router) + React + TypeScript (strict) + Tailwind CSS v4.
- **بنیادِ توکنِ سه‌لایه** (primitive → semantic → brand/niche) با `@theme`؛ حتی با یک تمِ پیش‌فرضِ خام — تا UIِ همهٔ فازها روی آن سوار شود.
- **i18n + RTL پایه:** next-intl + CSS logical properties + فونت Vazirmatn + قالب‌بندیِ عدد/پول/تاریخِ **جلالی** (تومان/ریال) به‌صورتِ زیرساخت (نه صفحه).
- **لایهٔ API تایپ‌دار** تولیدشده از OpenAPI (`drf-spectacular`) + TanStack Query (+ Zustand برای UI state)؛ provider-swap.
- یک صفحهٔ «health / walking skeleton» در فرانت که مسیرِ FE→API→BE را اثبات کند، با Vitest+RTL+MSW و یک e2e Playwright.

**خروجی فاز ۰:** `make ci` سبز، یک endpoint end-to-end در Docker، pipeline فعال، و یک ویترینِ خامِ تم‌پذیر که به API وصل است.

---

## فاز ۱ — هویت، کاربران و RBAC (Identity & Access)

> هدف: پاسخ به خواستهٔ «کاربرها با سطح دسترسی‌های مختلف».
>
> **وضعیتِ بک‌اند:** ✅ کامل. همهٔ اسلایس‌های قابل‌انجامِ فاز ۱ تحویل شدند؛ تنها
> اتصالِ scope به **انبار** به فاز ۵ (جایی که context انبار ساخته می‌شود) و مواردِ
> ذاتاً تراکنشی (شمارندهٔ atomic OTP و audit تراکنشیِ پول/موجودی) به Unit of Work
> فاز ۳ سپرده شدند.
>
> **وضعیتِ UI:** ✅ کامل (پایین). همراهِ آن، **بنیادِ فرانتِ فاز ۰** هم ساخته شد
> (انتخابِ کاربر: «استک کامل اول»): Tailwind v4 + سیستمِ توکنِ سه‌لایه، shadcn/ui،
> next-intl + RTL + Vazirmatn + قالب‌بندیِ جلالی/پول، و کلاینتِ API تایپ‌دار با
> کوکیِ JWT (`credentials:'include'`) و `ApiError`. تستِ فرانت با Vitest+RTL+MSW و
> یک E2E Playwright برای فلوِ ورود.

- مدل کاربر سفارشی (هویت مبتنی بر موبایل/ایمیل)، احراز هویت (JWT در HttpOnly cookie یا session).
- ثبت‌نام/ورود/بازیابی، تأیید OTP موبایل (نیاز بومی ایران).
- **RBAC دولایه:** نقش‌ها (Group + permission سفارشی) + scope سطح‌شیء (`django-guardian`).
- رجیستری permission که افزونه‌ها بتوانند permission اضافه کنند (الگوی `PermissionDefinition`).
- DRF permission classها به‌صورت secure-by-default.
- پنل ساخت کاربر/نقش، تخصیص نقش، scope به کانال/انبار.
- **audit log** پایه (چه کسی/کِی/چه تغییری).
- مدل اولیه‌ی **Channel** (موجودیت درجه‌یک) که از اینجا به بعد همه‌چیز به آن وابسته است.

**خروجی فاز ۱:** ورود کاربر با نقش‌های مختلف؛ اندپوینت‌ها بر اساس permission محافظت‌شده.

### پیشرفتِ بک‌اندِ فاز ۱ (خلاصه)

- [x] **Channel (موجودیت درجه‌یک)** — ADR 0004. دامنه: `Channel` + value objectهای `Currency`/`ChannelSlug` (خودـاعتبارسنج، immutable). application: `ChannelRepository` + use caseهای `CreateChannel`/`SetChannelStatus`/`GetChannel`/`ListChannels` با لاگِ مناسبِ حسابرسی. infrastructure: اپ `channel`، مدل/mapper/`DjangoChannelRepository` (ترجمهٔ خطاهای ORM به دامنه). interface: `channels/` (secure-by-default، نگاشت ۴۰۴/۴۰۹/۴۰۰). پوشش ۱۰۰٪.
- [x] **کاربر سفارشی + احراز هویتِ کوکی‌محورِ JWT** — ADR 0005. `PhoneNumber` (نرمال‌سازی به E.164 ایران)؛ `User(AbstractBaseUser)` با `USERNAME_FIELD=phone_number`؛ `CookieJWTAuthentication` (HttpOnly/SameSite=Lax/Secure-in-prod) + `auth/login|refresh|logout|me` (شکستِ یکنواختِ ۴۰۱). لاگ بدونِ رمز/شماره (PII)؛ actor = شناسهٔ پایدارِ کاربر. ✅ پیگیریِ معوق: blacklist توکن هنگام logout (ADR 0010).
- [x] **ثبت‌نام/بازیابی + OTP موبایل** — ADR 0006. `OtpChallenge` (انقضا، سقف تلاش، single-use) + `OtpPurpose`؛ فقط hash ذخیره می‌شود. use caseهای `RequestOtp`/`RegisterUser`/`ResetPassword` + `OtpVerifier` روی پورت‌های `OtpRepository`/`CodeGenerator`/`CodeHasher`/`SmsSender`/`Clock`/`UserDirectory`. امنیت: پاسخِ یکنواختِ ضدِenumeration، کدِ ۶رقمی با TTL ۲ دقیقه و قفل پس از ۵ تلاش، cooldown، purpose-scoped و single-use؛ در production کد/رمز/شماره هرگز لاگ نمی‌شود (در `DEBUG`، چون gatewayِ واقعیِ SMS وجود ندارد، `LoggingSmsSender` کد را به‌صورتِ رویدادِ `otp_dispatched_dev` لاگ می‌کند تا فلوِ OTP به‌صورتِ محلی قابلِ تکمیل باشد؛ این شاخه با `settings.DEBUG` محافظت می‌شود و در production هرگز اجرا نمی‌شود). ✅ ابطالِ توکن پس از reset (ADR 0010). ⏳ معوق به فاز ۳: شمارندهٔ تلاشِ atomic (نیازمند Unit of Work).
- [x] **RBAC دولایه + رجیستریِ permission** — ADR 0007. رجیستریِ خالص (`PermissionDefinition`/`RoleDefinition`/`PermissionRegistry`) با یکتایی و یکپارچگیِ ارجاعی؛ هر context مجوزش را اعلام می‌کند. application: `AccessControlGateway` + `AssignRole`/`GrantChannelManagement`. infrastructure: اپ `access` با `GuardianAccessControl` (Group برای نقش، guardian برای scope) و `sync_access_control` روی `post_migrate` (idempotent). interface: `GlobalChannelManagePermission` و `ScopedChannelManagePermission`؛ `ANONYMOUS_USER_NAME=None`. پوشش ۱۰۰٪. ✅ API ادمینِ تخصیصِ نقش/scope (ADR 0009). ⏳ معوق (کم‌اولویت، بدونِ فاز): مکانیزمِ entry-point برای افزونه‌ها.
- [x] **audit log پایه** — ADR 0008. value objectهای `FieldChange`/`AuditEntry` (action نقطه‌دارِ namespaceشده، actor، زمانِ tz-aware). application: `AuditRecorder` (seamِ سطح‌بالا) + `AuditTrail` (append-only) + `Clock`. infrastructure: اپ `audit`، `AuditLogModel` (جدولِ append-only، `changes` به‌صورت JSON، ایندکس روی resource/action). مصرف‌کنندهٔ اول = میوتیشن‌های Channel؛ تغییرِ بی‌اثر چیزی ثبت نمی‌کند؛ actor = شناسهٔ کاربر. ✅ ثبتِ رویدادهای RBAC (ADR 0009). ⏳ معوق به فاز ۳: **audit تراکنشی** برای مسیرهای پول/موجودی.
- [x] **API ادمینِ دسترسی + audit رویدادهای RBAC + API خواندنِ audit** — ADR 0009. مجوزِ `manage_access` + نقشِ `access_admin`؛ پورتِ خواندنیِ جدا `AuditQuery` + `ListAuditEntries` (صفحه‌بندی پیش‌فرض ۵۰، سقف ۲۰۰). اندپوینت‌های `POST access/role-assignments/`، `POST access/channel-grants/`، `GET audit/entries/` همگی پشتِ `manage_access`. پوشش ۱۰۰٪.
- [x] **ابطال توکن (logout + بازنشانیِ رمز)** — ADR 0010. اپ `token_blacklist`؛ logout همان refresh-tokenِ کوکی را blacklist می‌کند (best-effort)؛ بازنشانیِ رمز همهٔ توکن‌های outstanding را از طریقِ پورتِ `TokenRevoker` باطل می‌کند.
- [x] **اتصالِ scope دسترسی به انبار** — ✅ در **فاز ۵** همراهِ APIِ ادمینِ انبار انجام شد (ADR 0048).

### بخش UI/ویترینِ فاز ۱ — ✅ کامل

- [x] صفحاتِ احراز هویت: ورود/ثبت‌نام/تأییدِ OTP/بازیابیِ رمز (RTL، پیامِ یکنواختِ
  «نام‌کاربری یا رمز نادرست» روی ۴۰۱، ضدِ enumeration). دو فلوِ نیازمندِ OTP
  (ثبت‌نام و بازیابی) دکمهٔ «ارسالِ کد» درون‌فرمیِ مشترک دارند (`SendCodeButton`).
- [x] صفحهٔ حساب کاربری روی `auth/me` + خروج، با هوکِ `useCurrentUser`/`useLogout`
  (۴۰۱ = حالتِ خروج، نه خطا).
- [x] **پنلِ ادمینِ دسترسی**: تخصیصِ نقش و اعطای مدیریتِ کانال روی `access/*` (با
  `user_id`)؛ نگاشتِ ۴۰۳→پیام دسترسی. توجه: API فاز ۱ اندپوینتِ فهرست/ساختِ کاربر
  ندارد (کاربر از مسیرِ ثبت‌نام ساخته می‌شود)، پس پنل با `user_id` کار می‌کند و این
  محدودیت در UI یادداشت شده و در `ISSUES.md` ثبت شد.
- [x] نمایشگرِ **audit log** روی `audit/entries/` (فیلترِ نوع/رویداد/تعداد، خلاصهٔ
  before→after، زمانِ جلالی؛ پاسخِ آرایه‌ای، نه envelopeِ صفحه‌بندی).
- [x] مدیریتِ **کانال‌ها** روی `channels/`: فهرست (+فیلترِ فقط‌فعال)، ساخت
  (نگاشتِ ۴۰۹→موجود، ۴۰۰→نامعتبر)، و تغییرِ وضعیتِ فعال/غیرفعال.

---

## فاز ۲ — کاتالوگ و مدل داده‌ی منعطف (Catalog Core)

> هدف: قلب White-Label — مدل داده‌ای که هر niche را بپذیرد.

- انواع محصول (Product Type) + **ویژگی‌های پویا (Attributes / EAV-like)**.
- محصول، variant، گزینه/modifier، SKU، رسانه، متادیتای JSONB.
- دسته‌بندی سلسله‌مراتبی + کالکشن دستی و قانون‌محور.
- قیمت پایه per-channel/per-currency.
- موجودی ساده (آماده‌سازی برای MSI در فاز بعد).
- API کاتالوگ (لیست/فیلتر/جست‌وجوی پایه) + import/export CSV.
- پنل ادمین کاتالوگ.

**خروجی فاز ۲:** می‌توان کاتالوگ یک niche (مثلاً قهوه) را کامل تعریف و از API خواند و در ویترین دید.

### پیشرفتِ بک‌اندِ فاز ۲ (خلاصه)

- [x] **ویژگی‌های پویا (Attribute)** — ADR 0011. موجودیتِ `Attribute` + `AttributeCode`/`AttributeChoice` + enum `AttributeInputType` (`plain_text`/`number`/`boolean`/`dropdown`، پرچمِ `is_choice_type`)؛ قواعد: نامِ غیرخالی، choices فقط برای نوعِ انتخابی، یکتاییِ choiceها. `AttributeRepository` + `CreateAttribute`/`GetAttribute`/`ListAttributes` با audit (`attribute.created`). infrastructure: اپ `catalog`، `AttributeModel`+`AttributeChoiceModel` (constraintِ یکتاییِ per-attribute، درجِ atomicِ والد+فرزند)، مهاجرتِ `catalog/0001`. interface: `catalog/attributes/` + `<code>/`. RBAC: مجوزِ سراسریِ `manage_catalog` + نقشِ `catalog_admin`. پوشش ۱۰۰٪.
- [x] **انواع محصول (Product Type)** — ADR 0012. `ProductType` + `ProductTypeCode`؛ مجموعهٔ مرتبِ `AttributeCode`ها، بدونِ ارجاعِ دوباره (`DuplicateAttributeAssignmentError`). `ProductTypeRepository` + use caseها؛ ساخت، وجودِ هر Attribute را اعتبارسنجی می‌کند (`UnknownAttributeError`) و audit می‌نویسد. `ProductTypeModel` + جدولِ واسطِ مرتب (یکتاییِ per-type، FK با `PROTECT`، درجِ atomic)، مهاجرتِ `catalog/0002`. interface: `catalog/product-types/`. پوشش ۱۰۰٪ (شاملِ defenseِ TOCTOU).
- [x] **محصول (Product) + مقادیرِ منطبقِ Attribute + متادیتای JSONB** — ADR 0013. `Product` + `ProductCode`/`AttributeValue` + **سرویس دامنهٔ انطباق** (`normalize_attribute_values`): number با `Decimal` (ردِ NaN/Inf)، boolean literal، dropdown از choiceها، plain_text غیرخالی، حضورِ requiredها. `ProductRepository` + use caseها؛ `CreateProduct` نوع و تعاریف را بارگذاری، انطباق را به سرویس می‌سپارد، سپس persist و audit. `ProductModel` (`metadata` به‌صورت JSONB) + جدولِ فرزندِ مرتب؛ درجِ atomic؛ مهاجرتِ `catalog/0003`. interface: `catalog/products/`. پوشش ۱۰۰٪.
- [x] **variant محصول + SKU یکتا** — ADR 0014. `ProductVariant` + value objectِ `Sku` (کانونی‌سازیِ upper-case، شِیپِ slug سخت‌گیر). `VariantRepository` + use caseها؛ بررسیِ وجودِ والد، سپس persist و audit. `ProductVariantModel` (FK با `CASCADE`، `sku` یکتا؛ تبدیلِ `IntegrityError` به `VariantAlreadyExistsError`)، مهاجرتِ `catalog/0004`. interface: تودرتو زیرِ محصول (`catalog/products/<code>/variants/`) + `catalog/variants/<sku>/`. پوشش ۱۰۰٪.
- [x] **گزینه/modifier + رسانه (سطحِ variant) + تمایزِ Attributeهای product/variant** — ADR 0015/0016/0017، در سه زیراسلایس: (۱) `ProductType` مجموعهٔ دومِ `variant_attributes` کنارِ `attributes` می‌گیرد؛ یکتایی روی **هر دو سطح**؛ جدولِ واسط ستونِ `kind` + `position` گرفت. (۲) `ProductVariant` مقادیرِ منطبق با `variant_attributes` می‌گیرد و **همان سرویس دامنهٔ انطباق** را بازاستفاده می‌کند (`UnassignedAttributeError`)؛ درجِ atomicِ سر+مقادیر؛ audit با `value_count`. (۳) value objectِ `MediaAsset` (URLِ مطلق یا سایت‌نسبی + alt، بدونِ تکرارِ URL)؛ `ProductVariantMediaModel` هم‌تراکنش؛ audit با `media_count` — رسانه فعلاً «ارجاعِ URL» است، نه آپلودِ فایل. پوشش ۱۰۰٪.
- [x] **دسته‌بندی سلسله‌مراتبی (Category)** — ADR 0018. `Category` + `CategorySlug`؛ والد با slug (`None` برای ریشه)، ردِ self-parent (تنها چرخهٔ ممکن در زمانِ ساخت). `CategoryRepository` + use caseها؛ بررسیِ والد، ردِ slug تکراری، audit. `CategoryModel` (FKِ خودارجاعِ `parent` با `PROTECT`، slug یکتا؛ تبدیلِ `IntegrityError`، defenseِ TOCTOU؛ درجِ تک‌ردیفی بدونِ `atomic`)، مهاجرتِ `catalog/0008`. interface: `catalog/categories/`. پوشش ۱۰۰٪.
- [x] **اتصالِ محصول↔دسته (عضویت)** — ADR 0019. سرویس دامنهٔ `reject_duplicate_categories` + خطاهای `DuplicateCategoryAssignmentError`/`UnknownCategoryError`. پورتِ مجزای `ProductCategoryRepository` (replace/list) + `SetProductCategories`/`GetProductCategories` با audit (`product.categories_changed`، before/after). `ProductCategoryModel` (یکتاییِ (product, category)، FKِ محصول `CASCADE`/دسته `PROTECT`)؛ `replace` با `transaction.atomic()` + `select_for_update()` روی محصول، مهاجرتِ `catalog/0009`. interface: `GET/PUT catalog/products/<code>/categories/` (PUT = جایگزینیِ idempotent). پوشش ۱۰۰٪.
- [x] **کالکشن (گرهِ گروه‌بندیِ دستی)** — ADR 0020. `Collection` + `CollectionSlug`؛ غیرسلسله‌مراتبی (بدونِ parent)، گروه‌بندیِ مسطحِ merchandising. `CollectionRepository` + use caseها؛ ردِ slug تکراری، audit (`collection.created`). `CollectionModel` (slug یکتا، درجِ تک‌ردیفی، تبدیلِ `IntegrityError`)، مهاجرتِ `catalog/0010`. interface: `catalog/collections/`. پوشش ۱۰۰٪.
- [x] **عضویتِ دستیِ کالکشن (لیستِ مرتبِ محصولات)** — ADR 0021. سرویس دامنهٔ `reject_duplicate_products` + خطاهای `DuplicateProductMembershipError`/`UnknownProductError`؛ برخلافِ دسته، عضویت یک «لیستِ مرتبِ curated» است (ترتیبِ درخواست حفظ می‌شود). پورتِ مجزای `CollectionProductRepository` + `SetCollectionProducts`/`GetCollectionProducts` با audit (`collection.products_changed`، before/after). `CollectionProductModel` (یکتاییِ (collection, product)، FKِ کالکشن `CASCADE`/محصول `PROTECT`)؛ `replace` با `transaction.atomic()` + `select_for_update()` روی کالکشن، مهاجرتِ `catalog/0011`. interface: `GET/PUT catalog/collections/<slug>/products/` (PUT = جایگزینیِ idempotent). پوشش ۱۰۰٪.
- [x] **کالکشن قانون‌محور (عضویت از روی predicate)** — ADR 0022. enum `RuleOperator` (`equals`/`not_equals` — عملگرهای بازه‌ای/عددی به‌عمد به اسلایسِ بعد سپرده شد) + value objectِ `RuleCondition` + دو سرویس دامنه: `reject_duplicate_conditions` (یکتاییِ سه‌تاییِ attribute/operator/value؛ یک attribute با عملگر/مقدارِ متفاوت predicateِ مجزاست) و `match_products` (انتخابِ محصولات با **عطفِ (AND)** شرط‌ها روی مقادیرِ کانونیِ ذخیره‌شده؛ `not_equals` برای محصولِ فاقدِ آن attribute صادق است؛ قاعدهٔ خالی **هیچ** محصولی را انتخاب نمی‌کند، نه همه را). پورتِ مجزای `CollectionRuleRepository` + use caseهای `SetCollectionRule`/`GetCollectionRule`/`GetCollectionRuleMembers` (عضویت **به‌صورتِ پویا هنگام خواندن** محاسبه می‌شود؛ بدونِ materialize، بدونِ Celery) با audit (`collection.rule_changed`، before/after) و بررسیِ وجودِ هر Attribute (۴۰۰ در برابرِ ۴۰۴ِ خودِ کالکشن). `CollectionRuleConditionModel` (یکتاییِ (collection, attribute, operator, value)، FKِ کالکشن `CASCADE`/Attribute `PROTECT`)؛ `replace` با `transaction.atomic()` + `select_for_update()`؛ مهاجرتِ `catalog/0012`. interface: `GET/PUT catalog/collections/<slug>/rule/` (PUT = جایگزینیِ idempotent؛ خالی = پاک‌سازی) و `GET catalog/collections/<slug>/rule/members/`. عضویتِ دستی (ADR 0021) و قانون‌محور دو facetِ مستقل‌اند؛ ترکیبِ آن‌ها به اسلایسِ ویترین/PLP سپرده شد. پوشش ۱۰۰٪.
- [x] **قیمت پایه per-channel/per-currency** — ADR 0023. value objectهای `Money`
  (`amount: Decimal` — نه `float`؛ مثبتِ اکید، متناهی، با سقفِ دقت ۱۸ رقم/۴ اعشار) و
  `ChannelPrice` (ارجاع به کانال با slug + `Money`)؛ سرویس دامنهٔ
  `reject_duplicate_channel_prices` (هر variant در هر کانال حداکثر یک قیمت). پورتِ
  مجزای `VariantPriceRepository` (replace/list) + پورتِ باریکِ `ChannelReader`
  (`currency_of`) که کاتالوگ را بدونِ وابستگی به دامنهٔ channel به واحدِ پولِ کانال
  می‌رساند. use caseهای `SetVariantPrices`/`GetVariantPrices`: **واحدِ پول هرگز از
  کلاینت گرفته نمی‌شود بلکه از کانال مشتق می‌شود** (قیمت در واحدِ غلط غیرممکن می‌شود)؛
  کانالِ ناشناخته ۴۰۰، مبلغِ نامعتبر/صفر/منفی ۴۰۰، variantِ ناشناخته ۴۰۴؛ audit ردِ
  حساس‌به‌پول `variant.price_changed` (before/after با مبلغ‌ها) و لاگِ ساختاریافته که
  مبلغ را لو نمی‌دهد. `VariantPriceModel` (FKِ variant با `CASCADE`، `channel_slug`،
  snapshotِ `currency_code`، `amount` به‌صورت `DecimalField(18,4)`، یکتاییِ
  (variant, channel_slug))؛ `replace` با `transaction.atomic()` + `select_for_update()`
  روی variant؛ ارجاعِ کانال نرم است (بدونِ FKِ بین‌اپی، چون کانال bounded contextِ
  جداست و حذف‌شدنی نیست). مهاجرتِ `catalog/0013`. interface:
  `GET/PUT catalog/variants/<sku>/prices/` (PUT = جایگزینیِ idempotent؛ خالی = پاک‌سازی؛
  مبلغ در پاسخ رشته است تا `Decimal` دقیق در JSON حفظ شود). پوشش ۱۰۰٪.
- [x] موجودی ساده + API کاتالوگ (لیست/فیلتر/جست‌وجو) + import/export CSV. _(هر سه
  بخش کامل شد، اسلایس‌به‌اسلایس.)_
  - [x] **موجودی ساده (on-hand per variant)** — ADR 0024. value objectِ
    `StockQuantity` (عددِ صحیحِ نامنفی، ردِ bool/غیرصحیح، با سقفِ ۲٬۱۴۷٬۴۸۳٬۶۴۷) +
    سرویس دامنهٔ `adjust_stock` (اعمالِ deltaی علامت‌دار با کفِ صفر — ضدِ overselling؛
    `InsufficientStockError`). پورتِ مجزای `StockRepository` (get/set/adjust) +
    use caseهای `GetVariantStock`/`SetVariantStock`/`AdjustVariantStock` با auditِ
    حساس‌به‌موجودی `variant.stock_changed` (before/after). `VariantStockModel`
    (`OneToOne` به variant با `CASCADE`، `quantity` به‌صورت `PositiveIntegerField`)؛
    `adjust_quantity` کلِ read-modify-write را در `transaction.atomic()` +
    `select_for_update()` روی variant انجام می‌دهد تا دو تعدیلِ هم‌زمان update را گم
    نکنند یا oversell نشوند (قاعدهٔ کفِ صفر در دامنه می‌ماند). مهاجرتِ `catalog/0014`.
    interface: `GET/PUT/PATCH catalog/variants/<sku>/stock/` (PUT = مقدارِ مطلقِ
    idempotent؛ PATCH = deltaی علامت‌دارِ اتمیک). رزرو/کسرِ هنگامِ سفارش و MSIِ
    چندانباره به‌عمد به فازهای بعد سپرده شد. پوشش ۱۰۰٪.
  - [x] **API کاتالوگ (لیست/فیلتر/جست‌وجوی پایه)** — ADR 0025. فلگِ `is_published`
    روی محصول (پیش‌فرض `False`؛ تا انتشار، draft و نامرئی) + use caseِ ادمینِ
    `SetProductPublished` با auditِ `product.publish_changed`. پورتِ خواندنیِ مجزای
    `ProductQueryRepository` (تفکیکِ CQRS از repoی نوشتن) با `search`→`ProductPage`
    (آیتم‌های پنجره‌شده + شمارشِ کلِ match) و `get_published_by_code`. use caseها:
    `SearchCatalogProducts` (که `published_only=True` را **اجبار** می‌کند تا draft
    هرگز عمومی نشود؛ فیلترهای search/category/collection/product_type با ANDِ هم؛
    صفحه‌بندیِ limit پیش‌فرض ۲۰/سقف ۱۰۰ و offset≥۰ → ۴۰۰ در صورتِ خارج‌ازبازه) و
    `GetPublishedProduct` (draft = ۴۰۴، بدونِ لوِ وجود). adapter:
    `DjangoProductQueryRepository` با querysetِ پارامتری‌شده (ضدِ SQLi)، joinِ
    عضویتِ دسته/کالکشن، `icontains` روی name/code، مرتب بر اساس code. endpointهای
    **عمومیِ** `GET catalog/storefront/products/` (پاکتِ `{count,limit,offset,results}`)
    و `GET catalog/storefront/products/<code>/` (بدونِ لوِ `id`)، و `PUT
    catalog/products/<code>/publication/` (ادمین). پوشش ۱۰۰٪.
  - [x] **import/export CSV** — ADR 0026. اسلایسِ سومِ این آیتم. سطحِ محصول (استانداردِ
    product CSV): هر ردیف یک محصول با `code,name,product_type,is_published`، عضویتِ
    دسته (slugها با `|`)، و ستون‌های `attr:<code>` برای مقادیرِ attribute. لایهٔ
    application فقط با `ProductRow` (DTOی تخت) کار می‌کند؛ codecِ CSV (`csv_io.py`) در
    لایهٔ interface است (دامنه `csv` را import نمی‌کند). `ExportCatalogProducts`
    (خواندنی؛ `GET catalog/products/export/` که فایلِ `text/csv` می‌دهد، با همان
    postureی خواندنیِ کاتالوگ یعنی هر کاربرِ احرازشده). `ImportCatalogProducts`
    دو-فاز و **all-or-nothing**: اول کلِ ردیف‌ها اعتبارسنجی می‌شوند (ساختِ value
    object، ردِ کدِ تکراری در فایل/موجود از قبل [create-only]، حلِ product type،
    conformanceی مقادیر با سرویس دامنهٔ موجود، وجودِ دسته‌ها) و خطاها **جمع** می‌شوند؛
    اگر هر خطایی بود هیچ‌چیز نوشته نمی‌شود و همهٔ خطاهای هر-ردیف گزارش می‌شوند، وگرنه
    کلِ batch به writer سپرده می‌شود. مرزِ تراکنش در infrastructure است (پورتِ
    `CatalogImportWriter` / آداپترِ `DjangoCatalogImportWriter` که کلِ batch را در یک
    `transaction.atomic()` می‌نویسد؛ باختِ raceی درج → rollbackِ کامل). auditِ خلاصهٔ
    `catalog.products_imported` (created_count) + لاگِ ساختاریافته با actor. دو سقفِ
    ضدِ DoS: حجمِ بایتیِ آپلود در لبه و تعدادِ ردیف در use case (`ImportTooLargeError`).
    `POST catalog/products/import/` (multipart، پشتِ `manage_catalog`؛ پاسخ همیشه
    به‌شکلِ نتیجهٔ import: ۲۰۰ اگر همه ساخته شدند، ۴۰۰ اگر هیچ‌کدام). پارسِ
    `is_published` محافظه‌کار/fail-closed. ویرایشِ دسته‌جمعی (update) و variant/قیمت/
    موجودی در CSV به‌عمد خارج از این اسلایس. پوشش ۱۰۰٪.

### بخش UI/ویترینِ فاز ۲ (منتقل‌شده از فاز ۸ + پنلِ ادمینِ موجود)

- [x] **پنلِ ادمینِ کاتالوگ** — کاملِ سطحِ بک‌اندِ این فاز در UI آمد (همگام با کلاینتِ
  تایپ‌دارِ `lib/api/catalog.ts`، روی همان الگوی فاز ۱: TanStack Query + کامپوننت‌های
  presentational + i18n فارسی/RTL + Vitest/MSW). مسیرها زیر `/admin/catalog/*`:
  مدیریتِ **Attribute** (با choiceهای پویا برای نوعِ کشویی)، **Product Type** (مجموعهٔ
  ویژگیِ سطحِ product و variant)، **محصول + مقادیرِ ویژگی**، صفحهٔ محصول با **انتشار/لغوِ
  انتشار**، **عضویتِ دسته‌ها**، و **تنوع‌ها** (ساخت با SKU/نام + **گزینه‌ها (option-value)
  و رسانه**)؛ صفحهٔ تنوع با **قیمتِ هر کانال** (مبلغ همیشه رشته — هرگز float) و **موجودی**
  (تنظیمِ مطلق + تغییرِ دلتا با نگاشتِ oversell→پیامِ کاربرپسند)؛ **دستهٔ سلسله‌مراتبی**
  (با والد)، **کالکشن** + **عضویتِ دستی** و **قانونِ پویا** (شرط‌ها + پیش‌نمایشِ اعضا)؛
  و **import/export CSV** (دانلودِ خروجی + بارگذاریِ ورودی با جدولِ خطاهای هر-ردیف).
- [x] **ویترین پایه:** PLP عمومی (`/products`) با جست‌وجو/فیلترِ category/collection/
  product_type و صفحه‌بندی روی API عمومی، و PDP (`/products/<code>`) با مشخصات و
  مدیریتِ ۴۰۴. ملاحظه: **انتخابِ variant از روی option و گالریِ رسانه در PDP** هنوز نیست،
  چون API عمومیِ این فاز فقط در سطحِ محصول می‌خواند (تنوع‌ها را برنمی‌گرداند)؛ به اسلایسِ
  ویترینِ تنوع‌محور سپرده شد (نیازمندِ افزودنِ خواندنِ تنوع به storefront API).
- [x] جست‌وجوی پایه در UI — فیلدِ جست‌وجوی PLP روی `search`ِ API کاتالوگ (ارتقاء به
  جست‌وجوی هوشمند در فاز ۸).

---

## فاز ۳ — سبد خرید، چک‌اوت و سفارش (Cart → Checkout → Order)

- [x] **سبد ماندگار، افزودن/ویرایش/حذف، محاسبه‌ی قیمت سبد** — ADR 0027. context جدیدِ
  `cart`: value objectهای خودِ سبد (`Money` نامنفی — نه float؛ `Sku`، `CartQuantity`
  مثبت، `ChannelRef`)، اگریگیتِ `Cart` با ناوردایِ «هر variant حداکثر یک ردیف»، و سرویس
  دامنهٔ `price_cart` (جمعِ دقیقِ `Decimal`؛ ردیفِ بدونِ قیمت در کانال = `available:false`
  و بیرون از جمعِ کل). سه پورتِ باریک (`CartRepository`، `VariantPricingReader`،
  `ChannelReader`) و چهار use case؛ قیمت‌گذاریِ **پویا** (قیمت هنگام خواندن؛ snapshot در
  ثبتِ سفارش). `AddCartItem` وجود و **قابلِ‌فروش‌بودن** را پیش از درج بررسی می‌کند.
  `DjangoCartRepository.apply` کلِ read-modify-write را زیرِ `transaction.atomic()` +
  `select_for_update()` روی ردیفِ سبد انجام می‌دهد تا دو تغییرِ هم‌زمانِ همان سبد update
  را گم نکنند. API پشتِ `IsAuthenticated`، سبد **همیشه از `request.user`** (بدونِ cart id
  در URL → IDOR ناممکن)؛ پول رشتهٔ دقیق. بدونِ audit (هیچ پول/موجودی‌ای هنوز جابه‌جا
  نمی‌شود). پوشش ۱۰۰٪.
  - [x] **خواندنِ تنوع/قیمتِ ویترین** — ADR 0028 (بستنِ معوقِ فاز ۲، additive، با اجازهٔ
    صریحِ maintainer): `GET /catalog/storefront/products/<code>/variants/?channel=<slug>`
    تنوع‌های محصولِ منتشرشده را با قیمتِ کانال می‌دهد (draft = ۴۰۴، بدونِ لوِ `id`، قیمت
    رشته یا `null`). PDP اکنون سطحِ خرید دارد.
- [x] **use-case چک‌اوت (interactor) با Unit of Work + ایجاد سفارش + state machine
  سفارش** — ADR 0030. context جدیدِ `order` (دامنه/اپلیکیشن/زیرساخت/رابط، Clean
  Architecture کامل): value objectهای خودِ سفارش (`Money` با `Decimal` — نه float؛ `Sku`،
  `OrderQuantity`، `ChannelRef`، `OrderNumber`ِ مبهم/غیرقابل‌حدس، `OrderStatus`) و اگریگیتِ
  `Order` با **قیمتِ اسنپ‌شات‌شده** (هر ردیف unit/line-total را در لحظهٔ ثبت نگه می‌دارد؛
  ناوردایِ «جمع = مجموعِ ردیف‌ها» و هم‌ارزیِ واحدِ پول). **Unit of Work** به‌عنوان مرزِ
  تراکنش (`transaction.atomic`): `PlaceOrder` کلِ خواندنِ سبد → اسنپ‌شاتِ قیمت → **کسرِ
  موجودی** → ثبتِ سفارش → پاک‌سازیِ سبد → **auditِ تراکنشیِ** `order.placed` را در یک تراکنش
  انجام می‌دهد؛ overselling روی هر ردیف کلِ چک‌اوت را rollback می‌کند (ضدِ oversell با
  select_for_updateِ repositoryِ موجودیِ کاتالوگ). state machine سفارش
  (`pending→{paid,cancelled}`, `paid→{fulfilled,cancelled}`). owner-scoping کامل (بدونِ id
  در URL، شماره مبهم → IDOR ناممکن). endpointها پشتِ `IsAuthenticated`:
  `POST/GET orders/`، `GET orders/<number>/`، `POST orders/<number>/cancel/` (لغوِ سفارشِ
  pending با **بازگرداندنِ موجودی** و auditِ `order.cancelled`، هم‌تراکنش). پول رشتهٔ دقیق.
  پوشش ~۱۰۰٪ + integration/E2Eِ اتمیک‌بودن و IDOR.
- [x] خرید مهمان، آدرس‌بوک، سفارش دستی/پیش‌فاکتور — **هر سه کامل شدند** (آدرس‌بوک ADR 0031،
  خریدِ مهمان اسلایس‌های A–C در ADR 0033/0034/0035، سفارشِ دستی/پیش‌فاکتور ADR 0036).
  - [x] **آدرس‌بوک (address book)** — ADR 0031. context جدیدِ `address`: value objectهای
    خودِ آدرس (`PhoneNumber`ِ ایرانی — کپی‌شده از identity به‌جای import، طبقِ قاعدهٔ
    مرزهای context؛ `PostalCode` ده‌رقمیِ ایران؛ `RecipientName`/`Province`/`City`/
    `AddressLine`؛ `AddressId`ِ مبهم مشابهِ `OrderNumber`) و اگریگیتِ `Address` با
    `with_details(...)`ِ ویرایشِ ایمن (id/owner/is_default/created_at هرگز عوض
    نمی‌شوند). پنج use case (`AddAddress`/`ListMyAddresses`/`UpdateAddress`/
    `DeleteAddress`/`SetDefaultAddress`)؛ **اولین آدرسِ هر کاربر همیشه پیش‌فرض** است؛
    تعویضِ پیش‌فرض اتمیک (select_for_update روی هدف + پاک‌سازیِ پیش‌فرضِ قبلی در یک
    تراکنش) و با یک **partial unique constraint** در دیتابیس پشتیبانی می‌شود
    (حداکثر یک پیش‌فرض به‌ازای هر owner، حتی در برابرِ باگِ لایهٔ اپلیکیشن). سقفِ
    دفاعیِ ۲۰ آدرس به‌ازای هر owner (`AddressLimitExceededError` → ۴۰۹). owner-scoping
    کامل + idِ مبهم → IDOR ناممکن (شکلِ نامعتبر و «متعلق به دیگری» هر دو ۴۰۴). بدونِ
    endpointِ `GET /addresses/<id>/` (فهرست خودش کافی است). endpointها پشتِ
    `IsAuthenticated`: `GET/POST addresses/`، `PUT/DELETE addresses/<id>/`،
    `POST addresses/<id>/default/`. پوشش ~۱۰۰٪ + integration روی Postgresِ واقعی +
    E2Eِ سخت‌گیرانه (CRUD، مرزِ سقف، IDOR).
  - [x] **خریدِ مهمان (session-based ownership برای سبد/سفارش)** — کامل در سه اسلایس
    (A: بنیانِ مالکیت + سبدِ مهمان، B: خریدِ مهمان، C: ادغامِ سبد هنگامِ ورود).
    - [x] **اسلایس A — بنیانِ مالکیت + سبدِ مهمان** — ADR 0033. `owner` اکنون یک
      رشتهٔ مبهمِ پیشوندداره (`u:<pk>` برای کاربر، `g:<token>` برای مهمان)؛ `CartModel`
      یک FKِ کاربرِ **nullable** به‌علاوهٔ ستونِ `guest_token` دارد با یک check
      constraint (دقیقاً یک مالک) و دو partial unique constraint (یک سبدِ فعال به‌ازای
      هر مالک+کانال، برای هر نوعِ مالک). هویتِ مهمان یک کوکیِ HttpOnlyِ CSPRNG
      (`guest_session`) است که بک‌اند در **اولین نوشتنِ** سبد mint می‌کند؛ خواندنِ بدونِ
      کوکی سبدِ خالی می‌دهد و **هیچ** کوکی‌ای ست نمی‌کند (بدونِ ردیابیِ بازدیدکنندهٔ
      اول). endpointهای سبد از `IsAuthenticated` به `AllowAny` رفتند؛ ownerِ هر درخواست
      با `resolve_owner` حل می‌شود. توکن = credential، بدونِ idِ سبد در URL → IDOR برای
      مهمان و کاربر هر دو ناممکن. context سفارش در این اسلایس دست‌نخورده (سبدِ کاربر
      همچنان با `owner_id` خوانده می‌شود). بدونِ تغییرِ UI؛ پوششِ unit + integrationِ
      واقعیِDB (ایزولاسیونِ مهمان/کاربر و مهمان/مهمان، mint فقط روی نوشتن، IDOR) و E2Eِ
      موجود سبز.
    - [x] **اسلایس B — خریدِ مهمان** — ADR 0034. سفارش هم مثلِ سبد مالکیتِ دوستونی
      گرفت (`OrderModel` با FKِ کاربرِ nullable + `guest_token` + check constraint +
      indexِ تاریخچهٔ مهمان)؛ repository/mapper/cart-bridge با همان decodeِ پیشونديِ
      `u:`/`g:`. آدرسِ ارسال حالا **یا** `address_id`ِ ذخیره‌شده (کاربر) **یا** یک
      `InlineShippingAddress`ِ درون‌جا (مهمان) است — دقیقاً یکی؛ فرمتِ موبایل/کدپستیِ
      ایرانِ فرمِ درون‌جا در serializer اعتبارسنجی می‌شود و VOِ `ShippingAddress` دوباره
      presence/length را چک می‌کند. endpointهای سفارش از `IsAuthenticated` به `AllowAny`
      رفتند (بدونِ mint؛ owner با `resolve_owner`). UIِ سبد/چک‌اوت/تأییدِ سفارش/تاریخچه
      de-gate شد؛ مهمان فرمِ ارسالِ درون‌جا می‌بیند (بازاستفاده از فرمِ آدرس‌بوک)، بازبینی
      و ثبت می‌کند و به همان صفحهٔ تأیید می‌رسد. IDOR برای مهمان و کاربر ناممکن (بدونِ idِ
      مالک در URL، شمارهٔ مبهم). پوششِ unit + integrationِ واقعیِ DB (round-tripِ سفارشِ
      مهمان با توکن، ایزولاسیونِ مهمان/کاربر، خریدِ مهمانِ سرتاسری، ردِ `address_id` برای
      مهمان) + E2Eِ کاملِ سفرِ خرید مهمان (سبد → چک‌اوتِ درون‌جا → تأیید → تاریخچه → IDOR
      → لغو/بازگردانیِ موجودی). سازگارِ عقب‌رو (سفارش‌های کاربرِ موجود بدونِ مهاجرتِ داده).
    - [x] **اسلایس C — ادغامِ سبدِ مهمان در سبدِ کاربر هنگامِ ورود** — ADR 0035.
      قاعدهٔ ادغام در اگریگیتِ `Cart` (`merge_from`: جمعِ کمیتِ SKU مشترک با سقفِ
      `capped_sum` تا ورود هرگز به‌خاطرِ کمیتِ نامعقول شکست نخورد؛ افزودنِ بقیه).
      پورتِ `CartRepository.merge_guest_into_user` به‌صورتِ اتمیک همهٔ کانال‌های سبدِ
      مهمان را در یک `transaction.atomic()` (قفلِ `select_for_update` روی سبدهای مهمان،
      ادغام در سبدِ کاربرِ هم‌کانال، حذفِ سبدِ مهمان) ادغام می‌کند و idempotent است
      (ورودِ دوباره چیزی ادغام نمی‌کند). `LoginView` پس از احرازِ موفق، سبدِ مهمان را
      ادغام و کوکیِ `guest_session` را پاک می‌کند؛ ادغام best-effort است (خطا لاگ و
      بلعیده می‌شود تا ورود نشکند و کوکی حفظ می‌شود تا سبد گم نشود) و توکنِ مهمان (یک
      credential) هرگز لاگ نمی‌شود. فرانت: کوئریِ `["cart"]` هنگامِ ورود invalidate
      می‌شود تا سبدِ ادغام‌شده تازه خوانده شود. پوششِ unit + integrationِ واقعیِ DB +
      تستِ endpointِ ورود + تستِ فرانت + E2Eِ کامل (سبدِ مهمان → ورود → آیتم در سبدِ
      کاربر). خریدِ مهمان (اسلایس‌های A–C) کامل شد.
  - [x] **سفارشِ دستی/پیش‌فاکتور** — ADR 0036. use caseِ `CreateManualOrder` سفارشِ
    `PENDING` را مستقیم از ردیف‌های staff (sku+تعداد) و آدرسِ درون‌جا می‌سازد (همان مسیرِ
    اسنپ‌شاتِ قیمت + کسرِ اتمیکِ موجودیِ چک‌اوت، بدونِ سبد؛ helperِ مشترکِ
    `_capture_and_deduct` بین `PlaceOrder` و این استخراج شد). سفارش متعلق به staffِ سازنده
    است (مشتری با آدرسِ ثبت‌شده شناخته می‌شود) و aggregate ناوردایِ «هر variant یک ردیف»
    گرفت (`DuplicateOrderLineError`). `GetOrderForInvoice` هر سفارش را با شماره (بدونِ
    owner-scope، فقط پشتِ مجوز) برای پیش‌فاکتور می‌خواند. مجوزِ جدیدِ `manage_orders` +
    نقشِ `order_admin` (متعلق به context سفارش)؛ endpointهای `POST orders/manual/` و
    `GET orders/<number>/pre-invoice/` پشتِ `OrderManagePermission`. پیش‌فاکتور = سفارش +
    `document_type` + جای‌خالیِ مالیات (`tax=null`، `grand_total`=جمع). UI: فرمِ
    `/admin/orders/new` و صفحهٔ چاپیِ `/admin/orders/<number>/pre-invoice` (چاپ با
    `window.print()`، مخفی‌سازیِ کنترل‌ها با `@media print`، پول از منبعِ حقیقتِ سرور).
    پوششِ unit + integrationِ واقعیِ DB (مجوز ۴۰۱/۴۰۳، oversell ۴۰۹، تکراری/خالی ۴۰۰،
    پیش‌فاکتورِ staff برای سفارشِ مهمان) + تستِ فرانت + E2Eِ کامل (ساختِ سفارشِ دستی →
    پیش‌فاکتورِ چاپی → لغو/بازگردانیِ موجودی).
- [x] event bus: انتشار `OrderPlaced`, `PaymentCaptured` — در فاز ۴ تحویل شد (ADR 0041؛
  انتشارِ بعد از commit، مصرف‌کننده‌ها به فازهای بعد سپرده شدند).

**بخش UI/ویترینِ فاز ۳ (منتقل‌شده از فاز ۸):**
- [x] سبدِ خرید (افزودن/ویرایش/حذف، نمایشِ قیمتِ سبد از منبعِ حقیقتِ سرور — بدونِ
  محاسبهٔ مجددِ سمتِ کلاینت؛ ردیفِ ناموجود مشخص و بیرون از جمع). صفحهٔ `/cart`،
  افزودن‌به‌سبد در PDP روی تنوع‌های ویترین، لینکِ سبد در هدر، بلوکِ i18nِ `cart`، تستِ
  Vitest/MSW.
- [x] **آدرس‌بوک (address book)** — ADR 0031. صفحهٔ `/addresses` (لینک در هدر): فهرستِ
  آدرس‌های ذخیره‌شده (پیش‌فرض اول)، فرمِ افزودن/ویرایشِ مشترک، تغییرِ پیش‌فرض، و حذف با
  **تأییدِ درون‌صفحه‌ای (بدونِ dialogِ مرورگر)** — مشابهِ الگوی لغوِ سفارش. خطای
  اعتبارسنجیِ بک‌اند فنی/انگلیسی است، پس پیامِ لوکالایز‌شده نمایش داده می‌شود (مشابهِ
  خطای چک‌اوتِ سبد). تستِ Vitest/MSW + E2Eِ سخت‌گیرانه (CRUD، ورودیِ نامعتبر، مرزِ سقفِ
  ۲۰ آدرس، ایزولاسیونِ بین‌کاربری).
- [x] **چک‌اوتِ چندمرحله‌ای با آدرسِ ارسال** — ADR 0032. صفحهٔ `/checkout` (لینک از سبد،
  غیرفعال وقتی ردیفِ ناموجود هست) با دو مرحله: (۱) انتخابِ آدرس از آدرس‌بوک (پیش‌فرض
  از پیش انتخاب‌شده؛ اگر آدرسی نباشد فرمِ افزودنِ درون‌جا) و (۲) بازبینی + «ثبت سفارش».
  سفارش یک **اسنپ‌شاتِ آدرس** می‌گیرد (کپی از آدرس‌بوک در لحظهٔ ثبت — نه FK؛ ویرایش/حذفِ
  بعدیِ آدرس تاریخِ سفارش را بازنمی‌نویسد، دقیقاً مثلِ قیمت). `PlaceOrder` آدرس را از
  پورتِ باریکِ `AddressReader` (owner-scoped) پیش از Unit of Work حل می‌کند؛ آدرسِ
  متعلق به کاربرِ دیگر یا ناموجود ۴۰۰ می‌شود (بدونِ لوِ وجود → IDOR ناممکن). آدرسِ
  اسنپ‌شات‌شده در صفحهٔ تأییدِ سفارش نمایش داده می‌شود. seedِ E2E یک آدرسِ پیش‌فرضِ ماندگار
  برای شاپر می‌کارد که چک‌اوت به آن ارسال می‌کند و اسپکِ آدرس‌بوک هرگز حذفش نمی‌کند
  (بدونِ race بینِ اسپک‌ها). تستِ Vitest/MSW + E2Eِ سخت‌گیرانه (انتخابِ آدرس→ثبت→آدرسِ
  اسنپ‌شات→oversell روی مرحلهٔ بازبینی→IDOR). ⏳ باقی: خریدِ مهمان (اسلایسِ جدا).
- [x] **صفحهٔ تأیید و جزئیاتِ سفارش + timeline وضعیت + فهرستِ سفارش‌ها + لغو** — ADR 0030.
  دکمهٔ «ثبت سفارش» در سبد (غیرفعال وقتی ردیفِ ناموجود هست)، صفحهٔ `/orders/<number>` با
  timelineِ وضعیت و **لغوِ درون‌صفحه‌ای (بدونِ dialogِ مرورگر)**، و فهرستِ `/orders`؛ روی
  کلاینتِ API تایپ‌دار، RTL/جلالی، پول از منبعِ حقیقتِ سرور (بدونِ بازمحاسبه). تستِ
  Vitest/MSW + E2Eِ سخت‌گیرانه (خرید→سفارش→لغو→IDOR→oversell).
- [x] **پنلِ سفارشِ دستی + پیش‌فاکتورِ چاپی (staff)** — ADR 0036. فرمِ `/admin/orders/new`
  (کانال، ردیف‌های sku+تعداد، آدرسِ درون‌جا) و صفحهٔ چاپیِ
  `/admin/orders/<number>/pre-invoice` (شماره، تاریخِ جلالی، آدرسِ ثبت‌شده، جدولِ اقلام،
  جای‌خالیِ مالیات، مبلغِ نهایی؛ چاپ با `window.print()` و مخفی‌سازیِ کنترل‌ها با
  `@media print`؛ پول از منبعِ حقیقتِ سرور). لینک در نوارِ ادمین. تستِ Vitest/MSW + E2E.

**خروجی فاز ۳:** ✅ **کامل** — چرخهٔ کاملِ سبد → چک‌اوت → سفارش (کاربر و مهمان)، آدرس‌بوک،
ادغامِ سبدِ مهمان هنگامِ ورود، و سفارشِ دستی/پیش‌فاکتورِ staff، همگی با تستِ واحد روی
use-caseها (fake repo)، integrationِ واقعیِ DB، و E2Eِ full-stack قابلِ‌مشاهده در ویترین/پنل.
تنها معوقِ فاز ۳ انتشارِ رویداد روی event bus بود که در فاز ۴ (ADR 0041) تحویل شد.

---

## فاز ۴ — پرداخت (Payments)

> با تأکید بر آبستره‌سازی درگاه — حیاتی برای ایران.

- [x] **بنیانِ پرداخت + پرداخت در محل (COD)** — ADR 0037، اسلایسِ اولِ فاز. context جدیدِ
  `payment` (دامنه/اپلیکیشن/زیرساخت/رابط، Clean Architecture کامل): اگریگیتِ `Payment` با
  **state machine** (`pending→{authorized,captured,failed,cancelled}`, `authorized→
  {captured,voided,failed}`, `captured→refunded`)، value objectهای `Money` (`Decimal` — نه
  float) و `PaymentReference`/`OrderRef`ِ مبهم. **پورتِ `PaymentGateway` + رجیستریِ
  pluggable** (`PaymentGatewayRegistry`) — همان seamی که درگاه‌های بعدی به آن وصل می‌شوند —
  با آداپترِ `CashOnDeliveryGateway`. use caseِ `InitiatePayment` (مبلغ **از total سفارش**
  گرفته می‌شود، نه از کلاینت؛ owner-scoped برای کاربر/مهمان؛ اتمیک؛ auditِ
  `payment.initiated`) + خواندنی‌های `GetMyPayment`/`GetPaymentForOrder`. **حداکثر یک
  پرداختِ فعال به‌ازای هر سفارش** با partial unique constraintِ Postgres (ضدِ دوباره‌ثبت زیرِ
  هم‌زمانی). endpointهای `AllowAny`ِ owner-scoped: `POST payments/`،
  `GET payments/for-order/<number>/`، `GET payments/<reference>/` (بدونِ idِ مالک در URL →
  IDOR ناممکن). روش‌های `online`/`card_to_card` شناخته‌شده ولی بدونِ آداپتور → ۴۰۰. UI:
  انتخابِ روشِ پرداخت در چک‌اوت (COD فعال؛ آنلاین/کارت‌به‌کارت غیرفعال «به‌زودی») + بلوکِ
  پرداخت در صفحهٔ سفارش. پوششِ unit + integrationِ واقعیِ DB (COD، IDOR ۴۰۴، unsupported ۴۰۰،
  دوباره‌ثبت ۴۰۹، مهمان/کاربر) + تستِ فرانت + E2Eِ کاملِ COD (کاربر و مهمان). پوشش ~۱۰۰٪.
- [x] **درگاه آنلاین (زرین‌پال) + capture + وب‌هوکِ idempotent** — ADR 0038، اسلایسِ دومِ فاز.
  `OnlinePaymentGateway` (توسیعِ پورتِ پایه با `verify` — ISP)؛ آداپترِ `ZarinpalGateway`
  پشتِ پورتِ `HttpTransport` (تستِ واحد با transportِ جعلی، بدونِ شبکه) + `MockOnlineGateway`ِ
  DEBUG-only برای E2Eِ آفلاینِ قطعی. `Payment.gateway_reference` (authority)؛ use caseِ
  `CapturePayment` (قفلِ ردیف با `select_for_update`؛ **idempotent** — callbackِ تکراری no-op؛
  **هرگز به ریدایرکت اعتماد نمی‌کند و سمتِ سرور verify می‌کند**؛ اتمیک: capture → سفارش
  `paid` از طریقِ پلِ `PaidOrders` → auditِ `payment.captured`). endpointِ callback
  (`GET payments/callback/`) = وب‌هوک: idempotent، capture را به تسکِ Celery
  (`capture_online_payment`) می‌سپارد و مرورگر را به صفحهٔ سفارش redirect می‌کند؛ Celery در
  dev/test **eager** (نتیجهٔ فوری، E2E قطعی) و در production با workerِ واقعی async. UI:
  فعال‌سازیِ روشِ آنلاین در چک‌اوت، ریدایرکت به درگاه، و بازگشت به صفحهٔ سفارش (paid/failed).
  پوششِ unit + integrationِ واقعیِ DB (فلوِ کاملِ callback، idempotency، NOK، تلاشِ دوباره،
  authorityِ نامعتبر) + تستِ فرانت + E2Eِ کامل (پرداختِ آنلاین/لغو در درگاه). پوشش ~۱۰۰٪.
- [~] authorize/void (زرین‌پال مدلِ request→verify=capture دارد؛ authorize/void برای
  درگاه‌های کارتی در اسلایسِ بعد) / [x] وب‌هوکِ idempotent با Celery _(بالا)_.
- [x] **کیف‌پول داخلی + بازپرداخت آنی به کیف‌پول** — ADR 0039، اسلایسِ سومِ فاز. context جدیدِ
  `wallet` (دامنه/اپلیکیشن/زیرساخت/رابط، Clean Architecture کامل): اگریگیتِ `Wallet` با موجودیِ
  تک‌ارزی و دفترِ append-only از `WalletTransaction` (با `balance_after`)، value objectِ `Money`
  (`Decimal` — نه float). `CreditWallet` **اتمیک**، **idempotent** با `source_reference` (بازپرداختِ
  تکراری دوباره اعتبار نمی‌دهد؛ با partial unique در دیتابیس)، قفلِ ردیف (`select_for_update`) و ساختِ
  lazyِ کیف‌پول، auditِ `wallet.credited` (موجودیِ قبل/بعد). use caseِ `RefundPayment` در context
  پرداخت (مثلِ پلِ `PaidOrders`): قفلِ پرداخت با reference (اقدامِ **staff**، نه owner-scoped)،
  idempotent روی `captured→refunded`، اعتبار به کیف‌پولِ خریدار از طریقِ پورتِ `WalletCredit`، auditِ
  `payment.refunded` — همه در یک تراکنش. پرداختِ غیرِ captured → ۴۰۹؛ پرداختِ مهمان (بدونِ کیف‌پول) →
  ۴۰۹. endpointها: `GET wallet/` (**فقط احرازهویت‌شده**، owner از کاربر، بدونِ idِ مالک → IDOR ناممکن)؛
  `POST payments/<reference>/refund/` (`manage_orders`؛ غیرِ staff → ۴۰۳). UI: صفحهٔ **کیف‌پول** در
  ویترین + کنترلِ بازپرداختِ staff روی بلوکِ پرداختِ سفارش. پوششِ unit + integrationِ واقعیِ DB + تستِ
  فرانت + E2Eِ کامل (خرید→پرداختِ آنلاین→capture→بازپرداختِ staff→اعتبارِ کیف‌پول؛ و ۴۰۳ برای غیرِ staff).
  پوشش ~۱۰۰٪. معوق: دو edgeِ هم‌زمانیِ نادر که یکپارچگی را حفظ می‌کنند (در `ISSUES.md`).
- [x] **پرداخت با کیف‌پول (`debit`)** — ADR 0040، اسلایسِ چهارمِ فاز. کیف‌پول یاد می‌گیرد که
  خرج کند: `Wallet.debit` (بدونِ overdraft؛ `InsufficientWalletFundsError` پیش از هر حرکت)،
  `Money.subtract`/`covers`، و use caseِ `DebitWallet` (اتمیک، **idempotent** با `source_reference`،
  قفلِ ردیف، auditِ `wallet.debited`). use caseِ اختصاصیِ `PayWithWallet` (context پرداخت): در یک
  تراکنش سفارش را owner-scoped حل می‌کند، مبلغ را از جمعِ سفارش می‌گیرد، کیف‌پول را از طریقِ پورتِ
  `WalletDebit` بدهکار می‌کند، پرداخت را **آنی capture** می‌کند و سفارش را از طریقِ پلِ `PaidOrders`
  «paid» می‌کند؛ `WalletDebitAdapter` خطای کیف‌پول را به `InsufficientWalletBalanceError`ِ پرداخت
  ترجمه می‌کند. مهمان → ۴۰۹ (`WalletPaymentRequiresUserError`)؛ موجودیِ ناکافی → ۴۰۹. transport:
  همان `POST payments/` با dispatch بر اساسِ method. UI: گزینهٔ کیف‌پول در چک‌اوت فقط برای کاربرِ
  واردشده و فقط وقتی موجودی کفافِ سفارش را می‌دهد (مبلغ = مقدارِ سرور، نه بازمحاسبه). پوششِ unit +
  integrationِ واقعیِ DB + تستِ فرانت + E2Eِ کامل (تأمینِ اعتبار با بازپرداخت → پرداختِ سفارشِ جدید
  با کیف‌پول → سفارشِ paid، موجودی صفر؛ و نبودِ گزینه پس از خرجِ موجودی).
- [x] **رویدادهای دامنه‌ای روی event bus** — ADR 0041، اسلایسِ پنجمِ فاز (معوقِ فاز ۳). یک
  seamِ **انتشار** (`EventPublisher`) + رویدادهای typedِ `OrderPlaced`/`PaymentCaptured`
  (اگریگیتِ `DomainEvent`ِ مشترک، pure Python؛ `to_log` عمداً بدونِ مبلغ و بدونِ ownerِ خام).
  آداپترِ `DjangoEventPublisher` تحویل را به **بعد از commit** (`transaction.on_commit`) موکول
  می‌کند: رویداد داخلِ تراکنشِ use case منتشر می‌شود، پس یک سفارش/پرداختِ rollback‌شده هیچ side
  effectی را آتش نمی‌کند. به `PlaceOrder`/`CreateManualOrder` (→ `OrderPlaced`) و
  `CapturePayment`/`PayWithWallet` (→ `PaymentCaptured`، دقیقاً یک‌بار به‌ازای هر capture واقعی،
  idempotent) سیم‌کشی شد. مصرف‌کننده‌ها (اعلان/وب‌هوک/انجامِ سفارش) به فازهای بعد سپرده شدند —
  این اسلایس فقط seamِ انتشار را می‌سازد. پوششِ unit + integrationِ واقعیِ تراکنش (تحویلِ
  بعد از commit، دورانداختن روی rollback، آتش‌شدنِ فوری بیرونِ تراکنش). بک‌اندی محض، بدون UI.
- [x] **کارت‌به‌کارت (واریزِ دستی، تأییدِ staff)** — ADR 0042، اسلایسِ ششمِ فاز. جریان: خریدار
  `card_to_card` را انتخاب می‌کند → پرداختِ `pending` (بدونِ درگاه، مثلِ COD) → خریدار مبلغ را به
  کارتِ فروشگاه واریز و **شماره پیگیری** را ثبت می‌کند (`SubmitCardToCardReference`، owner-scoped،
  قفلِ ردیف، یک‌بار) → **staff** واریز را بررسی و `ConfirmCardToCardPayment` (capture → سفارش
  `paid` → رویدادِ `PaymentCaptured` → auditِ `payment.captured`) یا `RejectCardToCardPayment`
  (fail → آزادسازیِ سفارش) می‌کند؛ هر دو `manage_orders`، با reference، idempotent. تأیید بدونِ
  شماره پیگیریِ ثبت‌شده رد می‌شود (۴۰۹). `Payment.transfer_reference` (ستونِ nullable + مهاجرت).
  **کارتِ مقصد per-channel** از تنظیمات (`PAYMENT_CARD_TO_CARD` با کلیدِ slugِ کانال) از طریقِ پورتِ
  `CardToCardDirectory` (`PayableOrder.channel`)؛ `GetCardToCardInstructions`ِ owner-scoped آن را
  به خریدار می‌دهد (هرگز از کلاینت). endpointها: `GET .../card-to-card/`، `POST .../transfer-reference/`
  (owner)، `POST payments/<ref>/confirm|reject/` (staff). UI: فعال‌سازی در چک‌اوت + بلوکِ کارت‌به‌کارت
  در صفحهٔ سفارش (نمایشِ کارت + فرمِ ثبتِ شماره + «در انتظارِ تأیید» + کنترلِ تأیید/ردِ staff). پوششِ
  unit + integrationِ واقعیِ DB (جریانِ کامل، مرزهای ۴۰۳/۴۰۴/۴۰۹، کانالِ بدونِ کارت) + تستِ فرانت +
  E2Eِ کامل (خریدار ثبت می‌کند → غیرِ staff نمی‌تواند تأیید کند ۴۰۳ → staff تأیید → سفارش paid). ~۱۰۰٪.
  معوق: صفِ بازبینیِ اختصاصیِ staff برای پرداخت‌های کارت‌به‌کارتِ در انتظار (مثلِ وضعیتِ فعلیِ refund).
- [x] **نمای «در انتظارِ تأییدِ» پرداختِ آنلاین (polling)** — ADR 0043، اسلایسِ هفتمِ فاز. یک اسلایسِ
  فقط-فرانت: در پروडاکشن `capture_online_payment` روی workerِ async اجرا می‌شود، پس پنجره‌ای هست که
  خریدار به صفحهٔ سفارش برگشته ولی پرداختِ آنلاین هنوز `pending` است. بلوکِ پرداخت حالا فقط برای یک
  پرداختِ **آنلاینِ در حالِ settle** (`isSettlingOnline`) خودکار refetch می‌کند: **کران‌دار**
  (`ONLINE_POLL_INTERVAL_MS`=۲ث تا سقفِ `ONLINE_POLL_MAX_ATTEMPTS`=۱۰)، **خود-پایان‌پذیر** (به‌محضِ
  رسیدن به `captured`/`failed` بنر محو و وضعیتِ نهاییِ سرور نمایش داده می‌شود — هیچ استنتاجِ سمتِ
  کلاینت)، و **قابلِ‌بازیابی** (پس از اتمامِ تلاش‌ها دکمهٔ «بررسی دوباره»). بنرِ `OnlineAwaitingBanner`
  با اسپینر و `role="status" aria-live="polite"`. بدونِ سطحِ جدیدِ بک‌اند و بدونِ حرکتِ پولِ جدید. پوششِ
  تستِ کامپوننتی (نمایش برای settle، توقف و پاک‌شدن پس از settle، عدمِ نمایش برای onlineِ capture‌شده و
  CODِ pending). E2Eِ اختصاصی ندارد: زیرِ Celeryِ eager (dev/test) captureِ آنلاین همگام است، پس حالتِ
  settle end-to-end قابلِ‌مشاهده نیست — پنجرهٔ async فقط در پروداکشن وجود دارد؛ E2Eِ موجودِ آنلاین
  (capture/لغو در درگاه، ADR 0038) دوباره اجرا و سبز ماند (بی‌رگرسیون از بازنویسیِ `PaymentSection`).
- (آماده‌سازی برای BNPL/اقساط در فاز پیشرفته).

**بخش UI/ویترینِ فاز ۴:**
- [x] فلوِ ریدایرکت به درگاه و بازگشت (callback) با حالت‌های موفق/ناموفق — ADR 0038. نمای «در
  انتظارِ تأیید» با pollِ کران‌دار روی صفحهٔ سفارش تحویل شد — ADR 0043 (در dev/test captureِ eager
  همگام است، پس بنر آنجا دیده نمی‌شود؛ پنجرهٔ settle فقط در پروداکشنِ workerِ async رخ می‌دهد).
- [x] UIِ **کیف‌پول** (موجودی، تراکنش‌ها، بازپرداخت به کیف‌پول) — ADR 0039. صفحهٔ کیف‌پول در
  ویترین (`/account/wallet`، لینک از هابِ حساب؛ موجودی و صورتِ تراکنش‌ها با تومان و تاریخِ جلالی) +
  کنترلِ «بازپرداخت به کیف‌پول»ِ staff روی بلوکِ پرداختِ سفارش.
- [x] انتخابِ روشِ پرداخت در چک‌اوت (COD، آنلاین و کارت‌به‌کارت فعال؛ کیف‌پول برای کاربرِ واردشده با
  موجودیِ کافی) + بلوکِ پرداخت در صفحهٔ سفارش (شاملِ بلوکِ کارت‌به‌کارت) — ADR 0037/0040/0042.

**خروجی فاز ۴:** پرداخت واقعی end-to-end با یک درگاه ایرانی در محیط تست، با فلوِ قابلِ‌مشاهده در ویترین.

---

## فاز ۵ — حمل‌ونقل، مالیات و موجودی پیشرفته (Fulfillment & Inventory)

- پورت/آداپتور حمل (نرخ ثابت/وزنی/جدولی + کریر/پست داخلی)، مناطق ارسال.
  - [x] **نرخِ ثابت (اسلایسِ اول)** — ✅ context جدیدِ `shipping` (پورت/آداپتور)، انتخابِ
    روشِ حمل در چک‌اوت، ثبتِ `CapturedShipping` روی سفارش و تغییرِ invariant به
    `total = Σلاین‌ها + هزینهٔ حمل` (ADR 0044).
  - [x] **مناطقِ ارسال (اسلایسِ دوم)** — ✅ نرخِ هر روش بر اساسِ **استانِ** مقصد resolve می‌شود:
    `ShippingZone`/`Destination`/`ZonedRate` + سرویسِ `resolve_zone` در دامنه، `SHIPPING_ZONES`
    و `zone_rates` در تنظیمات (پشتِ همان reader port)، و `quote` سمتِ سفارش که نرخ را از آدرسِ
    ثبت‌شده **دوباره سمتِ سرور resolve می‌کند** (نه از قیمتِ نمایش‌دادهٔ کلاینت). چوزرِ چک‌اوت با
    تغییرِ آدرس دوباره quote می‌گیرد (ADR 0045). نرخِ وزنی/جدولی، تطبیقِ سطحِ شهر، و پنلِ ادمینِ
    مناطق در اسلایس‌های بعدی.
  - [x] **نرخِ وزنی/جدولی + تطبیقِ سطحِ شهر + aliasِ استان (اسلایسِ پنجم)** — ✅ فیلدِ `weight_grams`
    per-variant به کاتالوگ اضافه شد (مدل + مهاجرتِ `catalog/0017` + API/فرمِ ادمین). value objectهای
    `WeightBracket`/`WeightTable` (بازهٔ inclusive یا overflow، مرتب و تک‌ارز) و `ShippingMethod.weight_table`
    اختیاری: روشِ وزنی `price` را به‌عنوانِ قیمتِ «از» نشان می‌دهد و `quote(weight)` نرخِ واقعی را از وزنِ سفارش
    می‌گیرد؛ یک روش یا zoned-flat است یا وزنی (ترکیبشان config bug و skip می‌شود). سفارش وزنِ کل را از پورتِ
    باریکِ `VariantWeightReader` (پلِ کاتالوگ) حساب و به quote می‌دهد؛ quote حالا **داخلِ تراکنش** resolve
    می‌شود (چون به سبد نیاز دارد). `ShippingZone.cities` اختیاری + `covers(Destination)` تطبیقِ شهر
    (zoneِ ریزِ شهری قبل از zoneِ استانی)؛ `SHIPPING_PROVINCE_ALIASES` نامِ لاتینِ استان را به canonical
    نگاشت می‌کند تا به همان zone برسد. همه پشتِ همان `ShippingMethodReader` port (ADR 0051). معوق: مدلِ
    DB-backed مناطق/روش‌ها + پنلِ ادمین (اسلایسِ مستقل)، جدولِ وزنِ per-zone، و وزنِ حجمی.
- چاپ لیبل و رهگیری، تحویل محلی/حضوری (BOPIS).
  - [x] **انجامِ سفارش: رهگیریِ دستی + برچسبِ چاپی + BOPIS (اسلایسِ چهارم)** — ✅ ماشینِ حالتِ سفارش
    شاخهٔ pickup گرفت: حالت‌های `READY_FOR_PICKUP`/`PICKED_UP` و گذارهای
    `PAID→{FULFILLED, READY_FOR_PICKUP, CANCELLED}`، `READY_FOR_PICKUP→{PICKED_UP, CANCELLED}`.
    value objectِ `Fulfillment` (carrier/tracking_number/tracking_url؛ اسنپ‌شاتِ ثبت‌شده هنگامِ ارسال)،
    `CapturedShipping.is_pickup`، و `ShippingMethod.is_pickup` در context حمل (پیکربندیِ `"pickup": true`،
    روشِ رایگان). آدرسِ سفارش حالا **اختیاری** است (سفارشِ حضوری آدرس ندارد)؛ چک‌اوت بر اساسِ نوعِ روش
    شاخه می‌شود (pickup آدرس نمی‌گیرد؛ روشِ ارسالیِ بدونِ آدرس رد می‌شود). use caseهای staff
    (`manage_orders`، row-lock با `get_for_update_any`، audited): `ShipOrder` (روشِ pickup را رد می‌کند→۴۰۹)،
    `MarkOrderReadyForPickup`، `ConfirmOrderPickup`؛ endpointها
    `POST /orders/<n>/{ship,ready-for-pickup,confirm-pickup}/` (روشِ اشتباه/حالتِ غیرمجاز→۴۰۹، ناموجود→۴۰۴؛
    auditِ `order.shipped`/`ready_for_pickup`/`picked_up`). ستون‌های مدل + مهاجرتِ `order/0007`. UI:
    تایم‌لاینِ دوشاخه، نمایشِ carrier+tracking (لینک) پس از ارسال، نوتِ pickup، کنترل‌های staff (فرمِ ارسال +
    «چاپ برچسب»، آماده/تأییدِ تحویل)، و صفحهٔ **برچسبِ چاپیِ ارسال** (`/manage/orders/<n>/label`). API واقعیِ
    کریر، صفِ اختصاصیِ انجامِ staff، و چک‌اوتِ pickup-first (بدونِ گامِ آدرس) معوق (ADR 0050).
- **موجودی چندمنبعی (MSI):** منبع‌ها/stock، رزرو هنگام چک‌اوت، الگوریتم انتخاب منبع.
  - [x] **MSI + رزرو در چک‌اوت (اسلایسِ اول موجودی)** — ✅ context جدیدِ `inventory`
    (Clean Architecture کامل) که مرجعِ موجودی است: `StockSource` (انبار) و
    `StockLevel` per-source با شمارندهٔ `on_hand`/`reserved` مجزا و invariant `reserved ≤ on_hand`
    (CheckConstraint در DB به‌عنوانِ backstop). سرویس‌های دامنه: `available_to_promise` و
    `plan_reservation` (بیشترین-در-دسترس اول) و `plan_release` (بیشترین-رزرو اول). چک‌اوت از
    «کسرِ on-hand» به **«رزرو»** تغییر کرد (فیزیکی دست‌نخورده تا fulfilment در فاز ۶؛ لغوِ سفارش =
    آزادسازیِ رزرو)، همه اتمیک و با قفلِ ردیف (`select_for_update`) روی سطرهای level علیهِ
    فروشِ بیش‌ازموجودی. مهاجرتِ داده‌ایْ `catalog_variant_stock` را در منبعِ پیش‌فرضِ `main` fold
    کرد و آن جدولِ قدیمی حذف شد؛ `DjangoStockRepository` کاتالوگ (رابطِ get/set/adjust بدونِ تغییر) و
    پورتِ `Inventory` سفارش (که حالا reserve/release را پل می‌زند) روی مدلِ جدید سوار شدند و
    در-دسترس‌بودنِ ویترین به `available > 0` سوییچ کرد (ADR 0047). APIِ ادمینِ منابع/سطوح، انتخابِ منبع
    فراتر از highest-available، و اتصالِ scope انبار در اسلایس‌های بعدی.
- آستانه و هشدار موجودی، backorder.
  - [x] **آستانه/هشدارِ موجودی + backorderِ opt-in (اسلایسِ سوم موجودی)** — ✅ سیاستِ فروشِ
    per-variant در `StockPolicy`/`StockPolicyModel` (یک ردیف per SKU): `backorderable`،
    `low_stock_threshold` (۰ = غیرفعال)، و شمارندهٔ `backordered` (تعهد بدونِ پشتوانهٔ فیزیکی).
    invariantِ سختِ اسلایسِ ۱ دست‌نخورده می‌ماند: رزروِ فیزیکی هنوز `reserved ≤ on_hand`
    (CheckConstraint بدونِ تغییر) و سرریزِ backorder روی **policy** ردگیری می‌شود، نه روی level —
    پس backorder هرگز level را از موجودی فیزیکی رد نمی‌کند. `plan_reservation` حالا `backorderable`
    می‌گیرد و `ReservationPlan` (لاین‌ها + backordered) برمی‌گرداند؛ واریانتِ غیرbackorderableِ کم‌موجودی
    مثلِ قبل کامل رد می‌شود، و backorderable همهٔ موجودیِ فیزیکی را رزرو و کسری را backorder می‌کند.
    آزادسازی اول backorder را می‌بندد بعد فیزیکی. هشدارِ کم‌موجودی رویدادِ ساختاریافتهٔ `stock_low`
    (بعد از هر reserve/set/adjust که available را ≤ آستانه بگذارد). در-دسترس‌بودنِ ویترین یک
    variantِ backorderable را حتی با availableِ صفر buyable می‌داند. سطحِ ادمین:
    `GET/PUT /inventory/policies/<sku>/` (config سراسری → مجوزِ سراسریِ `manage_stock_source`؛
    SKU با کاتالوگ اعتبارسنجی می‌شود؛ آستانهٔ منفی→۴۰۰؛ auditِ `inventory.policy_set`). backend-only؛
    کانالِ اعلانِ کم‌موجودی و نمایشِ backorder/ETA در PLP/PDP معوق (ADR 0049).
- پورت/آداپتور مالیات، کلاس و منطقه‌ی مالیات، نمایش با/بدون مالیات.
  - [x] **مالیات بر ارزش افزوده per-channel (اسلایسِ اول مالیات)** — ✅ context جدیدِ `tax`
    (پورت/آداپتور): `TaxRate`/`Money` + سرویسِ `calculate_tax` در دامنه (اولین جای ضربِ پول در
    کسر، با گِردکردنِ صریحِ `ROUND_HALF_UP` تا ۴ رقمِ اعشار)، `TaxRateReader` + use caseهای
    `GetTaxRate`/`CalculateTax`، `SettingsTaxRateReader` روی `TAX_RATES` (کلیدِ slugِ کانال)، و
    `GET /tax/rate/` عمومی. سفارش مالیات را روی **زیرمجموعهٔ کالاها + ارسال** از طریقِ پورتِ باریکِ
    `TaxCalculator` (پلِ `ConfiguredTaxCalculator`) حساب و به‌صورتِ `CapturedTax` ثبت می‌کند؛
    invariant به `total = Σلاین‌ها + ارسال + مالیات` تغییر کرد (مالیات اختیاری → `None` برای کانالِ
    بدونِ مالیات و سطرهای قدیمی؛ ستون‌های `tax_amount`/`tax_rate` + مهاجرتِ backfill). مبلغِ مالیات را
    tax context محاسبه می‌کند و order هرگز از rate بازمحاسبه نمی‌کند. UI: خطِ مالیات در بریک‌داونِ
    چک‌اوت/سفارش/پیش‌فاکتور (پیش‌نمایشِ مالیات با همان ریاضیِ صحیحِ سمتِ سرور؛ مقدارِ نهایی همان سرور).
    dev/E2E نرخِ ۹٪ برای `ir-main`؛ pytest بدونِ `TAX_RATES` تا سایرِ تست‌ها بی‌مالیات بمانند (ADR 0046).
    معوق: کلاس‌های مالیاتِ per-product، مناطقِ مالیاتی، معافیت، و نمایشِ قیمتِ با/بدونِ مالیات در PLP/PDP.
  - [x] **کلاس‌های مالیاتی + معافیت + نمایشِ با-مالیات در PLP/PDP (اسلایسِ ششم مالیات)** — ✅ فیلدِ
    `tax_class` روی محصول (پیش‌فرض `standard`؛ مدل + مهاجرتِ `catalog/0018` + API/فرمِ ادمین) که یک
    کانال آن را به نرخ نگاشت می‌کند. `TaxRateReader.rate_for(channel, tax_class)` + use caseها
    tax_class می‌گیرند؛ `TAX_CLASSES[channel]` نرخِ هر کلاس (۰ = مالیاتِ صفر، مجاز)، کلاسِ `standard`
    به `TAX_RATES` fallback می‌کند، و هر کلاسِ نگاشت‌نشدهٔ دیگر **معاف** است (`None`). چک‌اوت مالیات را
    **هر لاین بر اساسِ کلاسِ محصول** (لاینِ معاف صفر) + ارسال با کلاسِ standard حساب و جمع می‌کند؛
    `CapturedTax.rate` نرخِ سرآیند (بیشترین) است و مبلغ مرجعِ دقیق. پورتِ باریکِ `ProductTaxClassReader`
    (پلِ کاتالوگ). ویترین: `PriceSummary.tax_rate` و پاکتِ واریانت‌های PDP نرخِ کلاسِ محصول را می‌دهند و
    کارت/PDP نوتِ «قیمت شاملِ X٪ مالیات» را نشان می‌دهند (محصولِ معاف بدونِ نوت) (ADR 0052). معوق: مناطقِ
    مالیاتی، مدلِ نرخِ ادمین، بریک‌داونِ چند-نرخی روی سفارش، و پیش‌نمایشِ کلاس‌آگاهِ چک‌اوت.
- **اتصالِ scope دسترسی به انبار** (پیگیریِ معوقِ فاز ۱؛ همراه با ساختِ context انبار).
  - [x] **APIِ ادمینِ انبار + اتصالِ scope (اسلایسِ دوم موجودی)** — ✅ سطحِ staffِ مدیریتِ انبار
    روی همان الگویِ دولایهٔ کانال: مجوزِ `manage_stock_source` (متعلق به context موجودی، روی
    `Meta.permissions` مدلِ منبع تا guardian بتواند per-object bind کند) + نقشِ `inventory_admin`؛
    `AccessControlGateway.grant_stock_source_management`/`can_manage_stock_source` و پیاده‌سازیِ
    guardian؛ use caseِ `GrantStockSourceManagement` (کنارِ grant کانال) + `POST
    /access/stock-source-grants/` (پشتِ `manage_access`). endpointها: `GET/POST
    /inventory/sources/` (لیست=auth، ساخت=مجوزِ سراسری؛ کدِ تکراری→۴۰۹، کد/نامِ نامعتبر→۴۰۰) و
    `GET/PUT/PATCH /inventory/sources/<code>/stock/<sku>/` (خواندن/تنظیم/تعدیلِ on-hand در یک منبع؛
    نوشتن سراسری **یا** با scope همان منبع — view منبع را resolve و `check_object_permissions` را با
    `StockSource` صدا می‌زند؛ کمتر از reserved / برداشتِ بیش‌ازموجودی→۴۰۹؛ منبع/واریانتِ ناموجود→۴۰۴).
    اعتبارسنجیِ SKU از طریقِ کاتالوگ تا level یتیم ساخته نشود. تغییرِ فیزیکیِ موجودی auditِ before/after
    دارد (`inventory.stock_set`/`stock_adjusted`/`source_created`). این اسلایس backendـه؛ پنلِ UIِ انبار
    معوق (ADR 0048).

**بخش UI/ویترینِ فاز ۵:**
- انتخابِ روشِ ارسال و نمایشِ هزینه/زمان در چک‌اوت؛ تعریفِ مناطقِ ارسال در پنل.
- نمایشِ موجودی/در دسترس‌بودن در PLP/PDP؛ حالتِ backorder.
- پنلِ ادمینِ موجودیِ چندمنبعی (MSI)، آستانه/هشدار، و گزینهٔ BOPIS.

**خروجی فاز ۵:** سفارش با محاسبه‌ی درست ارسال/مالیات و رزرو موجودی چندانباره، قابلِ‌مشاهده در چک‌اوت.

---

## فاز ۶ — انجام سفارش، مرجوعی و پنل عملیات (Operations / OMS)

> هدف: پاسخ به «افرادی با سطوح دسترسی مختلف، سفارش‌ها را پردازش کنند».

- خط لوله‌ی پردازش سفارش (۱۲ مرحله) با نگاشت به نقش‌ها (طبق گزارش ویژگی‌ها).
- **مرجوعی/RMA:** درخواست → تأیید → لیبل → دریافت → بازرسی → restock → بازپرداخت.
- بازپرداخت کامل/جزئی به روش اولیه یا اعتبار فروشگاهی.
- audit log کامل روی همه‌ی انتقال‌ها + رعایت scope سطح‌شیء.

**بخش UI/ویترینِ فاز ۶ (داشبوردِ عملیات — منتقل‌شده به همین‌جا):**
- **داشبوردِ عملیات:** لیست/فیلترِ سفارش، جزئیات، timeline، انجامِ جزئی/کامل — نقش‌محور و با رعایتِ scope سطح‌شیء.
- فلوِ مرجوعی/RMA در پنلِ عملیات و سمتِ مشتری.
- UIِ بازپرداخت (کامل/جزئی، روشِ اولیه یا اعتبارِ فروشگاهی).

**خروجی فاز ۶:** تیم چندنقشی می‌تواند چرخه‌ی کامل سفارش تا مرجوعی را از طریقِ داشبورد اداره کند.

---

## فاز ۷ — قیمت‌گذاری پیشرفته، پروموشن و بازاریابی (Pricing & Marketing)

- موتور تخفیف: قانون قیمت کاتالوگ vs سبد، کوپن (تولید دسته‌ای، stacking، انقضا).
- BOGO/Buy-X-Get-Y، فلش‌سیل، آستانه‌ی خرید.
- کارت هدیه، اعتبار فروشگاهی، **باشگاه وفاداری/امتیاز** (tier، گیمیفیکیشن).
- بازیابی سبد رهاشده (ایمیل/پیامک چندمرحله‌ای)، فلوهای back-in-stock.
- نظرات و امتیاز + پرسش‌وپاسخ، توصیه‌گر محصول (قانون‌محور، سپس AI).
- SEO (متا/slug/redirect/canonical/JSON-LD/sitemap).

**بخش UI/ویترینِ فاز ۷ (شاملِ wishlist منتقل‌شده از فاز ۸):**
- پنلِ تخفیف/کوپن (تولیدِ دسته‌ای، stacking، انقضا)، BOGO/فلش‌سیل.
- UIِ کارتِ هدیه/اعتبارِ فروشگاهی، باشگاهِ وفاداری/امتیاز.
- **wishlist**، نظرات و امتیاز + پرسش‌وپاسخ، فلوِ back-in-stock، بازیابیِ سبدِ رهاشده.
- رندرِ SEO سمتِ فرانت (متا/JSON-LD/sitemap).

**خروجی فاز ۷:** ابزارهای رشد فروش فعال و قابلِ‌مشاهده در ویترین/پنل.

---

## فاز ۸ — بلوغ و تم‌پذیریِ White-Label (Storefront Maturity & Theming)

> هدف بدون تغییر: قلبِ «با تغییر UI/UX هر چیزی بفروش». اما **صفحاتِ هر قابلیت در
> فازِ خودش ساخته شده‌اند**؛ این فاز سیستمِ تم‌پذیری و بلوغِ نهاییِ ویترین را روی همان
> بنیادِ توکنِ سه‌لایهٔ فاز ۰ کامل می‌کند (هیچ آیتمی حذف نشد — فقط صفحاتِ per-feature
> به فازهای خودشان منتقل شدند).

- **سیستمِ تحویلِ تم:** build-time per-tenant + runtime (تزریقِ CSS variable بر اساسِ دامنه/زیردامنه) روی بنیادِ توکنِ فاز ۰.
- **جست‌وجوی هوشمند** (Typesense/Meilisearch) + InstantSearch — ارتقاءِ کاملِ جست‌وجوی پایهٔ فاز ۲.
- PWA/موبایل، SSR/ISR برای SEO.
- **ساخت ۲–۳ تمِ نمونه** (قهوه / لوازم آرایشی / لوازم خودرو) برای اثباتِ White-Label.
- بازبینیِ نهاییِ i18n/RTL/جلالی روی کلِ ویترین.

**خروجی فاز ۸:** یک نصب، چند ویترین کاملاً متفاوت فقط با تغییر تم/پیکربندی.

---

## فاز ۹ — تحلیل، گزارش و CRM (Analytics & CRM)

- داشبورد بلادرنگ (فروش، AOV، نرخ تبدیل، عملکرد محصول).
- گزارش‌ها: مشتری/cohort، موجودی (ABC)، کوپن، مالیات، سبد رهاشده، سود/مارجین (COGS).
- گزارش‌ساز سفارشی + اکسپورت زمان‌بندی‌شده.
- **CRM:** بخش‌بندی RFM، پروفایل ۳۶۰ مشتری، LTV.
- **تیکتینگ/پشتیبانی** omnichannel با context کامل.

**بخش UI/ویترینِ فاز ۹:**
- داشبوردهای بلادرنگ + گزارش‌سازِ سفارشی + اکسپورتِ زمان‌بندی‌شده در پنل.
- پنل‌های CRM (RFM، پروفایلِ ۳۶۰ مشتری، LTV) و کنسولِ تیکتینگِ omnichannel.

**خروجی فاز ۹:** دید کامل کسب‌وکاری + ابزار پشتیبانی مشتری.

---

## فاز ۱۰ — قابلیت‌های پیشرفته (Advanced / آینده)

موارد high-value که پس از پایداری هسته اضافه می‌شوند (هرکدام UIِ خودش را در همان آیتم دارد):

- **اشتراک و پرداخت دوره‌ای** (selling plan، dunning، پورتالِ سلف‌سرویسِ مشتری).
- **B2B** (حساب شرکتی، RFQ، Net terms، کاتالوگ اختصاصی + پورتالِ B2B).
- **BNPL/اقساط** first-class (دیجی‌پی/اسنپ‌پی/ازکی‌وام).
- **مارکت‌پلیس چندفروشنده** + اپ/داشبورد فروشنده + کارمزد.
- کانال‌های فروش بیشتر (POS، مارکت‌پلیس‌ها، فید، اتصال به مقایسه‌گرهای قیمت).
- اتوماسیون گردش‌کار no-code (الگوی Shopify Flow).
- فریم‌ورک افزونه/وب‌هوک عمومی برای توسعه‌دهندگان ثالث.

---

## ترتیب وابستگی‌ها (خلاصه)

```
فاز ۰ (پایه + بنیادِ UI: توکنِ سه‌لایه، i18n/RTL/جلالی، کلاینتِ API تایپ‌دار)
   └─ فاز ۱ (هویت/RBAC/Channel)         + UIِ احراز هویت/پنلِ دسترسی
        └─ فاز ۲ (کاتالوگ)              + پنلِ ادمینِ کاتالوگ و ویترینِ PLP/PDP
             └─ فاز ۳ (سبد/سفارش)       + UIِ سبد/چک‌اوت
                  ├─ فاز ۴ (پرداخت)     + UIِ درگاه/کیف‌پول
                  ├─ فاز ۵ (حمل/مالیات/موجودی) + UIِ ارسال/موجودی
                  │    └─ فاز ۶ (عملیات/OMS/مرجوعی) + داشبوردِ عملیات
                  └─ فاز ۷ (پروموشن/بازاریابی)      + UIِ پروموشن/wishlist/نظرات
   فاز ۸ (تم‌پذیری/بلوغِ ویترین) ── سیستمِ تم، تم‌های نمونه، جست‌وجوی هوشمند، PWA/SEO
   فاز ۹ (تحلیل/CRM) ── پس از داده‌ی کافی (فاز ۶+)
   فاز ۱۰ (پیشرفته) ── پس از پایداری هسته
```

> نکته: از فاز ۰ به بعد، **UIِ هر فاز همراهِ همان فاز** ساخته می‌شود (روی بنیادِ توکن و
> کلاینتِ API تایپ‌دارِ فاز ۰). فاز ۸ دیگر «شروعِ UI» نیست، بلکه **کامل‌کنندهٔ
> تم‌پذیری و بلوغِ نهاییِ** ویترین است.

## معیار آمادگی برای production (MVP)

پایان **فاز ۶ + فاز ۸** = حداقل محصول قابل‌عرضه: کاتالوگ منعطف، سبد/چک‌اوت/سفارش، پرداخت ایرانی، حمل/موجودی، چرخه‌ی عملیات با نقش‌ها، و ویترین تم‌پذیر فارسی. چون UI اکنون در هر فاز ساخته می‌شود، تا رسیدن به این نقطه ویترینِ کاربردی به‌تدریج آماده است و فاز ۸ آن را به یک سیستمِ کاملِ تم‌پذیر ارتقا می‌دهد. فازهای ۷، ۹ و ۱۰ رشد و بلوغ‌اند.
