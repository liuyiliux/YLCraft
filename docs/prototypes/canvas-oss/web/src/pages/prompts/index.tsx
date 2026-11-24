import { type UIEvent, useEffect, useState } from "react";
import { App, Button, Empty, Input, Spin, Switch, Tooltip } from "antd";
import { Database, RefreshCw, Search } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PromptChip, PromptDetailDrawer, PromptLibraryCard } from "@/components/prompts/prompt-library-dialog";
import { usePromptList } from "@/components/prompts/use-prompt-list";
import { useCopyText } from "@/hooks/use-copy-text";
import { cn } from "@/lib/utils";
import { ALL_MODEL_GROUPS_OPTION, ALL_PROMPTS_OPTION, fetchPromptSourceStatuses, refreshAllSources, type Prompt } from "@/services/api/prompts";
import { usePromptSourceStore } from "@/stores/use-prompt-source-store";
import { useAssetStore } from "@/stores/use-asset-store";

/** Standalone prompt library page, styled after YLCraft's real
 *  frontend/src/pages/prompt-library: hero + command panel + filter panel +
 *  card grid + detail drawer. Uses the same shared card/detail components as
 *  the canvas / image / video dialogs. */
export default function PromptsPage() {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const copyText = useCopyText();
    const queryClient = useQueryClient();
    const addAsset = useAssetStore((state) => state.addAsset);
    const sources = usePromptSourceStore((state) => state.sources);
    const [favorites, setFavorites] = useState<Set<string>>(new Set());

    const [keyword, setKeyword] = useState("");
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [selectedCategory, setSelectedCategory] = useState(ALL_PROMPTS_OPTION);
    const [selectedModelGroup, setSelectedModelGroup] = useState(ALL_MODEL_GROUPS_OPTION);
    const [tagExpanded, setTagExpanded] = useState(false);
    const [detail, setDetail] = useState<Prompt | null>(null);
    const [refreshing, setRefreshing] = useState(false);
    const [remoteUpdate, setRemoteUpdate] = useState(false);

    const { query, items, tags: promptTags, categories, modelGroups, total } = usePromptList({ keyword, tags: selectedTags, category: selectedCategory, modelGroup: selectedModelGroup });
    const statusQuery = useQuery({ queryKey: ["prompt-source-statuses"], queryFn: fetchPromptSourceStatuses });

    useEffect(() => {
        if (query.isError) message.error(query.error instanceof Error ? query.error.message : t("prompts.loadFailed"));
    }, [message, query.error, query.isError, t]);

    const statuses = statusQuery.data || {};
    const syncedCount = Object.values(statuses).filter((status) => status.count > 0).length;
    const syncingCount = Object.values(statuses).filter((status) => status.lastError).length;

    const doRefresh = async () => {
        setRefreshing(true);
        try {
            const result = await refreshAllSources();
            await Promise.all([queryClient.invalidateQueries({ queryKey: ["prompts"] }), queryClient.invalidateQueries({ queryKey: ["prompt-source-statuses"] })]);
            message.success(t("prompts.refreshSuccess", { count: result.total }));
        } catch (error) {
            message.error(error instanceof Error ? error.message : t("prompts.refreshFailed"));
        } finally {
            setRefreshing(false);
        }
    };

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
    const toggleTag = (tag: string) => {
        if (tag === ALL_PROMPTS_OPTION) return setSelectedTags([]);
        setSelectedTags((current) => (current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]));
    };
    const handleScroll = (event: UIEvent<HTMLDivElement>) => {
        const target = event.currentTarget;
        if (query.hasNextPage && !query.isFetchingNextPage && target.scrollTop + target.clientHeight >= target.scrollHeight - 220) void query.fetchNextPage();
    };
    const clearFilters = () => {
        setKeyword("");
        setSelectedTags([]);
        setSelectedCategory(ALL_PROMPTS_OPTION);
        setSelectedModelGroup(ALL_MODEL_GROUPS_OPTION);
    };

    return (
        <div className="thin-scrollbar h-full overflow-y-auto bg-background text-stone-800 dark:text-stone-100" onScroll={handleScroll}>
            <div className="mx-auto max-w-[1560px] space-y-4 px-4 py-6 sm:px-6 lg:py-8">
                {/* Hero */}
                <section className="flex flex-col gap-6 rounded-2xl border border-stone-200 bg-gradient-to-br from-amber-50/60 via-white to-stone-50 p-6 dark:border-stone-800 dark:from-amber-950/20 dark:via-stone-900 dark:to-stone-900 lg:flex-row lg:items-end lg:justify-between">
                    <div className="min-w-0">
                        <div className="mb-2 flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400"><Database className="size-3" /><span>Image Prompt References</span></div>
                        <h1 className="text-3xl font-bold leading-tight text-stone-950 dark:text-stone-50">{t("prompts.title")}</h1>
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500 dark:text-stone-400">{t("prompts.heroDescription") || "本地优先浏览 IMI 与开源提示词集合，先找图感、构图和模型案例，再送入画布或生图链路。"}</p>
                        <div className="mt-4 flex flex-wrap gap-4 text-xs text-stone-500 dark:text-stone-400">
                            <span className="font-medium text-stone-700 dark:text-stone-200">{total.toLocaleString("zh-CN")} {t("prompts.caseUnit") || "条案例"}</span>
                            <span>{syncedCount} {t("prompts.syncedSources") || "个来源已同步"}</span>
                            {syncingCount ? <span className="text-red-500">{syncingCount} {t("prompts.failed") || "个失败"}</span> : null}
                        </div>
                    </div>
                    <div className="w-full shrink-0 rounded-xl border border-stone-200 bg-white/80 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-800/60 lg:w-[420px]">
                        <div className="mb-2 flex flex-wrap gap-2">
                            <Button size="small" type="primary" disabled>{t("prompts.videoTemplate") || "视频提示词模板"}</Button>
                            <Button size="small" disabled>{t("prompts.platformTemplate") || "平台/创作模板"}</Button>
                        </div>
                        <Input size="large" allowClear prefix={<Search className="size-4" />} placeholder={t("prompts.search")} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                        <div className="mt-3 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Switch size="small" checked={remoteUpdate} onChange={setRemoteUpdate} disabled />
                                <span className="text-xs text-stone-500">{remoteUpdate ? t("prompts.remoteUpdate") || "远程更新" : t("prompts.localOnly") || "仅本地"}</span>
                            </div>
                            <Tooltip title={t("prompts.refreshHint") || "从各来源重新拉取并重建本地索引"}>
                                <Button size="small" icon={<RefreshCw className="size-3.5" />} loading={refreshing} onClick={() => void doRefresh()}>{remoteUpdate ? t("prompts.updateRemote") || "更新远程源" : t("prompts.rebuildIndex") || "重建本地索引"}</Button>
                            </Tooltip>
                        </div>
                    </div>
                </section>

                {/* Filter panel */}
                <section className="rounded-xl border border-stone-200 bg-white/70 p-4 dark:border-stone-800 dark:bg-stone-900/50">
                    <div className="mb-2 text-xs font-semibold text-stone-500 dark:text-stone-400">{t("prompts.modelGroup") || "模型集合"}</div>
                    <div className="mb-4 flex flex-wrap gap-1.5">
                        {modelGroups.map((value) => <PromptChip key={value} active={selectedModelGroup === value} onClick={() => setSelectedModelGroup(value)}>{value === ALL_MODEL_GROUPS_OPTION ? t("common.all") : value}</PromptChip>)}
                    </div>
                    <div className="mb-2 flex items-center justify-between text-xs font-semibold text-stone-500 dark:text-stone-400"><span>{t("prompts.category")} / {t("prompts.tags")}</span><button type="button" className="font-normal text-amber-600 hover:underline dark:text-amber-400" onClick={() => setTagExpanded(!tagExpanded)}>{tagExpanded ? t("prompts.collapse") || "收起" : t("prompts.more") || "更多"}</button></div>
                    <div className="flex flex-wrap gap-1.5">
                        {categories.map((value) => <PromptChip key={value} active={selectedCategory === value} onClick={() => setSelectedCategory(value)}>{value === ALL_PROMPTS_OPTION ? t("common.all") : value}</PromptChip>)}
                        {(tagExpanded ? promptTags : promptTags.slice(0, 42)).map((value) => {
                            const active = value === ALL_PROMPTS_OPTION ? selectedTags.length === 0 : selectedTags.includes(value);
                            return <PromptChip key={value} active={active} onClick={() => toggleTag(value)}>{value === ALL_PROMPTS_OPTION ? t("common.all") : value}</PromptChip>;
                        })}
                    </div>
                    {selectedTags.length || selectedCategory !== ALL_PROMPTS_OPTION || selectedModelGroup !== ALL_MODEL_GROUPS_OPTION || keyword ? (
                        <button type="button" className="mt-3 text-xs text-stone-500 underline dark:text-stone-400" onClick={clearFilters}>{t("prompts.clearFilters") || "清空筛选"}</button>
                    ) : null}
                </section>

                {/* Result bar */}
                <div className="flex items-center justify-between px-1 text-xs text-stone-500 dark:text-stone-400">
                    <span>{t("prompts.allSources") || "全部来源"} · {t("prompts.pageInfo", { total }) || `${total} 条结果`}</span>
                    <span>{sources.filter((source) => source.enabled).length} {t("prompts.enabledSources") || "个来源启用"}</span>
                </div>

                {/* Card grid */}
                {query.isLoading ? <div className="flex h-60 items-center justify-center"><Spin description={t("prompts.loading")} /></div> : null}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" data-canvas-no-zoom>
                    {items.map((item) => <PromptLibraryCard key={item.id} item={item} onOpen={() => setDetail(item)} onUse={(prompt) => copyText(prompt, t("prompts.promptCopied") || t("prompts.use"))} onSaveAsset={savePromptAsset} onToggleFavorite={toggleFavorite} isFavorite={(item) => favorites.has(item.id)} />)}
                </div>
                {!query.isLoading && items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("prompts.empty")} className="py-16" /> : null}
                <div className="py-4 text-center text-xs text-stone-400">{query.isFetchingNextPage ? t("prompts.loading") : query.hasNextPage ? t("prompts.loadMore") : items.length ? t("prompts.end") : null}</div>
            </div>

            <PromptDetailDrawer item={detail} onClose={() => setDetail(null)} onUse={(prompt) => copyText(prompt, t("prompts.promptCopied") || t("prompts.use"))} onSaveAsset={savePromptAsset} onToggleFavorite={toggleFavorite} isFavorite={(item) => favorites.has(item.id)} />
        </div>
    );
}
