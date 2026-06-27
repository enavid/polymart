# مرحله ۱ — یادداشت منابع و لینک‌های تحقیق

> این فایل خروجی مرحله‌ی «جست‌وجو در اینترنت + بررسی پروژه‌ها و فروشگاه‌های بزرگ» است.
> همه‌ی لینک‌ها در یک جا جمع شده‌اند تا در مرحله‌ی بعد (گزارش ویژگی‌ها) به آن‌ها استناد شود.
>
> تاریخ گردآوری: ۲۰۲۶-۰۶-۲۷

فهرست منابع در چهار دسته سازماندهی شده است:

1. پلتفرم‌های تجاری بزرگ (Commercial platforms)
2. پروژه‌های اوپن‌سورس روی GitHub (Open-source projects)
3. پنل ادمین / CRM و سیستم سطح دسترسی (Admin / CRM / RBAC)
4. معماری مهندسی، تست، Docker، CI/CD و فرانت‌اند

---

## ۱. پلتفرم‌های تجاری بزرگ

### Shopify
- https://help.shopify.com/manual/products/variants/add-variants — محدودیت و مدل variant
- https://www.shopify.com/blog/2048-variants — افزایش تعداد variant به ۲۰۴۸
- https://help.shopify.com/manual/custom-data/metafields — متافیلدها (custom data)
- https://help.shopify.com/manual/custom-data/metaobjects — متاآبجکت‌ها
- https://shopify.dev/docs/apps/build/metafields — توسعه‌ی متافیلد
- https://help.shopify.com/manual/products/details/product-category — تاکسونومی استاندارد محصول
- https://www.shopify.com/blog/shopify-taxonomy — تاکسونومی Shopify
- https://help.shopify.com/manual/products/bundles/shopify-bundles — باندل محصولات
- https://shopify.dev/docs/apps/build/product-merchandising/bundles — API باندل
- https://help.shopify.com/manual/discounts — انواع تخفیف
- https://shopify.dev/docs/api/functions — Discount/Functions API (Rust/Wasm)
- https://shopify.dev/changelog/new-discount-function-api — تغییرات Discount Function
- https://help.shopify.com/manual/b2b/getting-started/features — قابلیت‌های B2B
- https://help.shopify.com/manual/products/gift-card-products/overview — کارت هدیه
- https://shopify.dev/docs/apps/build/purchase-options/subscriptions — اشتراک (subscriptions)
- https://apps.shopify.com/shopify-subscriptions — اپ اشتراک
- https://shopify.dev/docs/api/checkout-ui-extensions — افزونه‌ی UI چک‌اوت
- https://shopify.dev/changelog/introducing-checkout-extensibility — چک‌اوت قابل‌توسعه
- https://help.shopify.com/manual/payments/shopify-payments — درگاه پرداخت داخلی
- https://help.shopify.com/manual/payments/accelerated-checkouts — چک‌اوت سریع
- https://help.shopify.com/manual/payments/third-party-providers — درگاه‌های ثالث
- https://help.shopify.com/manual/shipping — حمل‌ونقل و انجام سفارش
- https://www.shopify.com/shipping — Shopify Shipping
- https://help.shopify.com/manual/taxes — مالیات
- https://help.shopify.com/manual/markets — چندارزی/چندزبانه (Markets)
- https://help.shopify.com/manual/promoting-marketing — بازاریابی
- https://help.shopify.com/manual/reports-and-analytics — گزارش و تحلیل
- https://help.shopify.com/manual/organization-settings/expansion-stores — چندفروشگاهی
- https://shopify.dev/docs/api/usage/limits — محدودیت API
- https://shopify.dev/docs/api/hydrogen — فریم‌ورک headless (Hydrogen)
- https://help.shopify.com/manual/your-account/users/roles — مدل نقش‌ها (roles)
- https://help.shopify.com/manual/your-account/users/roles/permissions/store-permissions — لیست دقیق سطوح دسترسی
- https://help.shopify.com/manual/fulfillment/managing-orders — مدیریت سفارش
- https://help.shopify.com/manual/fulfillment/managing-orders/order-status — وضعیت‌های سفارش
- https://help.shopify.com/manual/fulfillment/managing-orders/returns/creating-returns — مرجوعی/تعویض
- https://help.shopify.com/manual/fulfillment/managing-orders/returns/return-rules — قوانین مرجوعی

