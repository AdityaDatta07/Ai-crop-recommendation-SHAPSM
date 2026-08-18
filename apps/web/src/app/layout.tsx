import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from './providers';
import { AppShell } from '@/components/app-shell';

export const metadata: Metadata = {
  title: 'Crop Advisor',
  description:
    'Ranked crop recommendations for your field, with the reasoning and the economics behind each one.',
};

export const viewport: Viewport = {
  themeColor: '#1f6b3b',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // lang is corrected on the client once the stored locale is known.
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
