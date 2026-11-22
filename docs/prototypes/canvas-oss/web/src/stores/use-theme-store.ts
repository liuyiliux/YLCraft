import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * YLCraft 三主题（2026-11-22）：对齐 docs/prototypes/features/theme-switch.js
 * 的 deep 深海 / moonlight 月光 / dawn 晨曦。
 * 上游原本只有 light | dark；这里扩成三套，canvas-theme.ts 同步扩。
 * 旧存档里的 "dark" / "light" 在 persist 的 migrate 里映射到 deep / dawn。
 */
export type ThemeName = "deep" | "moonlight" | "dawn" | "light" | "dark";

type ThemeStore = {
    theme: ThemeName;
    setTheme: (theme: ThemeName) => void;
};

export const useThemeStore = create<ThemeStore>()(
    persist(
        (set) => ({
            theme: "deep",
            setTheme: (theme) => set({ theme }),
        }),
        {
            name: "infinite-canvas:theme_store",
            version: 2,
            migrate: (persisted) => {
                const old = (persisted as { theme?: string } | undefined)?.theme;
                if (old === "dark") return { theme: "deep" } as ThemeStore;
                if (old === "light") return { theme: "dawn" } as ThemeStore;
                if (old === "deep" || old === "moonlight" || old === "dawn") {
                    return { theme: old } as ThemeStore;
                }
                return { theme: "deep" } as ThemeStore;
            },
        },
    ),
);
