import { type UIEvent, useEffect, useState } from "react";
import { App, Button, Empty, Input, Spin, Tooltip } from "antd";
import { Database, RefreshCw, Search } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PromptChip, PromptDetailDrawer, PromptLibraryCard } from "@/components/prompts/prompt-library-dialog";
import { usePromptList } from "@/components/prompts/use-prompt-list";
import { useCopyText } from "@/hooks/use-copy-text";
import { ALL_MODEL_GROUPS_OPTION, ALL_PROMPTS_OPTION, fetchPromptSourceStatuses, refreshAllSources, type Prompt } from "@/services/api/prompts";
import { usePromptSourceStore } from "@/stores/use-prompt-source-store";
import { useAssetStore } from "@/stores/use-asset-store";

/** Standalone prompt library page — layout mirrors YLCraft's real
 *  frontend/src/pages/prompt-library: centred hero (title / subtitle / stat
 *  pills), a 760px command panel, a full-width filter bar with a 96px label
 *  column, then an auto-fill card grid (minmax 278px) and the detail drawer.
 *  Cards + drawer + chips are the shared components the dialogs use. */
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

    const { query, items, tags: promptTags, categories, modelGroups, total } = usePromptList({ keyword, tags: selectedTags, category: selectedCategory, modelGroup: selectedModelGroup });
    const statusQuery = useQuery({ queryKey: ["prompt-source-statuses"], queryFn: fetchPromptSourceStatuses });

    useEffect(() => {
        if (query.isError) message.error(query.error instanceof Error ? query.error.message : t("prompts.loadFailed"));
    }, [message, query.error, query.isError, t]);

    const statuses = statusQuery.data || {};
    const syncedCount = Object.values(statuses).filter((status) => status.count > 0).length;
    const failedCount = Object.values(statuses).filter((status) => status.lastError).length;

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

    const visibleTags = tagExpanded ? promptTags : promptTags.slice(0, 42);

    return (
        <div className="thin-scrollbar h-full overflow-y-auto bg-background text-stone-800 dark:text-stone-100" onScroll={handleScroll}>
            <div className="mx-auto w-[min(1320px,calc(100vw-48px))] space-y-4 pt-9 pb-10">
                {/* Hero — centred copy + command panel */}
                <section className="grid gap-6">
                    <div className="grid justify-items-center gap-2.5 text-center">
                        <div className="flex items-center gap-2 text-[13px] text-stone-500 dark:text-stone-400">
                            <Database className="size-3.5 text-teal-600 dark:text-cyan-300" />
                            <span>Image Prompt References</span>
                        </div>
                        <h1 className="text-balance text-[clamp(34px,4vw,56px)] font-bold leading-[1.05] text-stone-950 dark:text-stone-50">{t("prompts.title")}</h1>
                        <p className="max-w-2xl text-sm leading-6 text-stone-500 dark:text-stone-400">{t("prompts.heroDescription")}</p>
                        <div className="mt-2 flex flex-wrap justify-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                            <span className="rounded-lg border border-stone-200 bg-white/70 px-2 py-1.5 font-medium text-stone-700 dark:border-stone-700 dark:bg-white/5 dark:text-stone-200">{total.toLocaleString("zh-CN")} {t("prompts.caseUnit") || "条案例"}</span>
                            <span className="rounded-lg border border-stone-200 bg-white/70 px-2 py-1.5 dark:border-stone-700 dark:bg-white/5">{syncedCount} {t("prompts.syncedSources") || "个来源已同步"}</span>
                            {failedCount ? <span className="rounded-lg border border-red-200 px-2 py-1.5 text-red-500 dark:border-red-900">{failedCount} {t("prompts.failed") || "个失败"}</span> : null}
                        </div>
                    </div>

                    <div className="mx-auto grid w-[min(760px,100%)] content-center gap-3 rounded-[15px] border border-stone-200 bg-white/75 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,.7)] dark:border-stone-700 dark:bg-stone-900/50 dark:shadow-[inset_0_1px_0_rgba(255,255,255,.04)]">
                        <div className="flex flex-wrap gap-2">
                            <Button size="small" type="primary" disabled>{t("prompts.videoTemplate") || "视频提示词模板"}</Button>
                            <Button size="small" disabled>{t("prompts.platformTemplate") || "平台/创作模板"}</Button>
                        </div>
                        <Input
                            size="large"
                            allowClear
                            className="h-[46px] rounded-xl"
                            prefix={<Search className="size-4 text-stone-400" />}
                            placeholder={t("prompts.searchPlaceholder") || "搜索标题、提示词、风格或分类"}
                            value={keyword}
                            onChange={(event) => setKeyword(event.target.value)}
                        />
                        <div className="flex flex-wrap items-center justify-between gap-2.5">
                            <span className="text-xs text-stone-500 dark:text-stone-400">{t("prompts.sourceModeHint") || "各来源的本地/在线同步方式在「设置 → 提示词来源」里配置"}</span>
                            <Tooltip title={t("prompts.refreshHint") || "按各来源当前配置重新拉取并刷新缓存"}>
                                <Button icon={<RefreshCw className="size-3.5" />} loading={refreshing} onClick={() => void doRefresh()}>{t("prompts.syncSources") || "重新同步来源"}</Button>
                            </Tooltip>
                        </div>
                    </div>
                </section>

                {/* Filter bar — 96px label column like .prompt-filter-section */}
                <section className="grid gap-3 overflow-hidden rounded-2xl border border-stone-200 bg-white/70 px-4 py-3.5 dark:border-stone-800 dark:bg-white/[.025]">
                    <FilterRow label={t("prompts.modelGroup") || "模型集合"}>
                        {modelGroups.map((value) => (
                            <PromptChip key={value} active={selectedModelGroup === value} onClick={() => setSelectedModelGroup(value)}>{value === ALL_MODEL_GROUPS_OPTION ? t("common.all") : value}</PromptChip>
                        ))}
                    </FilterRow>
                    <FilterRow
                        label={`${t("prompts.category")} / ${t("prompts.tags")}`}
                        action={promptTags.length > 42 ? (
                            <button type="button" className="shrink-0 text-xs font-normal text-stone-500 hover:underline dark:text-stone-400" onClick={() => setTagExpanded(!tagExpanded)}>{tagExpanded ? t("prompts.collapse") || "收起" : t("prompts.more") || "更多"}</button>
                        ) : undefined}
                    >
                        <PromptChip active={!selectedTags.length && selectedCategory === ALL_PROMPTS_OPTION} onClick={() => { toggleTag(ALL_PROMPTS_OPTION); setSelectedCategory(ALL_PROMPTS_OPTION); }}>{t("common.all")}</PromptChip>
                        {categories.map((value) => (
                            <PromptChip key={`cat-${value}`} active={selectedCategory === value} onClick={() => setSelectedCategory(selectedCategory === value ? ALL_PROMPTS_OPTION : value)}>{value}</PromptChip>
                        ))}
                        {visibleTags.map((value) => (
                            <PromptChip key={`tag-${value}`} active={selectedTags.includes(value)} onClick={() => toggleTag(value)}>{value}</PromptChip>
                        ))}
                    </FilterRow>
                    {selectedTags.length || selectedCategory !== ALL_PROMPTS_OPTION || selectedModelGroup !== ALL_MODEL_GROUPS_OPTION || keyword ? (
                        <button type="button" className="justify-self-start text-xs text-stone-500 underline hover:text-stone-700 dark:text-stone-400" onClick={clearFilters}>{t("prompts.clearFilters") || "清空筛选"}</button>
                    ) : null}
                </section>

                {/* Result head */}
                <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-stone-500 dark:text-stone-400">
                    <span>{t("prompts.allSources") || "全部来源"} · {t("prompts.pageInfo", { total }) || `${total} 条结果`}</span>
                    <span>{sources.filter((source) => source.enabled).length} {t("prompts.enabledSources") || "个来源启用"}</span>
                </div>

                {/* Card grid */}
                {query.isLoading ? <div className="flex h-60 items-center justify-center"><Spin description={t("prompts.loading")} /></div> : null}
                <div className="grid grid-cols-[repeat(auto-fill,minmax(278px,1fr))] gap-4" data-canvas-no-zoom>
                    {items.map((item) => <PromptLibraryCard key={item.id} item={item} onOpen={() => setDetail(item)} onUse={(prompt) => copyText(prompt, t("prompts.promptCopied") || t("prompts.use"))} onSaveAsset={savePromptAsset} onToggleFavorite={toggleFavorite} isFavorite={(entry) => favorites.has(entry.id)} />)}
                </div>
                {!query.isLoading && items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("prompts.empty")} className="py-16" /> : null}
                <div className="py-4 text-center text-xs text-stone-400">{query.isFetchingNextPage ? t("prompts.loading") : query.hasNextPage ? t("prompts.loadMore") : items.length ? t("prompts.end") : null}</div>
            </div>

            <PromptDetailDrawer item={detail} onClose={() => setDetail(null)} onUse={(prompt) => copyText(prompt, t("prompts.promptCopied") || t("prompts.use"))} onSaveAsset={savePromptAsset} onToggleFavorite={toggleFavorite} isFavorite={(entry) => favorites.has(entry.id)} />
        </div>
    );
}

/** One filter row: fixed 96px label column + wrapping chips (matches
 *  .prompt-filter-section { grid-template-columns: 96px minmax(0,1fr) }). */
function FilterRow({ label, action, children }: { label: string; action?: React.ReactNode; children: React.ReactNode }) {
    return (
        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-3">
            <span className="text-xs font-semibold text-stone-600 dark:text-stone-300">{label}</span>
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                {children}
                {action}
            </div>
        </div>
    );
}
