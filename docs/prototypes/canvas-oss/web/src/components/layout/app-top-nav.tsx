import { Bot, Menu } from "lucide-react";
import { Button, Tooltip } from "antd";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AppConfigModal } from "@/components/layout/app-config-modal";
import { UserStatusActions } from "@/components/layout/user-status-actions";
import { findActiveNav } from "@/constant/navigation-groups";
import { useEffect, useRef } from "react";
import { useAgentStore } from "@/stores/use-agent-store";

type AppTopNavProps = {
    /** 窄屏时点 ≡ 打开左侧栏抽屉 */
    onOpenNav: () => void;
};

/** 顶部 48px 面包屑条（导航全在左侧栏里，这里只留位置与操作）。 */
export function AppTopNav({ onOpenNav }: AppTopNavProps) {
    const { t } = useTranslation();
    const { pathname } = useLocation();
    const autoConnectRef = useRef(false);
    const agentToken = useAgentStore((state) => state.token);
    const agentEnabled = useAgentStore((state) => state.enabled);
    const agentConnected = useAgentStore((state) => state.connected);
    const connectAgent = useAgentStore((state) => state.connectAgent);
    const togglePanel = useAgentStore((state) => state.togglePanel);
    const panelOpen = useAgentStore((state) => state.panelOpen);
    /** 画布项目页是沉浸式整屏，顶栏让位（侧栏保留） */
    const hideHeader = /^\/canvas\/[^/]+/.test(pathname);
    const active = findActiveNav(pathname);

    useEffect(() => {
        if (autoConnectRef.current || agentEnabled || agentConnected || !agentToken.trim()) return;
        autoConnectRef.current = true;
        connectAgent({ silent: true });
    }, [agentConnected, agentEnabled, agentToken, connectAgent]);

    return (
        <>
            {!hideHeader ? (
                <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/90 px-4 backdrop-blur-xl">
                    <button
                        type="button"
                        className="grid size-7 shrink-0 place-items-center rounded-[7px] border border-border bg-muted text-muted-foreground transition hover:text-foreground lg:hidden"
                        onClick={onOpenNav}
                        aria-label={t("topNav.openMenu")}
                        title={t("topNav.menu")}
                    >
                        <Menu className="size-4" />
                    </button>

                    <div className="flex min-w-0 items-center gap-1.5 whitespace-nowrap">
                        {active ? (
                            <span className="shrink-0 text-[13px] font-normal text-muted-foreground">
                                {t(`navGroups.${active.group.key}`)}
                                <span className="mx-1.5 opacity-60">/</span>
                            </span>
                        ) : null}
                        <span className="truncate text-[13px] font-semibold">
                            {active
                                ? t(active.item.external ? `navExtra.${active.item.key}` : `navigation.${active.item.key}`)
                                : t("meta.title")}
                        </span>
                    </div>

                    <span className="hidden min-w-0 flex-1 truncate pl-4 text-right text-[11px] text-muted-foreground xl:block">
                        {t("navGroups.hint")}
                    </span>
                    <span className="flex-1 xl:hidden" />

                    <div className="flex h-9 shrink-0 items-center gap-2 whitespace-nowrap">
                        <Tooltip title={t(panelOpen ? "topNav.closeAgent" : "topNav.openAgent")}>
                            <Button
                                type="text"
                                shape="circle"
                                className="!h-8 !w-8 !min-w-8"
                                icon={<Bot className="size-4" />}
                                onClick={togglePanel}
                                aria-label={t(panelOpen ? "topNav.closeAgent" : "topNav.openAgent")}
                            />
                        </Tooltip>
                        <UserStatusActions />
                    </div>
                </header>
            ) : null}

            <AppConfigModal />
        </>
    );
}
