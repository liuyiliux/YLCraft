import { useEffect, useRef, useState } from "react";
import { Button, Input, Modal, Spin, Tooltip } from "antd";
import { Sparkles, WandSparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AiConfig } from "@/stores/use-config-store";
import { requestImageQuestion } from "@/services/api/image";
import type { AiTextMessage } from "@/services/api/image";

export type AiShot = { title: string; content: string };

type Props = {
    sourceText: string;
    config: AiConfig;
    open: boolean;
    onClose: () => void;
    onConfirm: (shots: AiShot[]) => void;
};

/** 把模型回答解析成分镜数组：容忍 ```json 包裹、前后解释文字、中英文字段名。 */
export function parseAiShots(raw: string): AiShot[] {
    let text = (raw || "").trim();
    const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence) text = fence[1].trim();
    const start = text.search(/[\[{]/);
    if (start < 0) return [];
    let candidate = text.slice(start);
    let parsed: unknown;
    try {
        parsed = JSON.parse(candidate);
    } catch {
        const end = Math.max(candidate.lastIndexOf("]"), candidate.lastIndexOf("}"));
        if (end <= 0) return [];
        try {
            parsed = JSON.parse(candidate.slice(0, end + 1));
        } catch {
            return [];
        }
    }
    let rows: unknown =
        typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
            ? ((parsed as Record<string, unknown>).shots ?? (parsed as Record<string, unknown>).scenes ?? (parsed as Record<string, unknown>).items ?? parsed)
            : parsed;
    if (!Array.isArray(rows)) return [];
    return rows
        .map((row, index): AiShot | null => {
            if (typeof row === "string") return { title: `镜 ${index + 1}`, content: row.trim() };
            if (typeof row !== "object" || row === null) return null;
            const obj = row as Record<string, unknown>;
            const title = String(obj.title ?? obj.name ?? obj.shot ?? `镜 ${index + 1}`).trim();
            const content = String(obj.content ?? obj.text ?? obj.prompt ?? obj.description ?? "").trim();
            return content ? { title: title || `镜 ${index + 1}`, content } : null;
        })
        .filter((shot): shot is AiShot => Boolean(shot));
}

export function CanvasNodeAiSplitDialog({ sourceText, config, open, onClose, onConfirm }: Props) {
    const { t } = useTranslation();
    const [instruction, setInstruction] = useState("");
    const [count, setCount] = useState(6);
    const [status, setStatus] = useState<"idle" | "loading" | "preview" | "error">("idle");
    const [shots, setShots] = useState<AiShot[]>([]);
    const [error, setError] = useState("");
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        if (!open) return;
        setInstruction("");
        setCount(6);
        setStatus("idle");
        setShots([]);
        setError("");
    }, [open, sourceText]);

    useEffect(() => () => abortRef.current?.abort(), []);

    const run = async () => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        setStatus("loading");
        setError("");
        setShots([]);
        const sys = [
            "你是影视分镜助手。把用户给的剧本拆成一组可直接拿去生成视频的分镜。",
            `拆成 ${count} 个分镜，每个分镜是一句独立的画面描述（主体+动作+景别+光线/氛围）。`,
            "只输出 JSON 数组，不要 Markdown、不要解释。元素格式：{\"title\":\"镜 1 · 短标题\",\"content\":\"画面描述\"}。",
            "title 里带镜号（镜 1 / 镜 2…），content 是给视频模型的中文提示词，保留原文的角色名和场景。",
        ].join("\n");
        const user = `${sys}\n\n${instruction ? `补充要求：${instruction}\n\n` : ""}剧本：\n${sourceText}`;
        const messages: AiTextMessage[] = [{ role: "user", content: user }];
        try {
            const raw = await requestImageQuestion(config, messages, () => {}, { signal: controller.signal });
            if (controller.signal.aborted) return;
            const parsed = parseAiShots(raw);
            if (!parsed.length) {
                setStatus("error");
                setError(t("canvas.aiSplit.parseFailed"));
                return;
            }
            setShots(parsed);
            setStatus("preview");
        } catch (err) {
            if (controller.signal.aborted) return;
            setStatus("error");
            setError(err instanceof Error ? err.message : t("canvas.aiSplit.failed"));
        }
    };

    const updateShot = (index: number, patch: Partial<AiShot>) => {
        setShots((current) => current.map((shot, i) => (i === index ? { ...shot, ...patch } : shot)));
    };

    return (
        <Modal
            title={null}
            open={open}
            onCancel={onClose}
            footer={null}
            width={720}
            centered
            destroyOnHidden
            transitionName=""
            maskTransitionName=""
        >
            <div className="space-y-4" data-canvas-no-zoom>
                <div>
                    <h2 className="text-xl font-semibold">{t("canvas.aiSplit.title")}</h2>
                    <p className="mt-1 text-sm opacity-60">{t("canvas.aiSplit.description")}</p>
                </div>

                <div className="max-h-28 overflow-auto rounded-lg border p-3 text-xs leading-6 opacity-70">{sourceText}</div>

                <label className="block space-y-1.5">
                    <span className="text-sm font-medium opacity-75">{t("canvas.aiSplit.instruction")}</span>
                    <Input.TextArea
                        rows={2}
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder={t("canvas.aiSplit.instructionPlaceholder")}
                        disabled={status === "loading"}
                    />
                </label>

                <div className="flex items-center gap-3">
                    <span className="shrink-0 whitespace-nowrap text-sm font-medium opacity-75">{t("canvas.aiSplit.count")}</span>
                    <Input type="number" min={1} max={24} value={count} onChange={(e) => setCount(Math.max(1, Math.min(24, Number(e.target.value) || 1)))} disabled={status === "loading"} className="w-24" />
                    <span className="text-xs opacity-50">{t("canvas.aiSplit.countHint")}</span>
                </div>

                {status === "loading" ? (
                    <div className="flex items-center gap-2 rounded-lg border p-4 text-sm opacity-70">
                        <Spin size="small" /> {t("canvas.aiSplit.loading")}
                    </div>
                ) : null}
                {status === "error" ? <div className="rounded-lg border border-red-400/50 bg-red-500/5 p-3 text-sm text-red-500">{error}</div> : null}

                {status === "preview" ? (
                    <div className="space-y-2">
                        <div className="text-sm font-medium opacity-75">{t("canvas.aiSplit.review", { count: shots.length })}</div>
                        <div className="max-h-64 space-y-2 overflow-auto pr-1">
                            {shots.map((shot, index) => (
                                <div key={index} className="space-y-1 rounded-lg border p-2.5">
                                    <Input size="small" value={shot.title} onChange={(e) => updateShot(index, { title: e.target.value })} aria-label={t("canvas.aiSplit.shotTitle")} />
                                    <Input.TextArea size="small" rows={2} value={shot.content} onChange={(e) => updateShot(index, { content: e.target.value })} aria-label={t("canvas.aiSplit.shotContent")} />
                                </div>
                            ))}
                        </div>
                        <p className="text-xs opacity-50">{t("canvas.aiSplit.confirmHint")}</p>
                    </div>
                ) : null}

                <div className="flex items-center justify-end gap-2 pt-1">
                    <Button onClick={onClose}>{t("common.cancel")}</Button>
                    {status === "preview" ? (
                        <>
                            <Tooltip title={t("canvas.aiSplit.retryHint")}>
                                <Button icon={<Sparkles className="size-4" />} onClick={() => void run()}>{t("canvas.aiSplit.retry")}</Button>
                            </Tooltip>
                            <Button type="primary" icon={<WandSparkles className="size-4" />} onClick={() => onConfirm(shots)}>
                                {t("canvas.aiSplit.create", { count: shots.length })}
                            </Button>
                        </>
                    ) : (
                        <Button type="primary" icon={<Sparkles className="size-4" />} loading={status === "loading"} disabled={!sourceText.trim()} onClick={() => void run()}>
                            {t("canvas.aiSplit.run")}
                        </Button>
                    )}
                </div>
            </div>
        </Modal>
    );
}
