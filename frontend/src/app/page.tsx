import { APP_NAME, APP_TAGLINE } from "@/lib/site";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">{APP_NAME}</h1>
      <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">{APP_TAGLINE}</p>
      <p className="text-sm text-zinc-400 dark:text-zinc-600">M0 scaffold — game coming soon.</p>
    </main>
  );
}
