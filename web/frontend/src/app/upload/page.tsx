import { Upload } from "@/components/upload";
export default async function UploadPage({
  searchParams,
}: {
  searchParams: Promise<{ demo?: string }>;
}) {
  const params = await searchParams;
  return <Upload key={params.demo || "real"} demo={params.demo === "1"} />;
}
