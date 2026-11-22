/**
 * 三主题 + 两个旧别名：
 * deep/moonlight/dawn 是新三套；light/dark 保留为别名（light→dawn、dark→deep），
 * 让上游 AnimatedThemeToggler 等旧代码中的 "light"/"dark" 字面量继续编译。
 */
export type CanvasColorTheme = "deep" | "moonlight" | "dawn" | "light" | "dark";
export type CanvasBackgroundMode = "dots" | "lines" | "blank";

/**
 * 画布主题（2026-11-22 改造为三套）：
 * - deep      深海：沿用上游 dark 原值（暖灰 #181715），主色青 #22d3ee
 * - moonlight 月光：深紫底 #1d1a24，主色紫 #a78bfa
 * - dawn      晨曦：亮色白底 #ffffff，主色青绿 #0d9488
 *
 * 色值来源：
 * - 上游原值（dark / light）
 * - YLCraft docs/prototypes/features/theme-switch.js + shared/proto-nav.js
 * 配套：use-theme-store.ts 的 ThemeName 也是三套。
 */
export const canvasThemes = {
    deep: {
        canvas: {
            background: "#181715",
            dot: "rgba(245,245,244,.24)",
            line: "rgba(245,245,244,.10)",
            selectionStroke: "#fafaf9",
            selectionFill: "rgba(250,250,249,.10)",
        },
        node: {
            label: "#d6d3d1",
            fill: "#292524",
            panel: "#1f1d1a",
            stroke: "#44403c",
            activeStroke: "#fafaf9",
            placeholder: "#a8a29e",
            text: "#f5f5f4",
            muted: "#d6d3d1",
            faint: "#78716c",
        },
        toolbar: {
            panel: "rgba(31,29,26,.96)",
            border: "#44403c",
            item: "#d6d3d1",
            itemHover: "#292524",
            activeBg: "#3a3631",
            activeText: "#f5f5f4",
        },
    },
    moonlight: {
        canvas: {
            background: "#1d1a24",
            dot: "rgba(228,228,236,.24)",
            line: "rgba(228,228,236,.10)",
            selectionStroke: "#c4b5fd",
            selectionFill: "rgba(167,139,250,.14)",
        },
        node: {
            label: "#ded8ea",
            fill: "#262130",
            panel: "#1d1a24",
            stroke: "#4b4260",
            activeStroke: "#c4b5fd",
            placeholder: "#8884a4",
            text: "#e4e4ec",
            muted: "#ded8ea",
            faint: "#6f6a89",
        },
        toolbar: {
            panel: "rgba(29,26,36,.96)",
            border: "#4b4260",
            item: "#ded8ea",
            itemHover: "#262130",
            activeBg: "#3b3350",
            activeText: "#f3eefe",
        },
    },
    dawn: {
        canvas: {
            background: "#ffffff",
            dot: "rgba(68,64,60,.28)",
            line: "rgba(68,64,60,.12)",
            selectionStroke: "#1c1917",
            selectionFill: "rgba(28,25,23,.06)",
        },
        node: {
            label: "#57534e",
            fill: "#e7e5df",
            panel: "#fbfaf7",
            stroke: "#d6d3ca",
            activeStroke: "#1c1917",
            placeholder: "#8a8479",
            text: "#292524",
            muted: "#78716c",
            faint: "#a8a29e",
        },
        toolbar: {
            panel: "rgba(251,250,247,.96)",
            border: "#d6d3ca",
            item: "#57534e",
            itemHover: "#e7e5df",
            activeBg: "#e7e5df",
            activeText: "#292524",
        },
    },
    /* 旧别名：让上游代码里的 "dark" / "light" 字面量仍能用 */
    dark: {
        canvas: {
            background: "#181715",
            dot: "rgba(245,245,244,.24)",
            line: "rgba(245,245,244,.10)",
            selectionStroke: "#fafaf9",
            selectionFill: "rgba(250,250,249,.10)",
        },
        node: {
            label: "#d6d3d1", fill: "#292524", panel: "#1f1d1a", stroke: "#44403c",
            activeStroke: "#fafaf9", placeholder: "#a8a29e", text: "#f5f5f4",
            muted: "#d6d3d1", faint: "#78716c",
        },
        toolbar: {
            panel: "rgba(31,29,26,.96)", border: "#44403c", item: "#d6d3d1",
            itemHover: "#292524", activeBg: "#3a3631", activeText: "#f5f5f4",
        },
    },
    light: {
        canvas: {
            background: "#ffffff",
            dot: "rgba(68,64,60,.28)",
            line: "rgba(68,64,60,.12)",
            selectionStroke: "#1c1917",
            selectionFill: "rgba(28,25,23,.06)",
        },
        node: {
            label: "#57534e", fill: "#e7e5df", panel: "#fbfaf7", stroke: "#d6d3ca",
            activeStroke: "#1c1917", placeholder: "#8a8479", text: "#292524",
            muted: "#78716c", faint: "#a8a29e",
        },
        toolbar: {
            panel: "rgba(251,250,247,.96)", border: "#d6d3ca", item: "#57534e",
            itemHover: "#e7e5df", activeBg: "#e7e5df", activeText: "#292524",
        },
    },
} as const;

export type CanvasTheme = (typeof canvasThemes)[CanvasColorTheme];
