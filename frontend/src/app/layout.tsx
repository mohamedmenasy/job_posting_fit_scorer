import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { AppShell } from "@/components/app-shell";

import { Providers } from "./providers";
import "./globals.css";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "JobFit AI",
  description: "Explainable job-posting fit scores from typed semantic signals",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="min-h-full text-sm">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
