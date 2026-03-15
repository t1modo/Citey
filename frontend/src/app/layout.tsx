import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Syne } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { NotificationsProvider } from "@/contexts/NotificationsContext";
import Nav from "@/components/Nav";

const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-jakarta" });
const syne = Syne({ subsets: ["latin"], variable: "--font-syne" });

export const metadata: Metadata = {
  title: "Citey",
  description:
    "Citey monitors citations to your published works and sends you instant email alerts when a new paper cites your research. Track any DOI, powered by OpenAlex and Crossref.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${jakarta.variable} ${syne.variable} font-sans bg-gray-950 text-white antialiased`}>
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
