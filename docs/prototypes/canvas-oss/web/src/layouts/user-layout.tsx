import { useState, type ReactNode } from "react";

import { AgentPanel } from "@/components/agent/agent-panel";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppTopNav } from "@/components/layout/app-top-nav";

export default function UserLayout({ children }: { children: ReactNode }) {
    const [navOpen, setNavOpen] = useState(false);

    return (
        <div className="flex h-dvh overflow-hidden bg-background text-foreground">
            {/* 224px 固定左栏（窄屏收成抽屉），顶栏只剩面包屑 —— 对齐原型 shell.css */}
            <AppSidebar open={navOpen} onClose={() => setNavOpen(false)} />
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                <AppTopNav onOpenNav={() => setNavOpen(true)} />
                <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
            </div>
            <AgentPanel />
        </div>
    );
}
