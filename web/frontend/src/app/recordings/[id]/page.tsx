import { RecordingDetail } from "@/components/recording-detail";
export default async function RecordingPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ demo?: string }>;
}) {
  const [route, search] = await Promise.all([params, searchParams]);
  return (
    <RecordingDetail
      key={`${route.id}-${search.demo || "real"}`}
      id={route.id}
      demo={search.demo === "1"}
    />
  );
}
