import Link from "next/link";
import { WavesIcon } from "@phosphor-icons/react/dist/ssr";
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="蝦況 TIDE 首頁">
      <WavesIcon size={29} weight="bold" />
      <span>
        TIDE<span className="brand-chinese">蝦況</span>
      </span>
      {!compact && <span className="brand-caption">AQUATIC INTELLIGENCE</span>}
    </Link>
  );
}
