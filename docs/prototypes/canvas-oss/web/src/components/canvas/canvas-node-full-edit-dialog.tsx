/**
 * 完整图片编辑面板 —— 把 YLCraft 原型 06-imageops.js 的 33 项能力集中到一个入口。
 *
 * 为什么要这个：原型的编辑能力散在三个入口（镜头墙浮条 8 项 / 双击大图 33 项 /
 * 画布节点 6 项），画布节点上偏偏没有那套完整清单。参考项目的图片浮条入口统一，
 * 但只有 11 项。这里把 33 项挂到图片节点的「完整编辑」按钮上，入口就统一了。
 *
 * 原型阶段不真调模型：标价 ⚡ 的项点击给出 toast，免费本地项也是占位说明。
 * 真实现留在从实际项目迁移那一步。
 */
import { useMemo, useState } from "react";
import { App, Modal, Tag } from "antd";
import { useTranslation } from "react-i18next";
import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";

type Op = { k: string; d: string; c: string; local?: boolean };
type Group = { g: string; items: Op[] };

/* 与 docs/prototypes/canvas/js/06-imageops.js 的 IMG_OPS 一一对应 */
const GROUPS: Group[] = [
    {
        g: "本地处理 · 免费即时（不用调模型）",
        items: [
            { k: "裁剪", d: "改构图", c: "免费", local: true },
            { k: "旋转与翻转", d: "水平/垂直/任意角度", c: "免费", local: true },
            { k: "滤镜", d: "亮度 / 对比 / 饱和 / 色相", c: "免费", local: true },
            { k: "压缩 / 改尺寸", d: "改变像素尺寸与体积", c: "免费", local: true },
            { k: "加文字", d: "图上写字", c: "免费", local: true },
            { k: "水印", d: "加文字水印（居中/右下/平铺）", c: "免费", local: true },
            { k: "画图 / 涂鸦", d: "手绘几笔", c: "免费", local: true },
            { k: "字符画", d: "转成字符拼成的图", c: "免费", local: true },
            { k: "Base64", d: "导出编码，给开发用", c: "免费", local: true },
        ],
    },
    {
        g: "AI 修改 · 在这张图上改",
        items: [
            { k: "画面批注改图", d: "圈一块 + 写意见，直接重画", c: "⚡3" },
            { k: "局部重绘", d: "框选一块，描述要变成什么", c: "⚡3" },
            { k: "重新打光", d: "光位跟着原图走", c: "⚡3" },
            { k: "AI 调色", d: "说「冷一点/暖一点」", c: "⚡2" },
        ],
    },
    {
        g: "派生 · 生成新图",
        items: [
            { k: "扩展画布", d: "向外扩，补背景（outpaint）", c: "⚡4" },
            { k: "去背景 / 抠主体", d: "输出透明底 PNG", c: "⚡2" },
            { k: "换背景", d: "描述新背景", c: "⚡4" },
            { k: "画同款", d: "照这张的风格再出一张", c: "⚡14" },
            { k: "变体 ×4", d: "同提示词出 4 张备选", c: "⚡28" },
            { k: "生成多角度", d: "换机位看同一主体", c: "⚡14" },
            { k: "图层拆分", d: "拆成 人物 / 背景 / 文字 层", c: "⚡6" },
            { k: "编辑文字", d: "OCR 抽字重绘（会丢原字体效果）", c: "⚡14" },
            { k: "图生 3D", d: "TripoSR 出 glb，可进 3D 导演台", c: "⚡8" },
        ],
    },
    {
        g: "动图 · 多格图切帧",
        items: [
            { k: "生成动图", d: "一次画多格画面（不是视频）", c: "⚡14" },
            { k: "切帧合成 GIF", d: "选格数 → GIF / WebP / MP4", c: "免费", local: true },
            { k: "帧级滤镜", d: "亮度/对比/饱和/色相/旋转", c: "免费", local: true },
            { k: "自定义切分网格", d: "格子分割线可以手拖", c: "免费", local: true },
        ],
    },
    {
        g: "批量 · 一次出多张",
        items: [
            { k: "多机位九宫格", d: "一张 → 9 个机位", c: "⚡126" },
            { k: "角色三视图", d: "正面 / 侧面 / 背面", c: "⚡42" },
            { k: "剧情推演四宫格", d: "情节往下推 4 格", c: "⚡56" },
            { k: "25 宫格连贯分镜", d: "一次出 25 格", c: "⚡350" },
        ],
    },
    {
        g: "输出",
        items: [
            { k: "存到素材库", d: "合成图 + 分层结构两份", c: "免费", local: true },
            { k: "下载原图", d: "", c: "免费", local: true },
            { k: "复制一张", d: "", c: "免费", local: true },
        ],
    },
];

type Props = {
    open: boolean;
    onClose: () => void;
    imageTitle?: string;
};

