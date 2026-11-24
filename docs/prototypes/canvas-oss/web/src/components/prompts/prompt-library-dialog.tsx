import { BookOpen, Check, Copy, FileText, Images, Search, Sparkles } from "lucide-react";
import { type UIEvent, useEffect, useState } from "react";
import { App, Button, Drawer, Empty, Input, Modal, Spin, Tag, Tooltip } from "antd";
import { useTranslation } from "react-i18next";

import { ALL_MODEL_GROUPS_OPTION, ALL_PROMPTS_OPTION, type Prompt } from "@/services/api/prompts";
import { useCopyText } from "@/hooks/use-copy-text";
import { cn } from "@/lib/utils";
import { usePromptList } from "./use-prompt-list";

/** Shared prompt library used by canvas nodes, image generation and (later)
 *  video / character pages. Filters follow YLCraft's PromptReferencePicker:
 *  dataset (reference project vs downloaded IMI), model group, source, tags. */
export function PromptLibraryDialog({
    open,
    onOpenChange,
    onSelect,
    title,
    mode = "select",
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelect: (prompt: string, item: Prompt) => void;
    title?: string;
    mode?: "select" | "copy" | "both";
}) {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const copyText = useCopyText();
    const [keyword, setKeyword] = useState("");
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [selectedCategory, setSelectedCategory] = useState(ALL_PROMPTS_OPTION);
    const [selectedModelGroup, setSelectedModelGroup] = useState(ALL_MODEL_GROUPS_OPTION);
    const [selectedDataset, setSelectedDataset] = useState(ALL_PROMPTS_OPTION);
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

    const usePrompt = (item: Prompt) => {
        onSelect(item.prompt, item);
        onOpenChange(false);
    };

    const copyPrompt = (item: Prompt) => {
        copyText(item.prompt, t("prompts.promptCopied") || t("prompts.use"));
    };

    const handleListScroll = (event: UIEvent<HTMLDivElement>) => {
        const target = event.currentTarget;
        if (query.hasNextPage && !query.isFetchingNextPage && target.scrollTop + target.clientHeight >= target.scrollHeight - 200) void query.fetchNextPage();
    };

    return (
        <Modal title={title || t("prompts.library")} open={open} onCancel={() => onOpenChange(false)} footer={null} width={1080} centered destroyOnHidden>
            <div className="grid h-[64dvh] min-h-0 gap-4 sm:grid-cols-[210px_minmax(0,1fr)]" data-canvas-no-zoom onWheelCapture={(event) => event.stopPropagation()}>
                <aside className="thin-scrollbar min-h-0 space-y-4 overflow-y-auto border-r border-stone-200 pr-3 text-sm dark:border-stone-800">
                    <FilterGroup label={t("prompts.dataset") || "数据集"}>
                        {datasets.map((value) => (
                            <Tag.CheckableTag key={value} checked={selectedDataset === value} className={cn("prompt-filter-tag", selectedDataset === value && "is-active")} onChange={() => setSelectedDataset(value)}>
                                {value === ALL_PROMPTS_OPTION ? t("common.all") : value === "ylcraft-imi" ? "YLCraft 下载库" : value === "reference-project" ? "参考项目" : value}
                            </Tag.CheckableTag>
                        ))}
                    </FilterGroup>
                    <FilterGroup label={t("prompts.modelGroup") || "模型集合"}>
                        {modelGroups.map((value) => (
                            <Tag.CheckableTag key={value} checked={selectedModelGroup === value} className={cn("prompt-filter-tag", selectedModelGroup === value && "is-active")} onChange={() => setSelectedModelGroup(value)}>
                                {value === ALL_MODEL_GROUPS_OPTION ? t("common.all") : value}
                            </Tag.CheckableTag>
                        ))}
                    </FilterGroup>
                    <FilterGroup label={t("prompts.category")}>
                        {promptCategories.map((value) => (
                            <Tag.CheckableTag key={value} checked={selectedCategory === value} className={cn("prompt-filter-tag", selectedCategory === value && "is-active")} onChange={() => setSelectedCategory(value)}>
                                {value === ALL_PROMPTS_OPTION ? t("common.all") : value}
                            </Tag.CheckableTag>
                        ))}
                    </FilterGroup>
                    <FilterGroup label={t("prompts.tags")}>
                        {promptTags.slice(0, 60).map((value) => {
                            const active = value === ALL_PROMPTS_OPTION ? selectedTags.length === 0 : selectedTags.includes(value);
                            return (
                                <Tag.CheckableTag key={value} checked={active} className={cn("prompt-filter-tag", active && "is-active")} onChange={() => toggleTag(value)}>
                                    {value === ALL_PROMPTS_OPTION ? t("common.all") : value}
                                </Tag.CheckableTag>
                            );
                        })}
                    </FilterGroup>
                </aside>
                <section className="flex min-h-0 min-w-0 flex-col">
                    <div className="flex items-center gap-3">
                        <Input size="large" prefix={<Search className="size-4 text-stone-400" />} value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={t("prompts.search")} allowClear />
                        <span className="shrink-0 text-xs text-stone-500 dark:text-stone-400">{t("prompts.total", { count: total })}</span>
                    </div>
                    <div className="thin-scrollbar mt-3 min-h-0 flex-1 overflow-y-auto pr-2" data-canvas-no-zoom onScroll={handleListScroll} onWheelCapture={(event) => event.stopPropagation()}>
                        {query.isLoading ? (
                            <div className="flex h-40 items-center justify-center"><Spin description={t("prompts.loading")} /></div>
                        ) : null}
                        <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
                            {items.map((item) => (
                                <PromptLibraryCard key={item.id} item={item} onOpen={() => setDetail(item)} onUse={() => usePrompt(item)} onCopy={() => copyPrompt(item)} mode={mode} />
                            ))}
                        </div>
                        {!query.isLoading && items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("prompts.empty")} className="py-10" /> : null}
                        {query.isFetchingNextPage ? (
                            <div className="py-4 text-center"><Spin size="small" /></div>
                        ) : null}
                        {items.length > 0 && !query.hasNextPage ? <div className="py-4 text-center text-xs text-stone-400">{t("prompts.end")}</div> : null}
                    </div>
                </section>
            </div>

            <Drawer title={detail?.title || t("prompts.library")} open={Boolean(detail)} onClose={() => setDetail(null)} size={560} destroyOnHidden>
                {detail ? <PromptDetail item={detail} onUse={() => usePrompt(detail)} onCopy={() => copyPrompt(detail)} mode={mode} /> : null}
            </Drawer>
        </Modal>
    );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">{label}</div>
            <div className="flex flex-wrap gap-1.5">{children}</div>
        </div>
    );
}

