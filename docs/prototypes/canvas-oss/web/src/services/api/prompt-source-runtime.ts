import i18n from "@/i18n";
import type { PromptSource } from "./prompt-source-presets";

export type RawPrompt = {
    id: string;
    title: string;
    prompt: string;
    description: string;
    coverUrl: string;
    referenceImageUrls: string[];
    tags: string[];
    preview: string;
    createdAt: string;
    updatedAt: string;
    author?: string;
    sourceUrl?: string;
    imageMode?: string;
    imageModel?: string;
    imageSize?: string;
    imageCount?: number;
    /* Union dataset extras (reference project + YLCraft IMI). Kept in full so
       the shared library UI can show model group, stats, bilingual prompts and
       reference images without a second fetch. */
    sourceId?: string;
    sourceName?: string;
    dataset?: string;
    chinesePrompt?: string;
    englishPrompt?: string;
    model?: string;
    modelGroup?: string;
    viewCount?: number | null;
    likeCount?: number | null;
    copyCount?: number | null;
    referenceImages?: string[];
    raw?: Record<string, unknown>;
};

type RunOptions = { signal?: AbortSignal };

async function fetchUrl(url: string, options?: RunOptions) {
    const response = await fetch(url, { cache: "no-store", signal: options?.signal });
    if (!response.ok) throw new Error(i18n.t("config.promptSources.runtime.requestFailed", { status: response.status }));
    return response.json();
}

/** Resolve which URL to fetch. In online mode the upstream JSON is preferred
 *  and the local generated seed is the fallback — so a flaky network never
 *  empties the library. Returns both the data and the URL actually used (the
 *  latter resolves relative cover/reference image paths). */
async function fetchSourceWithFallback(source: PromptSource, options?: RunOptions): Promise<{ data: unknown; resolvedUrl: string }> {
    const useOnline = source.mode === "online" && Boolean(source.onlineUrl.trim());
    if (useOnline) {
        try {
            return { data: await fetchUrl(source.onlineUrl, options), resolvedUrl: source.onlineUrl };
        } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") throw error;
            // fall through to local seed
        }
    }
    if (!source.url.trim()) throw new Error(i18n.t("config.promptSources.runtime.urlRequired"));
    return { data: await fetchUrl(source.url, options), resolvedUrl: source.url };
}

export async function runPromptSource(source: PromptSource, options?: RunOptions): Promise<RawPrompt[]> {
    const { data, resolvedUrl } = await fetchSourceWithFallback(source, options);
    const activeSource = { ...source, url: resolvedUrl };

    const items = parseJsonSource(data, activeSource);
    if (source.builtIn && !items.length) throw new Error(i18n.t("config.promptSources.runtime.noPrompts", { name: source.name }));
    return items;
}

function parseJsonSource(data: unknown, source: PromptSource) {
    if (!Array.isArray(data)) throw new Error(i18n.t("config.promptSources.runtime.invalidRoot", { name: source.name }));
    return normalizeItems(data, source);
}

function normalizeItems(values: unknown[], source: PromptSource) {
    const seen = new Set<string>();
    const items: RawPrompt[] = [];
    values.forEach((value, index) => {
        const record = asRecord(value);
        const title = stringValue(record.title).trim();
        const prompt = stringValue(record.prompt).trim();
        if (!title || !prompt) return;
        const id = stringValue(record.id).trim() || `${source.id}-${leftPad(index + 1)}`;
        if (seen.has(id)) return;
        seen.add(id);
        const refValues = Array.isArray(record.referenceImageUrls) && record.referenceImageUrls.length ? record.referenceImageUrls : record.referenceImages;
        const referenceImageUrls = stringArray(refValues).map((url) => absoluteUrl(source.url, url));
        const coverUrl = absoluteUrl(source.url, stringValue(record.coverUrl)) || referenceImageUrls[0] || "";
        items.push({
            id,
            title,
            prompt,
            description: stringValue(record.description),
            coverUrl,
            referenceImageUrls,
            tags: stringArray(record.tags),
            preview: stringValue(record.preview) || prompt.slice(0, 360),
            createdAt: stringValue(record.createdAt),
            updatedAt: stringValue(record.updatedAt),
            author: stringValue(record.author),
            sourceUrl: absoluteUrl(source.url, stringValue(record.sourceUrl)),
            imageMode: optionalString(record.imageMode),
            imageModel: optionalString(record.imageModel),
            imageSize: optionalString(record.imageSize),
            imageCount: optionalNumber(record.imageCount),
            sourceId: stringValue(record.sourceId) || source.id,
            sourceName: stringValue(record.sourceName) || source.name,
            dataset: stringValue(record.dataset) || "reference-project",
            chinesePrompt: optionalString(record.chinesePrompt),
            englishPrompt: optionalString(record.englishPrompt),
            model: optionalString(record.model),
            modelGroup: optionalString(record.modelGroup),
            viewCount: numberOrNull(record.viewCount),
            likeCount: numberOrNull(record.likeCount),
            copyCount: numberOrNull(record.copyCount),
            referenceImages: stringArray(refValues),
            raw: asRecord(record.raw),
        });
    });
    return items;
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown) {
    return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function stringArray(value: unknown) {
    return Array.isArray(value) ? value.map(stringValue).map((item) => item.trim()).filter(Boolean) : [];
}

function optionalString(value: unknown) {
    const result = stringValue(value).trim();
    return result || undefined;
}

function optionalNumber(value: unknown) {
    const result = Number(value);
    return Number.isFinite(result) && result > 0 ? result : undefined;
}

function numberOrNull(value: unknown) {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
}

function absoluteUrl(baseUrl: string, path: string) {
    if (!path) return "";
    try {
        return new URL(path, baseUrl).toString();
    } catch {
        return path;
    }
}

function leftPad(value: number) {
    return String(value).padStart(4, "0");
}
