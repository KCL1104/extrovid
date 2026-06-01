import type { Metadata } from "next";
import { Instrument_Serif, Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import AuthGate from "@/components/AuthGate";

const display = Instrument_Serif({
  weight: ["400"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-display",
});

const sans = Hanken_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "extrovid — AI-native director",
  description: "Brief to rough cut. Plan, previsualize, generate, and assemble with AI.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable} h-full`}
    >
      <body className="atmosphere min-h-full">
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