function PromptLibraryCard({ item, onOpen, onUse, onCopy, mode }: { item: Prompt; onOpen: () => void; onUse: () => void; onCopy: () => void; mode: "select" | "copy" | "both" }) {
    const { t } = useTranslation();
    return (
        <div className="group flex min-w-0 flex-col overflow-hidden rounded-xl border border-stone-200 bg-white transition hover:border-stone-300 hover:shadow-md dark:border-stone-700 dark:bg-stone-900">
            <button type="button" className="relative block w-full overflow-hidden bg-stone-100 dark:bg-stone-800" onClick={onOpen} aria-label={item.title}>
                {item.coverUrl ? (
                    <img src={item.coverUrl} alt={item.title} className="aspect-[4/3] w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" onError={(event) => { event.currentTarget.style.display = "none"; }} />
                ) : (
                    <span className="grid aspect-[4/3] w-full place-items-center text-stone-400"><FileText className="size-9" /></span>
                )}
                {item.modelGroup ? <span className="absolute left-2 top-2 rounded-md bg-black/65 px-1.5 py-0.5 text-[10px] font-medium text-white">{item.modelGroup}</span> : null}
                {item.referenceImageUrls.length > 1 ? (
                    <span className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-black/65 px-1.5 py-0.5 text-[10px] text-white"><Images className="size-3" />{item.referenceImageUrls.length}</span>
                ) : null}
            </button>
            <div className="flex min-w-0 flex-1 flex-col p-2.5">
                <button type="button" className="min-w-0 text-left" onClick={onOpen}>
                    <div className="line-clamp-1 text-xs font-semibold text-stone-900 dark:text-stone-100">{item.title}</div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-stone-500 dark:text-stone-400">{item.prompt}</div>
                </button>
                <div className="mt-auto flex items-center gap-1 pt-2">
                    {mode !== "copy" ? (
                        <Button type="primary" size="small" className="!h-7 !px-2 !text-[11px]" icon={<Check className="size-3" />} onClick={onUse}>
                            {t("prompts.use")}
                        </Button>
                    ) : null}
                    {mode !== "select" ? (
                        <Tooltip title={t("common.copy")}>
                            <Button type="text" size="small" className="!h-7 !w-7 !px-0" icon={<Copy className="size-3" />} onClick={onCopy} aria-label={t("common.copy")} />
                        </Tooltip>
                    ) : null}
                    <span className="ml-auto truncate text-[10px] text-stone-400">{item.sourceName}</span>
                </div>
            </div>
        </div>
    );
}

