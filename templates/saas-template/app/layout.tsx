import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "{{PRODUCT_NAME}}",
  description: "{{PRODUCT_TAGLINE}}",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
