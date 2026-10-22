// Public GitHub Pages website uses this value to contact the owner PC over HTTPS.
// Once the PC owner has a stable Tailscale Funnel host, write its exact HTTPS
// origin here ONCE (example only: https://your-node.your-tailnet.ts.net).
// Until then the original URL continues to show the safe demo. No secrets here.
window.PERMIT_API_BASE = "";

// Initial end-to-end testing can use a single shareable link:
// https://minjeong731.github.io/external-relations-team/?server=https%3A%2F%2FNODE.TAILNET.ts.net
// After the owner confirms the stable HTTPS hostname, set PERMIT_API_BASE
// above so the ordinary, unchanged GitHub Pages URL works on every employee PC.
try {
  const candidate = new URLSearchParams(window.location.search).get("server");
  if (candidate && !window.PERMIT_API_BASE) {
    const parsed = new URL(candidate);
    const allowed = parsed.protocol === "https:" &&
      /^[a-z0-9-]+(\.[a-z0-9-]+)+\.ts\.net$/i.test(parsed.hostname) &&
      !parsed.port && !parsed.username && !parsed.password &&
      (parsed.pathname === "/" || parsed.pathname === "") &&
      !parsed.search && !parsed.hash;
    if (allowed) window.PERMIT_API_BASE = parsed.origin;
  }
} catch (_) {
  // Invalid testing endpoint means keep the ordinary demo mode.
}
