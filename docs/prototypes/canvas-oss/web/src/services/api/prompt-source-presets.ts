import { nanoid } from "nanoid";

export type PromptSourceMode = "local" | "online";

export type PromptSource = {
    id: string;
    name: string;
    /** Seed URL (local generated JSON) — always available offline. */
    url: string;
    /** Optional online JSON URL. Used when mode === "online"; falls back to url on failure. */
    onlineUrl: string;
    mode: PromptSourceMode;
    homepage: string;
    enabled: boolean;
    builtIn: boolean;
};

export const PROMPT_REGISTRY_HOMEPAGE = "https://github.com/yukkcat/image-prompts";
/** Local union dataset built by scripts/build_prompt_dataset.py. */
export const PROMPT_DATA_BASE = "/prompt-data";
/** Upstream reference registry — raw static JSON, used as the online source for the 7 OSS sources. */
export const PROMPT_ONLINE_BASE = "https://raw.githubusercontent.com/yukkcat/image-prompts/main/dist/sources";

export function createPromptSource(source?: Partial<PromptSource>): PromptSource {
    return {
        id: source?.id?.trim() || nanoid(),
        name: source?.name?.trim() || "",
        url: source?.url?.trim() || "",
        onlineUrl: source?.onlineUrl?.trim() || "",
        mode: source?.mode === "online" ? "online" : "local",
        homepage: source?.homepage?.trim() || "",
        enabled: source?.enabled ?? true,
        builtIn: source?.builtIn ?? false,
    };
}

/** Online JSON URL for a source id, or "" when no public online source exists
 *  (the 3 IMI sources only ship as a local seed). */
function onlineUrlFor(id: string): string {
    const ossIds = new Set(["banana-prompt-quicker", "davidwu-gpt-image2-prompts", "freestylefly-gpt-image-2", "awesome-gpt-image", "awesome-gpt4o-image-prompts", "youmind-gpt-image-2", "youmind-nano-banana-pro"]);
    return ossIds.has(id) ? `${PROMPT_ONLINE_BASE}/${id}.json` : "";
}

/** 10 sources: 7 from the reference project (with online URL) + 3 YLCraft IMI
 *  libraries (local seed only). Default mode is local so the prototype boots
 *  offline; switch a source to online in the source settings to re-sync from upstream. */
export const DEFAULT_PROMPT_SOURCES: PromptSource[] = [
    source("banana-prompt-quicker", "Banana Prompt Quicker", "https://glidea.github.io/banana-prompt-quicker/"),
    source("davidwu-gpt-image2-prompts", "DavidWu GPT Image 2", "https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts"),
    source("freestylefly-gpt-image-2", "Freestylefly GPT Image 2", "https://github.com/freestylefly/awesome-gpt-image-2"),
    source("awesome-gpt-image", "Awesome GPT Image", "https://github.com/ZeroLu/awesome-gpt-image"),
    source("awesome-gpt4o-image-prompts", "Awesome GPT-4o", "https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts"),
    source("youmind-gpt-image-2", "YouMind GPT Image 2", "https://github.com/YouMind-OpenLab/awesome-gpt-image-2"),
    source("youmind-nano-banana-pro", "YouMind Nano Banana Pro", "https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts"),
    source("imi-chatgpt-prompts", "IMI ChatGPT Prompt Gallery", "https://prompt.imi.ccwu.cc/ChatGPT"),
    source("imi-nano-banana-2-prompts", "IMI Nano Banana 2", "https://prompt.imi.ccwu.cc/Nano%20Banana%202"),
    source("imi-nano-banana-pro-prompts", "IMI Nano Banana Pro", "https://prompt.imi.ccwu.cc/Nano%20Banana%20Pro"),
];

function source(id: string, name: string, homepage: string): PromptSource {
    return { id, name, url: `${PROMPT_DATA_BASE}/${id}.json`, onlineUrl: onlineUrlFor(id), mode: "local", homepage, enabled: true, builtIn: true };
}
