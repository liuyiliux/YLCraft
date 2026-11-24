import { Bookmark, BookmarkCheck, BookOpen, Check, Copy, FileText, FolderPlus, Images, Search, Send, X } from "lucide-react";
import { type UIEvent, useEffect, useState } from "react";
import { App, Button, Drawer, Empty, Input, Modal, Spin, Tooltip } from "antd";
import { useTranslation } from "react-i18next";

import { ALL_MODEL_GROUPS_OPTION, ALL_PROMPTS_OPTION, type Prompt } from "@/services/api/prompts";
import { useCopyText } from "@/hooks/use-copy-text";
import { cn } from "@/lib/utils";
import { usePromptList } from "./use-prompt-list";

export type PromptLibraryCallbacks = {
    /** Insert the prompt into the current editor (canvas node / generation page). */
    onUse?: (prompt: string, item: Prompt) => void;
    /** Save the prompt into the user's asset library. */
    onSaveAsset?: (item: Prompt) => void;
    /** Toggle a local bookmark. */
    onToggleFavorite?: (item: Prompt, favorited: boolean) => void;
    isFavorite?: (item: Prompt) => boolean;
};

/** Shared prompt library used by canvas nodes, image / video workbenches and
 *  the standalone prompts page. Filters follow YLCraft's PromptReferencePicker
 *  (dataset / model group / source / tags), and the detail panel mirrors the
 *  YLCraft original: large image on the left, bilingual prompts with their own
 *  copy buttons on the right, a "style" tag section and an action bar. */
