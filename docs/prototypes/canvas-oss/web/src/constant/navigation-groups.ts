import { Maximize2, ImagePlus, Video, FileText, Images, Settings2 } from "lucide-react";

/** 侧栏导航（2026-11-24 收编：外壳换成原型那套 224px 左侧栏）。
 *
 *  分组口径沿用 docs/prototypes/shared/shell.js：
 *    · 工作台 / 素材与提示词  走本应用路由
 *    · 原型其他页            还留在 8901 那套原生 JS 原型里，先外链过去占位，
 *                            迁完一页就删一条（不要在这里假装已经迁完）
 *    · 系统                  配置
 *
 *  改导航只改这个文件。 */
export type NavItem = {
    /** i18n key：navigation.<key>（本应用路由）或 navExtra.<key>（原型其他页） */
    key: string;
    path: string;
    icon?: typeof Maximize2;
    /** 原型其他页：跨端口的静态页，新窗口打开 */
    external?: boolean;
    badge?: "new";
};

export type NavGroup = {
    key: string;
    /** 分组右侧的小字说明 */
    note?: string;
    items: NavItem[];
};

/** 原型（8901）的地址。部署后可用 VITE_PROTO_BASE 覆盖。 */
export const PROTO_BASE =
    (import.meta.env.VITE_PROTO_BASE as string | undefined)?.replace(/\/$/, "") || "http://127.0.0.1:8901";

const proto = (path: string) => `${PROTO_BASE}/${path}`;

export const navigationGroups: NavGroup[] = [
    {
        key: "workbench",
        note: "整屏应用",
        items: [
            { key: "canvas", path: "/canvas", icon: Maximize2 },
            { key: "image", path: "/image", icon: ImagePlus },
            { key: "video", path: "/video", icon: Video },
        ],
    },
    {
        key: "content",
        items: [
            { key: "prompts", path: "/prompts", icon: FileText, badge: "new" },
            { key: "assets", path: "/assets", icon: Images },
        ],
    },
    {
        key: "protoPages",
        note: "待迁入",
        items: [
            { key: "characters", path: proto("features/characters.html"), external: true },
            { key: "storyDesk", path: proto("features/story-desk.html"), external: true },
            { key: "assetsHome", path: proto("features/assets-home.html"), external: true },
            { key: "photoRef", path: proto("photo-ref/index.html"), external: true },
            { key: "tasks", path: proto("features/tasks.html"), external: true },
            { key: "accounts", path: proto("features/accounts.html"), external: true },
        ],
    },
    {
        key: "system",
        items: [{ key: "config", path: "/config", icon: Settings2 }],
    },
];

/** 当前路径命中的导航项（canvas/:id 也算画布）。 */
export function findActiveNav(pathname: string) {
    for (const group of navigationGroups) {
        for (const item of group.items) {
            if (item.external) continue;
            if (pathname === item.path || pathname.startsWith(`${item.path}/`)) {
                return { group, item };
            }
        }
    }
    return null;
}
