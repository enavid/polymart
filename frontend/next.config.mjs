import createNextIntlPlugin from "next-intl/plugin";

// Single-locale (Persian) setup; per-tenant locales can be added in Phase 8.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
};

export default withNextIntl(nextConfig);