export function PromptLibraryDialog({ open, onOpenChange, title, embedded = false, ...callbacks }: { open: boolean; onOpenChange: (open: boolean) => void; title?: string; embedded?: boolean } & PromptLibraryCallbacks) {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const [keyword, setKeyword] = useState("");
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [selectedCategory, setSelectedCategory] = useState(ALL_PROMPTS_OPTION);
    const [selectedModelGroup, setSelectedModelGroup] = useState(ALL_MODEL_GROUPS_OPTION);
    const [selectedDataset, setSelectedDataset] = useState(ALL_PROMPTS_OPTION);
    const [tagExpanded, setTagExpanded] = useState(false);
    const [detail, setDetail] = useState<Prompt | null>(null);
    const { query, items, tags: promptTags, categories: promptCategories, modelGroups, datasets, total } = usePromptList({ keyword, tags: selectedTags, category: selectedCategory, modelGroup: selectedModelGroup, dataset: selectedDataset, enabled: open });

    useEffect(() => {
        if (query.isError) message.error(query.error instanceof Error ? query.error.message : t("prompts.loadFailed"));
    }, [message, query.error, query.isError, t]);

    useEffect(() => {
        if (!open) setDetail(null);
    }, [open]);

    const toggleTag = (tag: string) => {
        if (tag === ALL_PROMPTS_OPTION) return setSelectedTags([]);
        setSelectedTags((current) => (current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]));
    };

    const handleListScroll = (event: UIEvent<HTMLDivElement>) => {
        const target = event.currentTarget;
        if (query.hasNextPage && !query.isFetchingNextPage && target.scrollTop + target.clientHeight >= target.scrollHeight - 220) void query.fetchNextPage();
    };

    const content = (
        <div className={cn("grid min-h-0 gap-4", embedded ? "h-full lg:grid-cols-[220px_minmax(0,1fr)]" : "h-[66dvh] sm:grid-cols-[220px_minmax(0,1fr)]")} data-canvas-no-zoom onWheelCapture={(event) => event.stopPropagation()}>
            <aside className="thin-scrollbar min-h-0 space-y-4 overflow-y-auto border-r border-stone-200 pr-3 text-sm dark:border-stone-800">
                <FilterGroup label={t("prompts.dataset") || "数据集"}>
                    {datasets.map((value) => (
                        <PromptChip key={value} active={selectedDataset === value} onClick={() => setSelectedDataset(value)}>
                            {value === ALL_PROMPTS_OPTION ? t("common.all") : value === "ylcraft-imi" ? "YLCraft 下载库" : value === "reference-project" ? "参考项目" : value}
                        </PromptChip>
                    ))}
                </FilterGroup>
                <FilterGroup label={t("prompts.modelGroup") || "模型集合"}>
                    {modelGroups.map((value) => (
                        <PromptChip key={value} active={selectedModelGroup === value} onClick={() => setSelectedModelGroup(value)}>
                            {value === ALL_MODEL_GROUPS_OPTION ? t("common.all") : value}
                        </PromptChip>
                    ))}
                </FilterGroup>
                <FilterGroup label={t("prompts.category")}>
                    {promptCategories.map((value) => (
                        <PromptChip key={value} active={selectedCategory === value} onClick={() => setSelectedCategory(value)}>
                            {value === ALL_PROMPTS_OPTION ? t("common.all") : value}
                        </PromptChip>
                    ))}
                </FilterGroup>
                <FilterGroup label={t("prompts.tags")} action={promptTags.length > 30 ? <button type="button" className="text-[11px] text-amber-600 hover:underline dark:text-amber-400" onClick={() => setTagExpanded(!tagExpanded)}>{tagExpanded ? t("prompts.collapse") || "收起" : t("prompts.more") || "更多"}</button> : undefined}>
                    {(tagExpanded ? promptTags : promptTags.slice(0, 30)).map((value) => {
                        const active = value === ALL_PROMPTS_OPTION ? selectedTags.length === 0 : selectedTags.includes(value);
                        return <PromptChip key={value} active={active} onClick={() => toggleTag(value)}>{value === ALL_PROMPTS_OPTION ? t("common.all") : value}</PromptChip>;
                    })}
                </FilterGroup>
            </aside>
            <section className="flex min-h-0 min-w-0 flex-col">
                <div className="flex items-center gap-3">
                    <Input size="large" prefix={<Search className="size-4 text-stone-400" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={t("prompts.search")} allowClear />
                    <span className="shrink-0 text-xs text-stone-500 dark:text-stone-400">{t("prompts.total", { count: total })}</span>
                </div>
                {selectedTags.length || (selectedCategory !== ALL_PROMPTS_OPTION) || (selectedModelGroup !== ALL_MODEL_GROUPS_OPTION) || (selectedDataset !== ALL_PROMPTS_OPTION) ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
                        {selectedDataset !== ALL_PROMPTS_OPTION ? <ActiveFilter label={selectedDataset} onClear={() => setSelectedDataset(ALL_PROMPTS_OPTION)} /> : null}
                        {selectedModelGroup !== ALL_MODEL_GROUPS_OPTION ? <ActiveFilter label={selectedModelGroup} onClear={() => setSelectedModelGroup(ALL_MODEL_GROUPS_OPTION)} /> : null}
                        {selectedCategory !== ALL_PROMPTS_OPTION ? <ActiveFilter label={selectedCategory} onClear={() => setSelectedCategory(ALL_PROMPTS_OPTION)} /> : null}
                        {selectedTags.map((tag) => <ActiveFilter key={tag} label={tag} onClear={() => toggleTag(tag)} />)}
                    </div>
                ) : null}
                <div className="thin-scrollbar mt-3 min-h-0 flex-1 overflow-y-auto pr-2" data-canvas-no-zoom onScroll={handleListScroll} onWheelCapture={(event) => event.stopPropagation()}>
                    {query.isLoading ? <div className="flex h-40 items-center justify-center"><Spin description={t("prompts.loading")} /></div> : null}
                    <div className="grid gap-4 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
                        {items.map((item) => <PromptLibraryCard key={item.id} item={item} onOpen={() => setDetail(item)} {...callbacks} />)}
                    </div>
                    {!query.isLoading && items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("prompts.empty")} className="py-10" /> : null}
                    {query.isFetchingNextPage ? <div className="py-4 text-center"><Spin size="small" /></div> : null}
                    {items.length > 0 && !query.hasNextPage ? <div className="py-4 text-center text-xs text-stone-400">{t("prompts.end")}</div> : null}
                </div>
            </section>
        </div>
    );

    if (embedded) return <>{content}<PromptDetailDrawer item={detail} onClose={() => setDetail(null)} {...callbacks} /></>;

    return (
        <>
            <Modal title={title || t("prompts.library")} open={open} onCancel={() => onOpenChange(false)} footer={null} width={1180} centered destroyOnHidden>
                {content}
            </Modal>
            <PromptDetailDrawer item={detail} onClose={() => setDetail(null)} {...callbacks} />
        </>
    );
}

function FilterGroup({ label, children, action }: { label: string; children: React.ReactNode; action?: React.ReactNode }) {
    return (
        <div>
            <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500"><span>{label}</span>{action}</div>
            <div className="prompt-chip-list flex flex-wrap gap-1.5">{children}</div>
        </div>
    );
}

/** YLCraft-style filter chip (prompt-filter-chip equivalent). */
function PromptChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
        <button type="button" onClick={onClick} className={cn("rounded-full border px-2.5 py-1 text-xs transition", active ? "border-amber-500 bg-amber-500/15 font-medium text-amber-700 dark:text-amber-300" : "border-stone-200 bg-stone-50 text-stone-600 hover:border-stone-300 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300")}>
            {children}
        </button>
    );
}

