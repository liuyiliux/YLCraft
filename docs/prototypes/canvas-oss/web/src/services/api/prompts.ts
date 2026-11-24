import localforage from "localforage";

import { runPromptSource, type RawPrompt } from "./prompt-source-runtime";
import { usePromptSourceStore } from "@/stores/use-prompt-source-store";
import i18n from "@/i18n";
import type { PromptSource } from "./prompt-source-presets";

export type Prompt = RawPrompt & {
    sourceId: string;
    category: string;
    githubUrl: string;
};

export const ALL_PROMPTS_OPTION = "all";

/** Human labels for the dataset buckets produced by build_prompt_dataset.py.
 *  Keeps raw ids like "ylcraft-imi" out of the UI. */
export const DATASET_LABELS: Record<string, string> = {
    "reference-project": "参考项目",
    "ylcraft-imi": "YLCraft 下载库",
    "ylcraft-library": "YLCraft 我的库",
    merged: "合并补全",
};

export function datasetLabel(value: string) {
    return DATASET_LABELS[value] ?? value;
}

export type PromptListResponse = {
    items: Prompt[];
    tags: string[];
    categories: string[];
    total: number;
};

export type PromptSourceStatus = {
    sourceId: string;
    count: number;
    lastSuccessAt: string;
    lastError: string;
};

export type PromptSourceRefreshResult = PromptSourceStatus & {
    sourceName: string;
    success: boolean;
};

export type PromptSourceRefreshSummary = {
    results: PromptSourceRefreshResult[];
    total: number;
    successCount: number;
    failureCount: number;
};

type SourceCache = PromptSourceStatus & {
    items: Prompt[];
    fetchedAt: number;
    signature: string;
};

const cacheTtlMs = 1000 * 60 * 60;
const promptCacheStore = localforage.createInstance({ name: "infinite-canvas", storeName: "prompt_cache" });
const loadingSources = new Map<string, Promise<PromptSourceRefreshResult>>();

function enabledSources() {
    return usePromptSourceStore.getState().sources.filter((source) => source.enabled);
}

function cacheKey(sourceId: string) {
    return `prompt-source:${sourceId}`;
}

function sourceSignature(source: PromptSource) {
    const value = `${source.name}\n${source.url}\n${source.homepage}`;
    let hash = 0;
    for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) | 0;
    return `${value.length}:${hash}`;
}

function withSourceMeta(source: PromptSource, items: RawPrompt[]): Prompt[] {
    return items.map((item) => ({
        ...item,
        description: item.description || "",
        referenceImageUrls: Array.isArray(item.referenceImageUrls) ? item.referenceImageUrls : [],
        sourceId: source.id,
        category: source.name,
        githubUrl: item.sourceUrl || source.homepage,
    }));
}

async function readSourceCache(sourceId: string) {
    return promptCacheStore.getItem<SourceCache>(cacheKey(sourceId));
}

async function refreshSourceRecord(source: PromptSource): Promise<PromptSourceRefreshResult> {
    const previous = await readSourceCache(source.id);
    try {
        const items = withSourceMeta(source, await runPromptSource(source));
        const lastSuccessAt = new Date().toISOString();
        const cache: SourceCache = { sourceId: source.id, items, count: items.length, fetchedAt: Date.now(), lastSuccessAt, lastError: "", signature: sourceSignature(source) };
        await promptCacheStore.setItem(cacheKey(source.id), cache);
        return { sourceId: source.id, sourceName: source.name, count: items.length, lastSuccessAt, lastError: "", success: true };
    } catch (error) {
        const lastError = error instanceof Error ? error.message : String(error);
        const cache: SourceCache = {
            sourceId: source.id,
            items: previous?.items || [],
            count: previous?.items?.length || 0,
            fetchedAt: previous?.fetchedAt || 0,
            lastSuccessAt: previous?.lastSuccessAt || "",
            lastError,
            signature: previous?.signature || sourceSignature(source),
        };
        await promptCacheStore.setItem(cacheKey(source.id), cache);
        return { sourceId: source.id, sourceName: source.name, count: cache.count, lastSuccessAt: cache.lastSuccessAt, lastError, success: false };
    }
}

