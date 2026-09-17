"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHealth } from "@/lib/api/hooks";
import { cnJoin } from "@/lib/format";

const NAV = [
  { href: "/", label: "Jobs" },
  { href: "/jobs/new", label: "New job" },
  { href: "/profile", label: "Profile" },
  { href: "/settings", label: "Scoring" },
];

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const health = useHealth();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (event.key === "/") {
        const search = document.getElementById("job-search");
        if (search) {
          event.preventDefault();
          search.focus();
        }
      } else if (event.key === "n") {
        event.preventDefault();
        router.push("/jobs/new");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const h = health.data;

  return (
    <div className="flex min-h-full flex-col">
      <header className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur">
        <div className="mx-auto flex h-12 max-w-[1440px] items-center gap-6 px-4">
          <Link href="/" className="font-semibold tracking-tight">
            JobFit<span className="text-brand"> AI</span>
          </Link>
          <nav className="flex items-center gap-1" aria-label="Main">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active(item.href) ? "page" : undefined}
                className={cnJoin(
                  "rounded px-2 py-1 transition-colors duration-150",
                  active(item.href) ? "bg-brand-soft text-brand font-medium" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground inline-flex items-center gap-2 text-xs">
                  <span
                    className={cnJoin(
                      "size-2 rounded-full",
                      health.isError ? "bg-status-blocked" : h ? "bg-status-strong" : "bg-status-low",
                    )}
                    aria-hidden
                  />
                  {health.isError ? "Backend offline" : h ? (h.evaluator === "fake" ? "Fake evaluator" : h.model) : "Connecting"}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {health.isError
                  ? "Start the backend with make dev"
                  : h
                    ? `Evaluator ${h.evaluator}, model ${h.model}, ${h.queue_depth} queued${h.evaluator === "typesafe" && !h.api_key_configured ? ", API key missing" : ""}`
                    : "Checking backend"}
              </TooltipContent>
            </Tooltip>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Toggle color theme"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            >
              <Sun className="size-4 dark:hidden" />
              <Moon className="hidden size-4 dark:block" />
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
