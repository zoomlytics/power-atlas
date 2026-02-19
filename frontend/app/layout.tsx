import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Power Atlas',
  description: 'Graph database exploration tool with Apache AGE',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