function getOrStartRefresh(source: PromptSource) {
    const current = loadingSources.get(source.id);
    if (current) return current;
    const loading = refreshSourceRecord(source).finally(() => loadingSources.delete(source.id));
    loadingSources.set(source.id, loading);
    return loading;
}

async function getSourcePrompts(source: PromptSource): Promise<Prompt[]> {
    const cached = await readSourceCache(source.id);
    if (cached) {
        const stale = cached.signature !== sourceSignature(source) || Date.now() - cached.fetchedAt >= cacheTtlMs;
        if (stale) void getOrStartRefresh(source).catch(() => undefined);
        return withSourceMeta(source, cached.items);
    }
    const result = await getOrStartRefresh(source);
    if (!result.success) throw new Error(result.lastError);
    return (await readSourceCache(source.id))?.items || [];
}

async function getAllPrompts(): Promise<Prompt[]> {
    const settled = await Promise.all(
        enabledSources().map(async (source) => {
            try {
                return await getSourcePrompts(source);
            } catch {
                return [];
            }
        }),
    );
    return settled.flat();
}

export const ALL_MODEL_GROUPS_OPTION = "all";

/** Real YLCraft tag ranking, exported by scripts/build_prompt_dataset.py from
 *  backend service.py (single source of truth — never hard-code it here). */
type TagPriorityData = { tags: string[]; stopwords: string[] };
let tagPriorityCache: Promise<TagPriorityData> | null = null;
function loadTagPriority(): Promise<TagPriorityData> {
    if (!tagPriorityCache) {
        tagPriorityCache = fetch("/prompt-data/tag-priority.json")
            .then((response) => (response.ok ? response.json() : Promise.reject(new Error("tag-priority"))))
            .catch(() => ({ tags: [], stopwords: [] }) as TagPriorityData);
    }
    return tagPriorityCache;
}

export async function fetchPrompts({ keyword = "", tag = [], category = ALL_PROMPTS_OPTION, modelGroup = ALL_MODEL_GROUPS_OPTION, dataset = ALL_PROMPTS_OPTION, page = 1, pageSize = 20 }: { keyword?: string; tag?: string[]; category?: string; modelGroup?: string; dataset?: string; page?: number; pageSize?: number } = {}) {
    const items = await getAllPrompts();
    const normalizedKeyword = keyword.trim().toLowerCase();
    const normalizedPage = Math.max(1, page);
    const normalizedPageSize = Math.max(1, Math.min(100, pageSize));
    const withoutTagFilter = filterPrompts(items, { keyword: normalizedKeyword, category, tags: [], modelGroup, dataset });
    const filtered = filterPrompts(items, { keyword: normalizedKeyword, category, tags: tag, modelGroup, dataset });
    const categories = enabledSources().map((source) => source.name);

    return {
        items: filtered.slice((normalizedPage - 1) * normalizedPageSize, normalizedPage * normalizedPageSize),
        tags: await collectTags(withoutTagFilter),
        categories,
        modelGroups: Array.from(new Set(items.map((item) => item.modelGroup).filter((value): value is string => Boolean(value)))).sort(),
        datasets: Array.from(new Set(items.map((item) => item.dataset).filter((value): value is string => Boolean(value)))).sort(),
        total: filtered.length,
    };
}

export async function fetchSourcePrompts(sourceId: string): Promise<Prompt[]> {
    const source = usePromptSourceStore.getState().sources.find((item) => item.id === sourceId);
    if (!source) throw new Error(i18n.t("prompts.sourceMissing"));
    return getSourcePrompts(source);
}

export async function refreshSource(sourceId: string): Promise<PromptSourceRefreshResult> {
    const source = usePromptSourceStore.getState().sources.find((item) => item.id === sourceId);
    if (!source) throw new Error(i18n.t("prompts.sourceMissing"));
    const result = await getOrStartRefresh(source);
    if (!result.success) throw new Error(result.lastError);
    return result;
}

