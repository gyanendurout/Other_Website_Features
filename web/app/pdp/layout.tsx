import "./pdp.css";

/**
 * PDP Lab section layout. Its only job is to scope `pdp.css` to /pdp/** so the
 * pickleball catalog's pages never load or are affected by it.
 */
export default function PdpLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
