import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "BMP Mode — Textile Design Rasterization",
  description: "Convert images to production-ready BMP with weaving grid optimization",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body>{children}</body>
    </html>
  );
}
