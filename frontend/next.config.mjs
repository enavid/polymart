import createNextIntlPlugin from "next-intl/plugin";

// Single-locale (Persian) setup; per-tenant locales can be added in Phase 8.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// The browser never calls the backend directly; it calls this app's own origin and
// Next proxies to the backend server-side (see `rewrites` below). The backend URL is
// therefore only needed here. Default to the local dev backend.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Allow the dev server to serve assets when the site is opened on either host.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
  // Keep the trailing slash on proxied API paths. The DRF backend serves its routes
  // with a trailing slash and, with APPEND_SLASH on, raises a 500 if a POST arrives
  // without one. Two separate steps strip it, so both are handled below:
  //  1) By default Next 308-redirects `/api/v1/auth/login/` to the slashless form
  //     *before* the rewrite -- `skipTrailingSlashRedirect` disables that.
  //  2) A `:path*` rewrite param splits on `/` and drops the trailing slash when it
  //     rebuilds the destination -- a `:path(.*)` catch-all forwards the path verbatim
  //     (trailing slash included) instead.
  skipTrailingSlashRedirect: true,
  // Same-origin API proxy. Because the browser talks to the frontend origin (not the
  // backend directly), the JWT auth cookie is always first-party -- so the session
  // survives a refresh no matter whether the site is opened on `localhost` or
  // `127.0.0.1`. Calling the backend cross-origin (e.g. a `127.0.0.1` page hitting a
  // `localhost` API) makes the browser treat it as a different site and drop the
  // SameSite=Lax cookie on the `/auth/me` probe, which logged the user out on reload.
  async rewrites() {
    return [
      {
        source: "/api/:path(.*)",
        destination: `${BACKEND_ORIGIN}/api/:path`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
