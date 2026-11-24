import { ExternalLink } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { findActiveNav, navigationGroups, PROTO_BASE } from "@/constant/navigation-groups";
import { cn } from "@/lib/utils";

type AppSidebarProps = {
    /** 窄屏抽屉是否展开（≥1024px 时忽略） */
    open: boolean;
    onClose: () => void;
    /** 沉浸页（具体画布）：不占位，按需以浮层形式唤出 */
    immersive?: boolean;
};

/** 224px 固定左栏（对齐 docs/prototypes/shared/shell.css 的视觉）：
 *  顶部 48px 品牌 · 中间分组导航（圆点 + 文字）· 底部预览地址。 */
export function AppSidebar({ open, onClose, immersive = false }: AppSidebarProps) {
    const { t } = useTranslation();
    const { pathname } = useLocation();
    const active = findActiveNav(pathname);

    return (
        <>
            {open ? (
                <div
                    className={cn("fixed inset-0 z-[999] bg-black/60", immersive ? "" : "lg:hidden")}
                    onClick={onClose}
                    aria-hidden
                />
            ) : null}

            <aside
                className={cn(
                    "flex w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground",
                    immersive
                        ? open
                            ? "fixed inset-y-0 left-0 z-[1000] shadow-2xl"
                            : "hidden"
                        : cn(
                              "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-[1000] max-lg:transition-transform max-lg:duration-200",
                              open ? "max-lg:translate-x-0" : "max-lg:-translate-x-full",
                          ),
                )}
                aria-label={t("navGroups.label")}
            >
                <div className="flex h-12 shrink-0 items-center gap-2 border-b border-sidebar-border px-3.5">
                    <span className="grid size-[22px] shrink-0 place-items-center rounded-md bg-primary text-[11px] font-extrabold text-primary-foreground">
                        Y
                    </span>
                    <span className="whitespace-nowrap text-[13px] font-bold tracking-tight">{t("navGroups.brand")}</span>
                    <span className="ml-auto rounded-full border border-sidebar-border px-1.5 py-px text-[11px] text-muted-foreground">
                        v0.9
                    </span>
                </div>

                <nav className="yl-nav min-h-0 flex-1 overflow-y-auto px-2 pb-3.5 pt-2 [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin]">
                    {navigationGroups.map((group) => (
                        <div key={group.key}>
                            <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-3 text-[12px] tracking-wide text-muted-foreground">
                                <span>{t(`navGroups.${group.key}`)}</span>
                                {group.note ? <span className="ml-auto text-[11px] opacity-70">{group.note}</span> : null}
                            </div>

                            {group.items.map((item) => {
                                const isActive = active?.item === item;
                                const label = t(item.external ? `navExtra.${item.key}` : `navigation.${item.key}`);
                                /** 结构放这里；颜色与状态色由 globals.css 的 .yl-nav a 接管
                                 *  （上游全局 a 重置会压掉 utilities 的 color/background）。*/
                                const inner = (
                                    <>
                                        <span className="dot" />
                                        <span className="lbl">{label}</span>
                                        {item.badge === "new" ? <span className="badge">{t("navGroups.new")}</span> : null}
                                        {item.external ? <ExternalLink className="ext" /> : null}
                                    </>
                                );

                                return item.external ? (
                                    <a
                                        key={item.key}
                                        href={item.path}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={onClose}
                                    >
                                        {inner}
                                    </a>
                                ) : (
                                    <Link
                                        key={item.key}
                                        to={item.path}
                                        aria-current={isActive ? "page" : undefined}
                                        onClick={onClose}
                                    >
                                        {inner}
                                    </Link>
                                );
                            })}
                        </div>
                    ))}
                </nav>

                <div className="shrink-0 border-t border-sidebar-border px-3.5 pb-3 pt-2.5 text-[12px] leading-relaxed text-muted-foreground">
                    {t("navGroups.footer")} <b className="font-medium text-foreground/80">127.0.0.1:3100</b>
                    <br />
                    {t("navGroups.footerProto")}{" "}
                    <span className="text-foreground/70">{PROTO_BASE.replace(/^https?:\/\//, "")}</span>
                </div>
            </aside>
        </>
    );
}
