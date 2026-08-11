import { CaseReportView } from "@/components/case/case-report-view";

export const dynamic = "force-dynamic";

type Props = {
  params: { case_id: string };
  searchParams: { mode?: string; add_to_collection?: string };
};

export default async function CasePage({ params, searchParams }: Props) {
  return (
    <CaseReportView
      caseId={params.case_id}
      mode={searchParams.mode}
      autoOpenCollection={searchParams.add_to_collection === "1"}
    />
  );
}
