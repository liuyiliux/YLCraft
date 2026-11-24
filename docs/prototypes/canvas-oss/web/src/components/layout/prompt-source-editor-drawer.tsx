import { App, Button, Drawer, Input, Segmented, Space, Switch } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { PromptSource, PromptSourceMode } from "@/services/api/prompt-source-presets";

export function PromptSourceEditorDrawer({ open, source, onSave, onClose }: { open: boolean; source: PromptSource | null; onSave: (source: PromptSource) => void; onClose: () => void }) {
    const { message } = App.useApp();
    const { t } = useTranslation();
    const [draft, setDraft] = useState<PromptSource | null>(source);

    useEffect(() => {
        if (open && source) setDraft(source);
    }, [open, source]);

    if (!draft) return null;

    const patch = (value: Partial<PromptSource>) => setDraft((current) => (current ? { ...current, ...value } : current));

    const save = () => {
        const name = draft.name.trim();
        const url = draft.url.trim();
        const onlineUrl = draft.onlineUrl.trim();
        if (!name) return message.warning(t("config.promptSources.editor.nameRequired"));
        if (!isUsableUrl(url)) return message.warning(t("config.promptSources.editor.invalidUrl"));
        if (onlineUrl && !isHttpUrl(onlineUrl)) return message.warning(t("config.promptSources.editor.invalidOnlineUrl"));
        if (draft.homepage.trim() && !isHttpUrl(draft.homepage.trim())) return message.warning(t("config.promptSources.editor.invalidHomepage"));
        onSave({ ...draft, name, url, onlineUrl, homepage: draft.homepage.trim(), builtIn: false });
        onClose();
    };

    return (
        <Drawer
            open={open}
            width={560}
            title={t(source?.name ? "config.promptSources.editor.editTitle" : "config.promptSources.editor.addTitle")}
            onClose={onClose}
            styles={{ body: { paddingTop: 16 } }}
            extra={
                <Space>
                    <Button onClick={onClose}>{t("common.cancel")}</Button>
                    <Button type="primary" onClick={save}>
                        {t("common.save")}
                    </Button>
                </Space>
            }
        >
            <div className="space-y-5">
                <label className="block">
                    <span className="mb-1.5 block text-sm font-medium">{t("config.promptSources.editor.name")}</span>
                    <Input value={draft.name} onChange={(event) => patch({ name: event.target.value })} placeholder={t("config.promptSources.editor.namePlaceholder")} />
                </label>
                <div>
                    <span className="mb-1.5 block text-sm font-medium">{t("config.promptSources.editor.mode") || "同步模式"}</span>
                    <Segmented
                        block
                        value={draft.mode || "local"}
                        onChange={(value) => patch({ mode: value as PromptSourceMode })}
                        options={[
                            { label: t("config.promptSources.editor.modeLocal") || "本地种子", value: "local" },
                            { label: t("config.promptSources.editor.modeOnline") || "在线同步", value: "online" },
                        ]}
                    />
                    <p className="mt-1.5 text-xs text-stone-500 dark:text-stone-400">{t("config.promptSources.editor.modeHint") || "在线同步优先拉取在线地址，失败自动回落到本地种子。"}</p>
                </div>
                <label className="block">
                    <span className="mb-1.5 block text-sm font-medium">{t("config.promptSources.editor.seedUrl") || "种子 JSON 地址（本地）"}</span>
                    <Input value={draft.url} onChange={(event) => patch({ url: event.target.value })} placeholder="/prompt-data/example.json" />
                </label>
                <label className="block">
                    <span className="mb-1.5 block text-sm font-medium">{t("config.promptSources.editor.onlineUrl") || "在线 JSON 地址"}</span>
                    <Input value={draft.onlineUrl || ""} onChange={(event) => patch({ onlineUrl: event.target.value })} placeholder="https://example.com/prompts.json" />
                </label>
                <label className="block">
                    <span className="mb-1.5 block text-sm font-medium">{t("config.promptSources.editor.homepage")}</span>
                    <Input value={draft.homepage} onChange={(event) => patch({ homepage: event.target.value })} placeholder="https://example.com" />
                </label>
                <div className="flex items-center justify-between border-y border-stone-200 py-3 dark:border-stone-800">
                    <span className="text-sm font-medium">{t("config.promptSources.editor.enabled")}</span>
                    <Switch checked={draft.enabled} onChange={(enabled) => patch({ enabled })} />
                </div>
                <div>
                    <div className="mb-2 text-sm font-medium">{t("config.promptSources.editor.jsonFormat")}</div>
                    <pre className="overflow-x-auto rounded-md bg-stone-100 p-3 text-xs leading-5 text-stone-600 dark:bg-stone-900 dark:text-stone-300">{`[
  {
    "id": "product-photo-1",
    "title": "Product photo",
    "prompt": "Generate a professional product photo on a white background",
    "description": "",
    "coverUrl": "",
    "referenceImageUrls": [],
    "tags": ["product", "photography"]
  }
]`}</pre>
                </div>
            </div>
        </Drawer>
    );
}

function isHttpUrl(value: string) {
    try {
        return ["http:", "https:"].includes(new URL(value).protocol);
    } catch {
        return false;
    }
}

function isUsableUrl(value: string) {
    return value.startsWith("/") || isHttpUrl(value);
}
