const API_URL = process.env.PRICE_LENS_API_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "問題格式不正確。" }, { status: 400 });
  }

  try {
    const response = await fetch(`${API_URL}/api/v1/ask`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(12_000),
    });
    const payload = await response.text();
    return new Response(payload, {
      status: response.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json(
      { detail: "目前無法連線到價格問答服務，請稍後再試。" },
      { status: 503 },
    );
  }
}
