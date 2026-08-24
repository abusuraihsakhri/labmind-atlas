import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LabMind Intelligence Dashboard",
  description: "Agentic monitoring & safety layer for Laboratory Information Systems",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