### BigCommerce
- https://support.bigcommerce.com/s/article/Variants-and-Modifiers — variant در برابر modifier
- https://developer.bigcommerce.com/docs/rest-catalog — REST Catalog API
- https://support.bigcommerce.com/articles/Public/Platform-Limits — محدودیت‌های پلتفرم
- https://support.bigcommerce.com/s/article/Price-Lists — لیست قیمت (Price Lists)
- https://www.bigcommerce.com/product/promos-and-coupons — پروموشن و کوپن
- https://github.com/bigcommerce/checkout-js — چک‌اوت اوپن‌سورس
- https://github.com/bigcommerce/checkout-sdk-js — Checkout SDK
- https://www.bigcommerce.com/payments — پرداخت
- https://support.bigcommerce.com/s/article/Shipping-Methods — روش‌های حمل
- https://developer.bigcommerce.com/docs/storefront/graphql — Storefront GraphQL
- https://catalyst.dev — Catalyst (Next.js headless)
- https://docs.bigcommerce.com/developer/docs/b2b-edition — B2B Edition
- https://support.bigcommerce.com/s/article/Multi-Storefront — چند ویترین (MSF)

### WooCommerce
- https://woocommerce.com/products/woocommerce/ — هسته
- https://woocommerce.com/products/woocommerce-subscriptions/ — اشتراک
- https://woocommerce.com/products/woocommerce-memberships/ — عضویت
- https://woocommerce.com/products/woocommerce-bookings/ — رزرواسیون
- https://woocommerce.com/products/product-bundles/ — باندل
- https://woocommerce.com/document/smart-dynamic-pricing/ — قیمت‌گذاری پویا
- https://woocommerce.com/products/woopayments/ — WooPayments
- https://wpml.org/documentation/related-projects/woocommerce-multilingual/ — چندزبانه/چندارزی
- https://woocommerce.com/products/woocommerce-points-and-rewards/ — باشگاه مشتریان
- https://woocommerce.com/document/woocommerce-analytics/ — تحلیل
- https://developer.woocommerce.com/docs/apis/rest-api/ — REST API
- https://woocommerce.com/document/webhooks/ — وب‌هوک

### Adobe Commerce / Magento
- https://experienceleague.adobe.com/en/docs/commerce-admin/b2b/introduction — مجموعه‌ی B2B
- https://experienceleague.adobe.com/en/docs/commerce-admin/inventory/basics/sources-stocks — موجودی چندمنبعی (MSI)
- https://experienceleague.adobe.com/en/docs/commerce-admin/marketing/promotions/cart-rules — قوانین قیمت سبد
- https://experienceleague.adobe.com/en/docs/commerce-admin/marketing/promotions/catalog-rules — قوانین قیمت کاتالوگ
- https://experienceleague.adobe.com/en/docs/commerce-admin/config/sales/delivery-methods — روش‌های ارسال
- https://experienceleague.adobe.com/en/docs/commerce-admin/live-search — جست‌وجوی هوشمند (Sensei)
- https://developer.adobe.com/commerce/webapi/graphql/ — GraphQL API
- https://developer.adobe.com/commerce/pwa-studio/ — PWA Studio
- https://mgt-commerce.com/tutorial/magento-2-website-store-view/ — سلسله‌مراتب website/store/store-view

### Salesforce Commerce Cloud
- https://help.salesforce.com/s/articleView?id=cc.b2c_product_types.htm — انواع محصول B2C
- https://help.salesforce.com/s/articleView?id=cc.b2c_campaigns_and_promotions.htm — کمپین و پروموشن
- https://www.salesforce.com/commerce/b2b-ecommerce — تجارت B2B
- https://www.salesforce.com/products/commerce-cloud/commerce-cloud-einstein — توصیه‌گر هوشمند Einstein
- https://developer.salesforce.com/docs/commerce/commerce-api/guide/why-use-scapi.html — SCAPI (headless)
- https://help.salesforce.com/s/articleView?id=cc.comm_om_oci.htm — مدیریت سفارش/موجودی (OMS/OCI)

### پلتفرم‌های ایرانی (مرجع بومی)
- https://en.wikipedia.org/wiki/Digikala — مدل مارکت‌پلیس دیجی‌کالا
- https://about.digikala.com/en/reports/ — گزارش‌ها، DigiClub، DigiPay (پرداخت اقساطی)
- https://cafebazaar.ir/app/ir.basalam.app — اپ خریدار باسلام
- https://cafebazaar.ir/app/ir.basalam.basalam — اپ فروشنده باسلام
- https://help.basalam.com — ساختار کارمزد
- https://crunchbase.com/organization/torob — ترب (مقایسه قیمت)
- https://pay.snapp.ir — اسنپ‌پی (BNPL/اقساط)
- https://shopfa.com — فروشگاه‌ساز ایرانی (شاپفا)
- https://portal.ir/ecommerce — فروشگاه‌ساز پورتال
- https://github.com/parsisolution/gateway — کتابخانه درگاه‌های پرداخت ایرانی
- https://github.com/dena-a/iran-payment — درگاه پرداخت ایرانی

