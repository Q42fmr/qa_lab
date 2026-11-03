import type { Metadata } from "next";
import { Libre_Franklin, Lora } from "next/font/google";
import "./globals.css";

import { site } from "@/content/site";
import { SITE_URL } from "@/lib/seo";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { CookieBanner } from "@/components/layout/CookieBanner";
import { JsonLd } from "@/components/seo/JsonLd";
import { organizationSchema, websiteSchema } from "@/components/seo/schema";

const libreFranklin = Libre_Franklin({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-sans",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin"],
  weight: ["600", "700"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${site.brandName} – ${site.tagline}`,
    template: `%s – ${site.brandName}`,
  },
  description: site.description,
  applicationName: site.brandName,
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: site.brandName,
    title: `${site.brandName} – ${site.tagline}`,
    description: site.description,
    url: SITE_URL,
    locale: "de_CH",
  },
  twitter: {
    card: "summary_large_image",
    title: `${site.brandName} – ${site.tagline}`,
    description: site.description,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="de-CH" className={`${libreFranklin.variable} ${lora.variable}`}>
      <body className="flex min-h-screen flex-col bg-background text-foreground antialiased">
        <JsonLd data={organizationSchema(site)} />
        <JsonLd data={websiteSchema(site)} />
        <Header site={site} />
        <main className="flex-1">{children}</main>
        <Footer site={site} />
        <CookieBanner />
      </body>
    </html>
  );
}
