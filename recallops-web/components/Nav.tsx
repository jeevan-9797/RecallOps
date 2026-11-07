"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { isMock } from "@/lib/api";

const links = [
  { href: "/incidents", label: "Incidents" },
  { href: "/patterns", label: "Learned patterns" },
  { href: "/learning-curve", label: "Learning curve" },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-line bg-panel">
      <div className="mx-auto flex h-12 max-w-page items-center justify-between gap-4 px-4 sm:px-8">
        <div className="flex h-full min-w-0 items-center gap-4 sm:gap-8">
          <Link href="/incidents" className="text-base font-semibold text-ink">RecallOps</Link>
          <nav className="flex h-full min-w-0 items-center gap-3 overflow-x-auto sm:gap-6 [scrollbar-width:none]">
            {links.map((l) => {
              const on = path.startsWith(l.href);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={on ? "page" : undefined}
                  className={`inline-flex h-full items-center whitespace-nowrap border-b-2 px-1 text-sm transition-colors ${
                    on ? "border-accent font-medium text-accent" : "border-transparent text-ink-2 hover:text-ink"
                  }`}
                >
                  {l.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="hidden items-center gap-4 text-sm text-muted md:flex">
          {isMock && <span title="No NEXT_PUBLIC_API_BASE set. Showing built-in data.">Mock data</span>}
          <span>Kartly SRE</span>
        </div>
      </div>
    </header>
  );
}
