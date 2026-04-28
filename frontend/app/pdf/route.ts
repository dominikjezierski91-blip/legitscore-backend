import { NextResponse } from "next/server";

export async function GET() {
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
  return NextResponse.redirect(`${apiBase}/static/sample/report_example.pdf`);
}
