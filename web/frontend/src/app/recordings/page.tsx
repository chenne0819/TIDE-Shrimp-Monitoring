import { Recordings } from "@/components/recordings";
export default async function RecordingsPage({
  searchParams,
}: {
  searchParams: Promise<{ demo?: string }>;
}) {
  const params = await searchParams;
  return <Recordings key={params.demo || "real"} demo={params.demo === "1"} />;
}
