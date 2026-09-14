"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/features", label: "Features" },
  { href: "/screens", label: "Screens" },
  { href: "/compare", label: "Compare" },
  { href: "/gaps", label: "Gaps" },
  { href: "/search", label: "Search" },
  { href: "/pdp", label: "PDP Lab" },
  { href: "/capture", label: "+ Capture" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="nav">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          data-active={l.href === "/" ? path === "/" : path.startsWith(l.href)}
        >
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