function ActiveFilter({ label, onClear }: { label: string; onClear: () => void }) {
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-700 dark:text-amber-300">{label}<button type="button" onClick={onClear} aria-label={`清除 ${label}`}><X className="size-3" /></button></span>
    );
}

function PromptLibraryCard({ item, onOpen, onUse, onSaveAsset, onToggleFavorite, isFavorite }: { item: Prompt; onOpen: () => void } & PromptLibraryCallbacks) {
    const { t } = useTranslation();
    const favorite = isFavorite?.(item) || false;
    return (
        <div className="group flex min-w-0 flex-col overflow-hidden rounded-xl border border-stone-200 bg-white transition hover:border-stone-300 hover:shadow-md dark:border-stone-700 dark:bg-stone-900">
            <div className="relative block w-full overflow-hidden bg-stone-100 dark:bg-stone-800">
                <button type="button" className="block w-full" onClick={onOpen} aria-label={item.title}>
                    {item.coverUrl ? <img src={item.coverUrl} alt={item.title} className="aspect-[4/3] w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" onError={(event) => { event.currentTarget.style.display = "none"; }} /> : <span className="grid aspect-[4/3] w-full place-items-center text-stone-400"><FileText className="size-9" /></span>}
                </button>
                {item.modelGroup ? <span className="pointer-events-none absolute bottom-1.5 left-1.5 rounded-md bg-black/65 px-1.5 py-0.5 text-[10px] text-white">{item.modelGroup}</span> : null}
                {onToggleFavorite ? (
                    <button type="button" onClick={() => onToggleFavorite(item, !favorite)} className="absolute right-1.5 top-1.5 grid size-7 place-items-center rounded-full bg-black/55 text-white" aria-label={favorite ? "取消收藏" : "收藏"}>
                        {favorite ? <BookmarkCheck className="size-3.5" /> : <Bookmark className="size-3.5" />}
                    </button>
                ) : null}
            </div>
            <div className="flex min-w-0 flex-1 flex-col p-2.5">
                <button type="button" className="min-w-0 text-left" onClick={onOpen}>
                    <div className="line-clamp-1 text-xs font-semibold text-stone-900 dark:text-stone-100">{item.title}</div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-stone-500 dark:text-stone-400">{item.prompt}</div>
                </button>
                <div className="mt-auto flex flex-wrap gap-1 pt-2">
                    {item.tags.slice(0, 3).map((tag) => <span key={tag} className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500 dark:bg-stone-800 dark:text-stone-400">{tag}</span>)}
                </div>
            </div>
        </div>
    );
}

/** YLCraft-style detail drawer: image left, bilingual prompt sections right. */
function PromptDetailDrawer({ item, onClose, onUse, onSaveAsset, onToggleFavorite, isFavorite }: { item: Prompt | null; onClose: () => void } & PromptLibraryCallbacks) {
    const { t, i18n } = useTranslation();
    const copyText = useCopyText();
    const [copied, setCopied] = useState<"cn" | "en" | null>(null);
    const favorite = item ? isFavorite?.(item) || false : false;
    const copy = (which: "cn" | "en", value: string) => {
        copyText(value, t("prompts.promptCopied") || t("prompts.use"));
        setCopied(which);
        setTimeout(() => setCopied(null), 1600);
    };
    return (
        <Drawer title={item?.title || t("prompts.library")} open={Boolean(item)} onClose={onClose} size="min(1100px, 92vw)" destroyOnHidden extra={item ? (
            <div className="flex flex-wrap items-center gap-2">
                {onToggleFavorite ? <Button size="small" icon={favorite ? <BookmarkCheck className="size-3.5" /> : <Bookmark className="size-3.5" />} onClick={() => onToggleFavorite(item, !favorite)}>{favorite ? "已收藏" : "收藏"}</Button> : null}
                <Button size="small" icon={<Copy className="size-3.5" />} onClick={() => copy("cn", item.prompt)}>{t("common.copy")}</Button>
                {onSaveAsset ? <Button size="small" icon={<FolderPlus className="size-3.5" />} onClick={() => onSaveAsset(item)}>{t("common.addToAssets")}</Button> : null}
                {onUse ? <Button type="primary" size="small" icon={<Send className="size-3.5" />} onClick={() => onUse(item.prompt, item)}>{t("prompts.use")}</Button> : null}
            </div>
        ) : undefined}>
            {item ? <PromptDetailBody item={item} copied={copied} onCopy={copy} i18nLocale={i18n.resolvedLanguage} /> : null}
        </Drawer>
    );
}

function PromptDetailBody({ item, copied, onCopy, i18nLocale }: { item: Prompt; copied: "cn" | "en" | null; onCopy: (which: "cn" | "en", value: string) => void; i18nLocale?: string }) {
    const { t } = useTranslation();
    return (
        <div className="grid min-h-[60vh] gap-5 lg:grid-cols-[minmax(0,44%)_minmax(0,1fr)]" data-canvas-no-zoom>
            <div className="min-w-0">
                {item.coverUrl ? <img src={item.coverUrl} alt={item.title} className="aspect-square w-full rounded-xl object-cover" onError={(event) => { event.currentTarget.style.display = "none"; }} /> : <div className="grid aspect-square w-full place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><FileText className="size-16" /></div>}
                <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.modelGroup ? <span className="rounded-full border border-stone-200 px-2 py-0.5 text-[11px] text-stone-500 dark:border-stone-700">{item.modelGroup}</span> : null}
                    <span className="rounded-full border border-stone-200 px-2 py-0.5 text-[11px] text-stone-500 dark:border-stone-700">{item.sourceName}</span>
                    {item.referenceImageUrls.length > 1 ? <span className="inline-flex items-center gap-1 rounded-full border border-stone-200 px-2 py-0.5 text-[11px] text-stone-500 dark:border-stone-700"><Images className="size-3" />{item.referenceImageUrls.length}</span> : null}
                </div>
            </div>
            <div className="thin-scrollbar min-w-0 space-y-4 overflow-y-auto pr-1">
                <PromptTextSection label={t("prompts.promptText") || "提示词正文"} value={item.prompt} copied={copied === "cn"} onCopy={() => onCopy("cn", item.prompt)} />
                {item.englishPrompt && item.englishPrompt !== item.prompt ? <PromptTextSection label="English prompt" value={item.englishPrompt} copied={copied === "en"} onCopy={() => onCopy("en", item.englishPrompt || "")} /> : null}
                {item.description ? <p className="rounded-lg bg-stone-50 p-3 text-xs leading-5 text-stone-600 dark:bg-stone-800 dark:text-stone-300">{item.description}</p> : null}
                <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400">{t("prompts.style") || "风格"}</div>
                    <div className="flex flex-wrap gap-1.5">
                        {item.tags.map((tag) => <span key={tag} className="rounded-md bg-stone-100 px-2 py-1 text-[11px] text-stone-600 dark:bg-stone-800 dark:text-stone-300">{tag}</span>)}
                        {item.tags.length === 0 ? <span className="text-xs text-stone-400">—</span> : null}
                    </div>
                </div>
                {item.referenceImageUrls.length ? (
                    <div>
                        <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400">{t("prompts.referenceImages") || "参考图"} · {item.referenceImageUrls.length}</div>
                        <div className="thin-scrollbar flex gap-2 overflow-x-auto pb-1">
                            {item.referenceImageUrls.slice(0, 12).map((url, index) => <img key={`${url}-${index}`} src={url} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" loading="lazy" onError={(event) => { event.currentTarget.style.display = "none"; }} />)}
                        </div>
                    </div>
                ) : null}
                <div className="flex flex-wrap gap-3 text-xs text-stone-500 dark:text-stone-400">
                    {item.likeCount ? <span>♥ {item.likeCount}</span> : null}{item.viewCount ? <span>👁 {item.viewCount}</span> : null}{item.copyCount ? <span><Copy className="mr-1 inline size-3" />{item.copyCount}</span> : null}
                    {item.updatedAt ? <span className="ml-auto">{new Intl.DateTimeFormat(i18nLocale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(item.updatedAt))}</span> : null}
                </div>
            </div>
        </div>
    );
}

function PromptTextSection({ label, value, copied, onCopy }: { label: string; value: string; copied: boolean; onCopy: () => void }) {
    const { t } = useTranslation();
    return (
        <div>
            <div className="mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-stone-400"><BookOpen className="size-3.5" />{label}</span>
                <Button type="text" size="small" className="!h-6 !px-1.5 !text-[11px]" icon={copied ? <Check className="size-3" /> : <Copy className="size-3" />} onClick={onCopy}>{copied ? t("common.copied") : t("common.copy")}</Button>
            </div>
            <pre className="thin-scrollbar max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-5 dark:border-stone-700 dark:bg-stone-900">{value}</pre>
        </div>
    );
}
