import { AnalyzeSuccess } from "@/components/analyze/analyze-success";

type Props = {
  searchParams: {
    caseId?: string;
    mode?: string;
  };
};

export default function AnalyzeSuccessPage({ searchParams }: Props) {
  const caseId = searchParams.caseId ?? "";
  const mode = searchParams.mode ?? "";

  return (
    <div className="flex flex-1 items-center justify-center">
      <AnalyzeSuccess caseId={caseId} mode={mode} />
    </div>
  );
}

