"use client";

import { MessageSquare, X } from "lucide-react";
import { useState } from "react";
import { Thread } from "@/components/thread";

export function AssistantModal() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        className="fixed bottom-5 right-5 z-30 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg"
        onClick={() => setOpen(true)}
        type="button"
        title="Open assistant"
      >
        <MessageSquare className="h-5 w-5" />
      </button>

      {open ? (
        <div className="fixed inset-0 z-40 bg-black/35">
          <section className="absolute bottom-5 right-5 flex h-[680px] max-h-[calc(100vh-40px)] w-[440px] max-w-[calc(100vw-40px)] flex-col overflow-hidden rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="text-sm font-semibold">Assistant</div>
              <button
                className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border"
                onClick={() => setOpen(false)}
                type="button"
                title="Close assistant"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <Thread />
          </section>
        </div>
      ) : null}
    </>
  );
}
