import { NextResponse } from 'next/server';

// NEXT_PUBLIC_API_BASE_URL jest dostępny server-side w route handlerach.
// Idealnie powinien to być API_BASE_URL (bez NEXT_PUBLIC_), ale zostawiamy
// kompatybilny fallback, żeby nie wymagać zmiany .env.local.
const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/instagram/random-fake-case`, {
      cache: 'no-store',
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: 'Backend error' }));
      return NextResponse.json(body, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: 'Backend not reachable' }, { status: 500 });
  }
}
