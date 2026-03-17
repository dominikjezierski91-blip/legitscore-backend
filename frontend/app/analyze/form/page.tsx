import { AnalyzeForm } from "@/components/analyze/analyze-form";
import { BackButton } from "@/components/ui/back-button";

export default function AnalyzeFormPage() {
  return (
    <div className="flex flex-1 flex-col py-4 gap-3">
      <BackButton label="Analiza" />
      <AnalyzeForm />
    </div>
  );
}

