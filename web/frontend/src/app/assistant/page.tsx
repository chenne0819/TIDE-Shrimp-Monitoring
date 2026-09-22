import type { Metadata } from "next";
import { AssistantWorkspace } from "@/components/assistant-workspace";
import "../assistant.css";

export const metadata: Metadata = { title: "AI 分析" };
export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<{ demo?: string }>;
}) {
  const params = await searchParams;
  return (
    <AssistantWorkspace
      key={params.demo || "real"}
      demo={params.demo === "1"}
    />
  );
}
