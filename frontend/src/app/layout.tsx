import type { Metadata } from "next";
import { Instrument_Serif, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { NotificationsProvider } from "@/contexts/NotificationsContext";
import Nav from "@/components/Nav";

const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-jakarta" });
const serif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
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
    <html lang="en" className="dark">
      <body
        className={`${jakarta.variable} ${serif.variable} ${mono.variable} bg-ink font-sans text-white antialiased`}
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