---

## ۲. پروژه‌های اوپن‌سورس روی GitHub

### Python / Django (نزدیک‌ترین به استک ما)
- https://github.com/saleor/saleor — هسته‌ی headless با Django/GraphQL (~۲۳k ⭐) — **مهم‌ترین مرجع**
- https://docs.saleor.io — مستندات Saleor
- https://docs.saleor.io/developer/permissions — گروه‌های دسترسی، scope کانال، JWT
- https://docs.saleor.io/developer/extending/apps/overview — فریم‌ورک App و manifest
- https://docs.saleor.io/developer/extending/webhooks/overview — وب‌هوک sync/async
- https://docs.saleor.io/developer/channels/overview — مدل چندکاناله (Channels)
- https://github.com/saleor/storefront — ویترین Next.js (~۱.۵k ⭐)
- https://github.com/django-oscar/django-oscar — تجارت DDD با Django (~۶.۶k ⭐)
- https://django-oscar.readthedocs.io/en/latest/topics/customisation.html — fork اپ، dynamic class loading
- https://github.com/shuup/shuup — تجارت ماژولار چندفروشنده با Django (~۲.۴k ⭐)
- https://shuup.readthedocs.io/en/latest/ref/provides.html — رجیستری «Provides»

### Headless / JavaScript
- https://github.com/medusajs/medusa — تجارت headless تایپ‌اسکریپت، modules + workflows (~۳۴.۷k ⭐) — **بهترین مرجع Clean Architecture**
- https://docs.medusajs.com/learn/introduction/architecture — معماری چهارلایه
- https://docs.medusajs.com/learn/fundamentals/workflows — Workflow + الگوی saga/rollback
- https://github.com/RSC-Labs/medusa-rbac-public — RBAC اجتماعی
- https://github.com/vendure-ecommerce/vendure — تجارت GraphQL با NestJS (~۷–۸k ⭐)
- https://docs.vendure.io/guides/developer-guide/custom-permissions/ — مدل RBAC با `@Allow`
- https://docs.vendure.io/guides/core-concepts/channels/ — چندمستأجری با Channel
- https://github.com/vuestorefront/vue-storefront — Frontend-as-a-Service / Alokai (~۱۱k ⭐)
- https://docs.alokai.com/general/basics/architecture/ — معماری چهارلایه + anti-corruption layer

### Rails / PHP (فقط برای الگوهای معماری)
- https://github.com/spree/spree — Rails Engines، API-first (~۱۵.۵k ⭐)
- https://github.com/Sylius/Sylius — DDD نمونه با Symfony (~۸.۵k ⭐) — **مرجع تفکیک Domain/Application/Infrastructure**
- https://old-docs.sylius.com/en/1.6/book/architecture/architecture.html — معماری component/bundle + state machine
- https://github.com/bagisto/bagisto — Laravel، بسته‌محور (~۲۷.۵k ⭐)
- https://devdocs.bagisto.com/package-development/access-control-list.html — ACL غیرمتمرکز per-package

