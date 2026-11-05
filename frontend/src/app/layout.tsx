import type { Metadata } from "next";
import { Atkinson_Hyperlegible, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { NotificationsProvider } from "@/contexts/NotificationsContext";
import Nav from "@/components/Nav";

// Atkinson Hyperlegible for interface text; Source Serif 4 (a reading serif
// with optical sizes) for headings and longer prose; mono only for DOIs.
const ui = Atkinson_Hyperlegible({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-ui" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-serif",
});
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: {
    default: "Citey — Citation alerts for researchers",
    template: "%s · Citey",
  },
  description:
    "Citey monitors citations to your published works and sends you instant email alerts when a new paper cites your research. Track any DOI, powered by OpenAlex, Crossref, and Semantic Scholar.",
  icons: {
    icon: "/logo.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${ui.variable} ${serif.variable} ${mono.variable} bg-paper font-sans text-ink antialiased`}
      >
        <AuthProvider>
          <NotificationsProvider>
            <Nav />
            <main className="min-h-screen">{children}</main>
          </NotificationsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