export async function refreshAllSources(): Promise<PromptSourceRefreshSummary> {
    const results = await Promise.all(enabledSources().map(getOrStartRefresh));
    return summarizeRefresh(results);
}

export async function refreshDueSources(maxAgeMs: number): Promise<PromptSourceRefreshSummary> {
    const sources = await Promise.all(
        enabledSources().map(async (source) => {
            const cached = await readSourceCache(source.id);
            const lastSuccess = cached?.lastSuccessAt ? new Date(cached.lastSuccessAt).getTime() : 0;
            return !lastSuccess || Boolean(cached?.lastError) || Date.now() - lastSuccess >= maxAgeMs || cached?.signature !== sourceSignature(source) ? source : null;
        }),
    );
    const results = await Promise.all(sources.filter((source): source is PromptSource => Boolean(source)).map(getOrStartRefresh));
    return summarizeRefresh(results);
}

export async function fetchPromptSourceStatuses(): Promise<Record<string, PromptSourceStatus>> {
    const entries = await Promise.all(
        usePromptSourceStore.getState().sources.map(async (source) => {
            const cache = await readSourceCache(source.id);
            return [source.id, { sourceId: source.id, count: cache?.items?.length || 0, lastSuccessAt: cache?.lastSuccessAt || "", lastError: cache?.lastError || "" }] as const;
        }),
    );
    return Object.fromEntries(entries);
}

function summarizeRefresh(results: PromptSourceRefreshResult[]): PromptSourceRefreshSummary {
    return {
        results,
        total: results.reduce((total, item) => total + item.count, 0),
        successCount: results.filter((item) => item.success).length,
        failureCount: results.filter((item) => !item.success).length,
    };
}

function filterPrompts(items: Prompt[], options: { keyword: string; category: string; tags: string[]; modelGroup?: string; dataset?: string }) {
    return items.filter((item) => {
        if (isActiveOption(options.category) && item.category !== options.category) return false;
        if (options.modelGroup && isActiveOption(options.modelGroup) && item.modelGroup !== options.modelGroup) return false;
        if (options.dataset && isActiveOption(options.dataset) && item.dataset !== options.dataset) return false;
        if (options.tags.length && !options.tags.some((tag) => item.tags.includes(tag))) return false;
        if (!options.keyword) return true;
        return [item.title, item.prompt, item.description, item.category, item.modelGroup, ...item.tags].filter(Boolean).join(" ").toLowerCase().includes(options.keyword);
    });
}

async function collectTags(items: Prompt[]) {
    const { tags: priority, stopwords } = await loadTagPriority();
    const rank = new Map(priority.map((tag, index) => [tag.toLowerCase(), index]));
    const blocked = new Set(stopwords.map((tag) => tag.toLowerCase()));
    const counts = new Map<string, { label: string; count: number }>();
    for (const item of items) {
        for (const raw of item.tags) {
            if (!raw) continue;
            const key = raw.trim().toLowerCase();
            if (!key || key.startsWith("@") || blocked.has(key)) continue;
            const entry = counts.get(key);
            if (entry) entry.count += 1;
            else counts.set(key, { label: raw.trim(), count: 1 });
        }
    }
    return Array.from(counts.values())
        .sort((a, b) => {
            const ai = rank.get(a.label.toLowerCase());
            const bi = rank.get(b.label.toLowerCase());
            if (ai !== undefined || bi !== undefined) {
                if (ai === undefined) return 1;
                if (bi === undefined) return -1;
                if (ai !== bi) return ai - bi;
            }
            return b.count - a.count || a.label.localeCompare(b.label);
        })
        .slice(0, 180)
        .map((entry) => entry.label);
}

function isActiveOption(value: string) {
    return value && value !== ALL_PROMPTS_OPTION && value !== "all";
}

export function formatPromptDate(value: string, locale?: string) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}
