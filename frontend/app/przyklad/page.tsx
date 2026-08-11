import { Metadata } from "next";
import { CaseReportView } from "@/components/case/case-report-view";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Przykładowy raport — LegitScore",
  description:
    "Zobacz przykładowy raport ryzyka autentyczności LegitScore na prawdziwej analizie koszulki.",
};

// Realny, zdecydowany case z produkcji (FC Bayern München, Lewandowski, oryginalna sklepowa, 90%).
// Zmieniając ten ID podmieniamy przykładowy raport bez dotykania Lovable / linku na landing page.
const EXAMPLE_CASE_ID = "1f0bdd80-a8be-4642-8f05-47a31a90e51a";

export default async function PrzykladPage() {
  return <CaseReportView caseId={EXAMPLE_CASE_ID} isExample />;
}
