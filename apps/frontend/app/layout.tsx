import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AssistantRoot } from "@/components/assistant-root";

export const metadata: Metadata = {
  title: "Magnum Opus Auth0 Workflow Sample",
  description: "assistant-ui sample for Auth0 Client Credentials workflows"
};

export default function RootLayout({
  children
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AssistantRoot>{children}</AssistantRoot>
      </body>
    </html>
  );
}
