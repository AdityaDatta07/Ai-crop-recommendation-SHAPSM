import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from './providers';
import { AppShell } from '@/components/app-shell';
import { ServiceWorkerRegistration } from '@/components/service-worker';

export const metadata: Metadata = {
  title: 'Beej Nirnay',
  description:
    'Ranked crop recommendations for your field, with the reasoning and the economics behind each one.',
  // Installable to a home screen: no app store, any phone with a browser.
  manifest: '/manifest.webmanifest',
  appleWebApp: { capable: true, title: 'Beej Nirnay', statusBarStyle: 'default' },
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: '/icons/apple-touch-icon.png',
  },
};

export const viewport: Viewport = {
  // Matches the canvas, so the phone's status bar blends into the page
  // instead of drawing a lighter green stripe above a dark one.
  themeColor: '#0f2a1e',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // lang is corrected on the client once the stored locale is known.
    <html lang="en">
      <body>
        <Providers>
          <ServiceWorkerRegistration />
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
