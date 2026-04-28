import { redirect } from "next/navigation";

export async function GET() {
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
  redirect(`${apiBase}/static/sample/report_example.pdf`);
}
