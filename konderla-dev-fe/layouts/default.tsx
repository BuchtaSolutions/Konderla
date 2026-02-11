import { Head } from "./head";
import { Link } from "@heroui/link";
import { Logo } from "@/components/icons";
import { ThemeSwitch } from "@/components/theme-switch";

export default function DefaultLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen w-full bg-default-50 flex flex-col">
      <Head />
      
      {/* Top Standard Navbar */}
      <header className="h-16 bg-background border-b border-divider flex items-center justify-between px-6 sticky top-0 z-50">
        <div className="flex items-center gap-4">
          <Link href="/" color="foreground" className="flex items-center gap-2">
            <span className="font-bold text-lg tracking-tight">Srovnávač rozpočtů</span>
          </Link>
        </div>
        <div className="flex items-center gap-4">
          <ThemeSwitch />
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full px-6 py-6">
        <div className="mx-auto w-full max-w-full">
          {children}
        </div>
      </main>
    </div>
  );
}
