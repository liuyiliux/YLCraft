import { useState } from "react";
import { App } from "antd";
import { useTranslation } from "react-i18next";

import { PromptLibraryDialog } from "@/components/prompts/prompt-library-dialog";
import type { Prompt } from "@/services/api/prompts";
import { useAssetStore } from "@/stores/use-asset-store";

/** Standalone prompt library page — embeds the same shared component used by
 *  canvas / image / video so all surfaces get YLCraft's detail design. */
export default function PromptsPage() {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const addAsset = useAssetStore((state) => state.addAsset);
    const [favorites, setFavorites] = useState<Set<string>>(new Set());

    const savePromptAsset = (item: Prompt) => {
        addAsset({ kind: "text", title: item.title, coverUrl: item.coverUrl, tags: item.tags, source: item.sourceName, data: { content: item.prompt }, metadata: { source: "prompt-library", promptId: item.id, githubUrl: item.githubUrl } });
        message.success(t("common.addedToAssets"));
    };

    const toggleFavorite = (item: Prompt, favorited: boolean) => {
        setFavorites((current) => {
            const next = new Set(current);
            if (favorited) next.add(item.id);
            else next.delete(item.id);
            return next;
        });
        message.success(favorited ? "已收藏" : "已取消收藏");
    };

    return (
        <div className="flex h-full flex-col overflow-hidden bg-background text-stone-800 dark:text-stone-100">
            <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background px-4 py-6 sm:px-6 lg:py-8">
                <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col">
                    <div className="mb-5 text-center">
                        <h1 className="text-2xl font-semibold text-stone-950 dark:text-stone-100">{t("prompts.title")}</h1>
                        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">{t("prompts.library")} · 参考项目 + YLCraft 下载库并集</p>
                    </div>
                    <div className="min-h-0 flex-1 rounded-2xl border border-stone-200 bg-white/60 p-4 dark:border-stone-800 dark:bg-stone-900/40">
                        <PromptLibraryDialog
                            open
                            onOpenChange={() => undefined}
                            embedded
                            onSaveAsset={savePromptAsset}
                            onToggleFavorite={toggleFavorite}
                            isFavorite={(item) => favorites.has(item.id)}
                        />
                    </div>
                </div>
            </main>
        </div>
    );
}
