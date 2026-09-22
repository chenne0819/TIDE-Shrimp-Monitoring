import { Dashboard } from "@/components/dashboard";
export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ demo?: string }>;
}) {
  const params = await searchParams;
  return <Dashboard key={params.demo || "real"} demo={params.demo === "1"} />;
}
