import { AssistantRoot } from "@/components/assistant-root";
import { AssistantDrawer } from "@/components/assistant-drawer";
import {
  AUTH0_SESSION_COOKIE,
  readAuth0SessionCookieValue
} from "@/lib/server/auth0-session";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

type HomeProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Home({ searchParams }: HomeProps) {
  const auth0Error = firstParam((await searchParams)?.auth0_error);
  if (!(await hasAuth0Session())) {
    if (auth0Error) return <Auth0ErrorScreen message={auth0Error} />;
    redirect("/api/auth/login?returnTo=/");
  }

  return (
    <main className="min-h-screen bg-background">
      <AssistantRoot>
        <AssistantDrawer />
      </AssistantRoot>
    </main>
  );
}

async function hasAuth0Session(): Promise<boolean> {
  const cookieStore = await cookies();
  const cookieValue = cookieStore.get(AUTH0_SESSION_COOKIE)?.value ?? null;
  if (!cookieValue) return false;

  try {
    return Boolean(readAuth0SessionCookieValue(cookieValue));
  } catch {
    return false;
  }
}

function Auth0ErrorScreen({ message }: { message: string }) {
  return (
    <main className="grid min-h-screen place-items-center bg-background px-6">
      <section className="w-full max-w-md rounded-md border border-border bg-white p-5 shadow-sm">
        <h1 className="text-base font-semibold text-foreground">SSO sign-in failed</h1>
        <p className="mt-2 break-words text-sm text-muted-foreground">{message}</p>
        <a
          className="mt-4 inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground"
          href="/api/auth/login"
        >
          Retry SSO
        </a>
      </section>
    </main>
  );
}

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}