export function CanvasNodeFullEditDialog({ open, onClose, imageTitle }: Props) {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const themeName = useThemeStore((state) => state.theme);
    const t3 = canvasThemes[themeName] || canvasThemes.dark;
    /* 上游主题是嵌套结构（node / toolbar / canvas），摊平成面板用的语义名 */
    const theme = {
        text: t3.node.text,
        textMuted: t3.node.muted,
        border: t3.node.stroke,
        panel: t3.node.panel,
        toolbarBg: t3.toolbar.itemHover,
        canvasBg: t3.canvas.background,
        accent: themeName === "dawn" || themeName === "light" ? "#0d9488" : themeName === "moonlight" ? "#a78bfa" : "#22d3ee",
        accentSoft: themeName === "dawn" || themeName === "light" ? "rgba(13,148,136,.16)" : themeName === "moonlight" ? "rgba(167,139,250,.16)" : "rgba(34,211,238,.16)",
    };
    const [filter, setFilter] = useState<"all" | "local" | "ai">("all");
    const [keyword, setKeyword] = useState("");

    const total = useMemo(() => GROUPS.reduce((n, g) => n + g.items.length, 0), []);
    const groups = useMemo(() => {
        const kw = keyword.trim().toLowerCase();
        return GROUPS.map((g) => ({
            ...g,
            items: g.items.filter((op) => {
                if (filter === "local" && !op.local) return false;
                if (filter === "ai" && op.local) return false;
                if (!kw) return true;
                return (op.k + " " + op.d).toLowerCase().includes(kw);
            }),
        })).filter((g) => g.items.length > 0);
    }, [filter, keyword]);

    const run = (op: Op) => {
        message.info(
            op.local
                ? `${op.k} · 原型本地像素编辑，迁移到实际项目时接真实现`
                : `${op.k} · 原型不真调模型（${op.c}），迁移后接我们的 AI 网关`,
            3,
        );
    };

    const chip = (active: boolean) => ({
        border: `1px solid ${active ? theme.accent : theme.border}`,
        background: active ? theme.accent : "transparent",
        color: active ? theme.canvasBg : theme.text,
    });

    return (
        <Modal
            open={open}
            onCancel={onClose}
            footer={null}
            width={900}
            destroyOnHidden
            title={
                <span style={{ color: theme.text }}>
                    完整图片编辑 <span style={{ color: theme.textMuted, fontWeight: 400 }}>· {imageTitle || "图片节点"} · {total} 项能力</span>
                </span>
            }
            styles={{ body: { background: theme.panel, padding: "12px 18px 18px", maxHeight: "70vh", overflow: "auto" } }}
        >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                {(["all", "local", "ai"] as const).map((f) => (
                    <button
                        key={f}
                        type="button"
                        onClick={() => setFilter(f)}
                        style={{
                            ...chip(filter === f),
                            borderRadius: 999,
                            padding: "4px 12px",
                            fontSize: 13,
                            cursor: "pointer",
                            lineHeight: 1.4,
                        }}
                    >
                        {f === "all" ? `全部 ${total}` : f === "local" ? "本地免费" : "AI 生成"}
                    </button>
                ))}
                <input
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    placeholder={t("canvas.imageTools.fullEditSearch")}
                    style={{
                        marginLeft: "auto",
                        width: 200,
                        height: 30,
                        padding: "0 10px",
                        borderRadius: 6,
                        border: `1px solid ${theme.border}`,
                        background: theme.toolbarBg,
                        color: theme.text,
                        fontSize: 13,
                    }}
                />
            </div>

            {groups.length === 0 ? (
                <div style={{ color: theme.textMuted, padding: "28px 0", textAlign: "center", fontSize: 13 }}>没有匹配的编辑能力</div>
            ) : (
                groups.map((g) => (
                    <section key={g.g} style={{ marginBottom: 16 }}>
                        <div style={{ color: theme.textMuted, fontSize: 13, fontWeight: 600, padding: "4px 0 8px", borderBottom: `1px solid ${theme.border}` }}>
                            {g.g} <span style={{ fontWeight: 400 }}>({g.items.length})</span>
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8, paddingTop: 8 }}>
                            {g.items.map((op) => (
                                <button
                                    key={op.k}
                                    type="button"
                                    onClick={() => run(op)}
                                    style={{
                                        textAlign: "left",
                                        border: `1px solid ${theme.border}`,
                                        borderRadius: 8,
                                        background: theme.toolbarBg,
                                        color: theme.text,
                                        padding: "9px 10px",
                                        cursor: "pointer",
                                        minWidth: 0,
                                    }}
                                    title={op.d || op.k}
                                >
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                                        <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{op.k}</span>
                                        <Tag
                                            style={{
                                                margin: 0,
                                                fontSize: 12,
                                                lineHeight: "16px",
                                                padding: "0 5px",
                                                border: 0,
                                                background: op.local ? theme.accentSoft : theme.panel,
                                                color: op.local ? theme.accent : theme.textMuted,
                                                flex: "0 0 auto",
                                            }}
                                        >
                                            {op.c}
                                        </Tag>
                                    </div>
                                    <div style={{ color: theme.textMuted, fontSize: 13, marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {op.d || "—"}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </section>
                ))
            )}

            <div style={{ color: theme.textMuted, fontSize: 13, borderTop: `1px solid ${theme.border}`, paddingTop: 8 }}>
                来源：原型 <code style={{ color: theme.text }}>06-imageops.js</code> 的 33 项清单 · 原型阶段只演示入口，不真调模型
            </div>
        </Modal>
    );
}
