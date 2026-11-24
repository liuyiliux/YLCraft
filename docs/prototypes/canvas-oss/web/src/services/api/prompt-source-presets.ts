import { nanoid } from "nanoid";

export type PromptSource = {
    id: string;
    name: string;
    url: string;
    homepage: string;
    enabled: boolean;
    builtIn: boolean;
};

export const PROMPT_REGISTRY_HOMEPAGE = "https://github.com/yukkcat/image-prompts";
/** Local union dataset built by scripts/build_prompt_dataset.py. Swap this base
 *  for a YLCraft backend endpoint when the prototype is embedded for real. */
export const PROMPT_DATA_BASE = "/prompt-data";

export function createPromptSource(source?: Partial<PromptSource>): PromptSource {
    return {
        id: source?.id?.trim() || nanoid(),
        name: source?.name?.trim() || "",
        url: source?.url?.trim() || "",
        homepage: source?.homepage?.trim() || "",
        enabled: source?.enabled ?? true,
        builtIn: source?.builtIn ?? false,
    };
}

/** 10 sources: 7 from the reference project + 3 YLCraft downloaded IMI libraries.
 *  Full field fidelity, 13,128 prompts. Source IDs stay stable so old caches
 *  are reused until the URL signature changes. */
export const DEFAULT_PROMPT_SOURCES: PromptSource[] = [
    localSource("banana-prompt-quicker", "Banana Prompt Quicker", "https://glidea.github.io/banana-prompt-quicker/"),
    localSource("davidwu-gpt-image2-prompts", "DavidWu GPT Image 2", "https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts"),
    localSource("freestylefly-gpt-image-2", "Freestylefly GPT Image 2", "https://github.com/freestylefly/awesome-gpt-image-2"),
    localSource("awesome-gpt-image", "Awesome GPT Image", "https://github.com/ZeroLu/awesome-gpt-image"),
    localSource("awesome-gpt4o-image-prompts", "Awesome GPT-4o", "https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts"),
    localSource("youmind-gpt-image-2", "YouMind GPT Image 2", "https://github.com/YouMind-OpenLab/awesome-gpt-image-2"),
    localSource("youmind-nano-banana-pro", "YouMind Nano Banana Pro", "https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts"),
    localSource("imi-chatgpt-prompts", "IMI ChatGPT Prompt Gallery", "https://prompt.imi.ccwu.cc/ChatGPT"),
    localSource("imi-nano-banana-2-prompts", "IMI Nano Banana 2", "https://prompt.imi.ccwu.cc/Nano%20Banana%202"),
    localSource("imi-nano-banana-pro-prompts", "IMI Nano Banana Pro", "https://prompt.imi.ccwu.cc/Nano%20Banana%20Pro"),
];

function localSource(id: string, name: string, homepage: string): PromptSource {
    return { id, name, url: `${PROMPT_DATA_BASE}/${id}.json`, homepage, enabled: true, builtIn: true };
}
