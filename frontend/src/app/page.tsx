import { fetchHealth } from "@/lib/api/health";

export default async function HomePage() {
  let backendState = "unknown";
  try {
    const report = await fetchHealth();
    backendState = report.state;
  } catch {
    backendState = "unreachable";
  }

  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem" }}>
      <h1>Polymart</h1>
      <p>White-label, multi-niche e-commerce platform.</p>
      <p data-testid="backend-state">Backend status: {backendState}</p>
    </main>
  );
}
