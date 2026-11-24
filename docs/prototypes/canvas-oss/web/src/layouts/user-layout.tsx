import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { AgentPanel } from "@/components/agent/agent-panel";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppTopNav } from "@/components/layout/app-top-nav";

export default function UserLayout({ children }: { children: ReactNode }) {
    const { t } = useTranslation();
    const { pathname } = useLocation();
    const [navOpen, setNavOpen] = useState(false);
    /** 具体画布是沉浸工具态：产品侧栏不占位（左下角按钮唤出浮层），
     *  顶栏也由 AppTopNav 自己让位。 */
    const immersive = /^\/canvas\/[^/]+/.test(pathname);

    return (
        <div className="flex h-dvh overflow-hidden bg-background text-foreground">
            <AppSidebar open={navOpen} onClose={() => setNavOpen(false)} immersive={immersive} />
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                <AppTopNav onOpenNav={() => setNavOpen(true)} />
                <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
            </div>
            <AgentPanel />

            {immersive && !navOpen ? (
                <button
                    type="button"
                    onClick={() => setNavOpen(true)}
                    className="fixed left-0 top-1/2 z-30 grid h-11 w-3.5 -translate-y-1/2 place-items-center rounded-r-md border border-l-0 border-border bg-background/80 text-muted-foreground opacity-60 backdrop-blur transition hover:w-4 hover:opacity-100"
                    aria-label={t("topNav.openMenu")}
                    title={t("topNav.menu")}
                >
                    <ChevronRight className="size-3" />
                </button>
            ) : null}
        </div>
    );
}
