'use client'

import { Toaster } from '@/components/ui/sonner'
import { DocumentsView } from '@/components/documents/DocumentsView'

export default function DocumentsPage() {
  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-10">
        <h1 className="text-sm font-semibold">Documents</h1>
      </header>
      <DocumentsView />
    </>
  )
}