function PromptDetail({ item, onUse, onCopy, mode }: { item: Prompt; onUse: () => void; onCopy: () => void; mode: "select" | "copy" | "both" }) {
    const { t, i18n } = useTranslation();
    const [copied, setCopied] = useState(false);
    const copyText = useCopyText();
    const copy = () => {
        copyText(item.prompt, t("prompts.promptCopied") || t("prompts.use"));
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
    };
    return (
        <div className="space-y-4" data-canvas-no-zoom>
            {item.coverUrl ? <img src={item.coverUrl} alt={item.title} className="aspect-[16/9] w-full rounded-xl object-cover" onError={(event) => { event.currentTarget.style.display = "none"; }} /> : null}
            <div className="flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                <Tag>{item.sourceName}</Tag>
                {item.modelGroup ? <Tag color="blue">{item.modelGroup}</Tag> : null}
                {item.dataset === "ylcraft-imi" ? <Tag color="gold"><Sparkles className="mr-1 inline size-3" />YLCraft 下载库</Tag> : null}
                {item.likeCount ? <span>♥ {item.likeCount}</span> : null}
                {item.viewCount ? <span>👁 {item.viewCount}</span> : null}
                {item.copyCount ? <span><Copy className="mr-1 inline size-3" />{item.copyCount}</span> : null}
                {item.updatedAt ? <span className="ml-auto">{new Intl.DateTimeFormat(i18n.resolvedLanguage, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(item.updatedAt))}</span> : null}
            </div>
            {item.description ? <p className="rounded-lg bg-stone-50 p-3 text-sm leading-6 text-stone-600 dark:bg-stone-800 dark:text-stone-300">{item.description}</p> : null}
            <div>
                <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-stone-400"><BookOpen className="size-3.5" />{t("prompts.promptText") || "提示词正文"}</div>
                <pre className="thin-scrollbar max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-5 dark:border-stone-700 dark:bg-stone-900">{item.prompt}</pre>
            </div>
            {item.englishPrompt && item.englishPrompt !== item.prompt ? (
                <div>
                    <div className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-stone-400">English prompt</div>
                    <pre className="thin-scrollbar max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs leading-5 dark:border-stone-700 dark:bg-stone-900">{item.englishPrompt}</pre>
                </div>
            ) : null}
            {item.referenceImageUrls.length ? (
                <div>
                    <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-stone-400"><Images className="size-3.5" />{t("prompts.referenceImages") || "参考图"} · {item.referenceImageUrls.length}</div>
                    <div className="thin-scrollbar flex gap-2 overflow-x-auto pb-1">
                        {item.referenceImageUrls.slice(0, 12).map((url, index) => (
                            <img key={`${url}-${index}`} src={url} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" loading="lazy" onError={(event) => { event.currentTarget.style.display = "none"; }} />
                        ))}
                    </div>
                </div>
            ) : null}
            {item.tags.length ? <div className="flex flex-wrap gap-1.5">{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div> : null}
            <div className="flex gap-2 pt-2">
                {mode !== "copy" ? <Button type="primary" icon={<Check className="size-4" />} onClick={onUse}>{t("prompts.use")}</Button> : null}
                {mode !== "select" ? <Button icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />} onClick={copy}>{copied ? t("common.copied") : t("common.copy")}</Button> : null}
            </div>
        </div>
    );
}