> توجه: Reaction Commerce (https://github.com/reactioncommerce/reaction) متوقف شده — فقط برای الگو، نه استفاده.

---

## ۳. پنل ادمین / CRM و سیستم سطح دسترسی (RBAC)

- https://docs.medusajs.com/user-guide/orders/fulfillments — انجام سفارش (pick/pack/ship)
- https://docs.medusajs.com/user-guide/orders/returns — مرجوعی/RMA
- https://docs.medusajs.com/resources/commerce-modules/order/return — مدل داده‌ی مرجوعی
- https://www.odoo.com/app/inventory-features — انبارداری/WMS (Odoo)
- https://www.odoo.com/app/crm — CRM (Odoo)
- https://mcpanalytics.ai/articles/ecommerce__generic__customers__rfm_segmentation — بخش‌بندی مشتری RFM
- https://www.klaviyo.com/uk/blog/what-is-an-ecommerce-crm — توابع اصلی CRM فروشگاهی
- https://hiverhq.com/blog/crm-ticket-system — تیکتینگ پشتیبانی + CRM
- https://www.netsuite.com/portal/resource/articles/erp/order-fulfillment.shtml — فرایند ۷ مرحله‌ای انجام سفارش
- https://last9.io/blog/getting-started-with-e-commerce-audit-logs/ — لاگ ممیزی (audit log)
- https://www.technaureus.com/blog-detail/django-object-level-permissions-guide — دسترسی سطح‌شیء با django-guardian
- https://www.django-rest-framework.org/api-guide/permissions/ — سطح دسترسی DRF
- https://testdriven.io/blog/django-permissions/ — مدل دسترسی Django
- https://www.permit.io/blog/how-to-implement-role-based-access-control-rbac-into-a-django-application — پیاده‌سازی RBAC در Django

---

## ۴. معماری مهندسی، تست، Docker، CI/CD و فرانت‌اند

### Clean Architecture / DDD در Python و Django
- https://www.cosmicpython.com/book/preface — کتاب «Architecture Patterns with Python» (مرجع اصلی Repository/UoW/Service Layer)
- https://www.cosmicpython.com/book/chapter_02_repository — فصل الگوی Repository
- https://github.com/cosmicpython — کد نمونه‌ی هر فصل
- https://jordifierro.dev/django-clean-architecture — لایه‌بندی عملی در Django
- https://medium.com/21buttons-tech/clean-architecture-in-django-d326a4ab86a9 — entities/interactors/repository
- https://shiladityamajumder.medium.com/clean-architecture-in-django-a-practical-real-world-project-structure-1f4c89e402f0 — ساختار پوشه domain/application/infrastructure/interface

### تست و TDD (بک‌اند)
- https://testdriven.io/courses/tdd-django/ — دوره‌ی کامل TDD با Django/DRF/Docker/pytest
- https://djangostars.com/blog/django-pytest-testing/ — راهنمای pytest/pytest-django
- https://dev.to/sherlockcodes/pytest-with-django-rest-framework-from-zero-to-hero-8c4 — pytest + DRF
- https://codezup.com/master-django-testing-pytest-and-factory-boy-strategies/ — factory_boy

### تست فرانت‌اند
- https://vitest.dev/guide/comparisons — Vitest در برابر Jest
- https://dev.to/agent-tools-dev/choosing-a-typescript-testing-framework-jest-vs-vitest-vs-playwright-vs-cypress-2026-7j9 — انتخاب فریم‌ورک تست
- https://getautonoma.com/blog/playwright-vs-cypress — Playwright در برابر Cypress

### Docker
- https://www.honeybadger.io/blog/docker-django-react/ — داکرایز Django + React
- https://github.com/farhad0085/django-postgres-nginx-redis-celery-react-docker — ریپوی مرجع استک کامل
- https://testdriven.io/courses/django-celery/docker/ — داکرایز Celery

### CI/CD (GitHub Actions)
- https://buildsmartengineering.substack.com/p/cicd-pipelines-for-django-testing — CI/CD برای Django
- https://oneuptime.com/blog/post/2026-01-15-cicd-pipelines-react-github-actions/view — CI/CD برای React
- https://github.com/github/awesome-copilot/blob/main/instructions/github-actions-ci-cd-best-practices.instructions.md — بهترین‌شیوه‌های GitHub Actions

### فرانت‌اند / تم‌پذیری White-Label
- https://github.com/vercel/commerce — Next.js Commerce، provider قابل‌تعویض (~۱۴.۱k ⭐)
- https://github.com/medusajs/nextjs-starter-medusa — استارتر کامل‌تر (~۲.۸k ⭐)
- https://ui.shadcn.com/docs/theming — توکن‌های معنایی با CSS variable
- https://tailwindcss.com/docs/theme — متغیرهای تم Tailwind v4
- https://www.maviklabs.com/blog/design-tokens-tailwind-v4-2026/ — design token مقیاس‌پذیر per-tenant
- https://tanstack.com/query/latest — TanStack Query (مدیریت داده سمت سرور)

### i18n / RTL / فارسی
- https://next-intl.dev/docs/usage/translations — i18n نیتیو Next.js + RTL
- https://flowbite.com/docs/customize/rtl/ — RTL با Tailwind (logical properties)
- https://github.com/fffaraz/awesome-persian — فونت Vazirmatn، ابزارها و کتابخانه‌های فارسی

---

## جمع‌بندی منابع

- **نزدیک‌ترین نقشه برای کپی‌کردن:** Saleor (دقیقاً همین استک Django + جداسازی دامنه از transport + Channels + گروه‌های دسترسی/JWT).
- **بهترین الگوی Clean Architecture:** Medusa (لایه‌ی Workflow/use-case + ایزوله‌سازی ماژول).
- **بهترین مدل RBAC:** Vendure (`@Allow`، secure-by-default) + Saleor (scope کانال).
- **بهترین انضباط معماری دامنه:** Sylius (تفکیک Domain/Application/Infrastructure + state machine).
- **بهترین مرجع فرانت white-label:** vercel/commerce + معماری توکن سه‌لایه Tailwind v4 + shadcn/ui.
- **مرجع نظری بک‌اند:** کتاب Cosmic Python (Repository، Unit of Work، Service Layer).
