"""3D 绑骨链路的真实调用验收（`3d-rigging-digital-human` #16）。

**这个脚本会真的调用腾讯云并产生费用**，所以默认不自动跑，需要显式给出素材 id。

用法：
    python tools/verify_rigging_live.py --preflight-only                  # 只查本地前置条件，不提交、不花钱
    python tools/verify_rigging_live.py --asset-id <素材库里的 3D 模型 id>
    python tools/verify_rigging_live.py --asset-id <id> --motion-type 26   # 附带预设动作
    python tools/verify_rigging_live.py --asset-id <id> --polls 30          # 轮询次数

前置条件（缺一不可，脚本会先自查）：
1. 后端在跑（默认 http://127.0.0.1:8000）；
2. 存在 `capability=rigging` 的 3D 连接器；
3. COS 已配置——源模型要靠 COS 的 24h 签名 URL 交给腾讯，
   否则会退回本机 BASE_URL，腾讯云根本下载不到；
4. 账号有**可用的绑骨积分**（预付费资源包或已开通后付费），否则提交即返回
   `ResourceInsufficient`。⚠️ 这一条**无法离线自查**：腾讯 ai3d 的 19 个接口全是
   "提交/查询任务"类，**没有**查询开通状态或资源余量的接口，只能真提交一次才知道。
   参考价（官方计费文档）：绑骨蒙皮 **10 积分/次**；后付费 0.12 元/积分 ≈ **1.2 元/次**；
   预付费 1000 积分 = 100 元。**任务失败不计费**——所以"未开通时跑一次"不花钱，
   只有"已开通时跑一次"才会正常计费，而那时正是我们想要的结果；
5. 源模型是**人形 A/T-Pose**、无骨骼、≤60MB
   （用 `tools/inspect_model3d.py` 体检，用 `core/blender.py` 剥骨/减面）。
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

#: 腾讯返回的几种常见失败，翻译成人话（否则用户面对一串英文代码无从下手）
_ERROR_HINTS = {
    "ResourceInsufficient": (
        "账号没有可用的绑骨积分（资源包积分已用尽或未购买，且后付费未开通——后付费默认不开通）。"
        "三条解封路径：① 领取免费额度 https://console.cloud.tencent.com/ai3d/packages ；"
        "② 购买资源包 https://buy.cloud.tencent.com/ai3d ；"
        "③ 控制台设置里开通后付费 https://console.cloud.tencent.com/ai3d/settings 。"
        "绑骨蒙皮 10 积分/次（后付费 0.12 元/积分 ≈ 1.2 元/次）；任务失败不计费，故本次未产生费用。"
    ),
    "FailedOperation.JobNotExist": "任务不存在——通常是上一步提交就没成功，先看提交阶段（submit）的返回",
    "AuthFailure": "密钥无效或过期，检查连接器的 API Key",
    "LimitExceeded": "超出调用频率或并发限制，稍后重试",
    "InvalidParameter": "参数不合规：确认模型是人形 A/T-Pose、无外部组件、文件 ≤60MB",
}


def _get(path: str, timeout: int = 120) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}:", error.read().decode("utf-8", "replace")[:1200])
        raise


def _hints(text: str) -> list[str]:
    return [message for code, message in _ERROR_HINTS.items() if code in (text or "")]


def _preflight() -> bool:
    print("== 前置检查 ==")
    ok = True
    try:
        backends = _get("/api/v1/model-3d/backends?capability=rigging")
        names = [item.get("name") for item in backends.get("backends") or []]
        print(f"  绑骨连接器: {names or '（无）'}")
        if not names:
            ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"  读取连接器失败: {exc}（后端在跑吗？）")
        return False
    try:
        settings = _get("/api/v1/settings")
        data = (settings.get("data") or {}).get("data") or {}
        cos = data.get("cos") or {}
        configured = bool(cos.get("bucket")) and bool(cos.get("secret_id")) and bool(cos.get("secret_key"))
        print(f"  COS 配置: {'已配置（走签名 URL）' if configured else '未配置（会退回本机地址，腾讯下载不到）'}")
        if not configured:
            ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"  读取设置失败: {exc}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="3D 绑骨真实调用验收")
    parser.add_argument("--asset-id", default="", help="素材库里的 3D 模型 id")
    parser.add_argument("--provider", default="", help="绑骨连接器名，默认取第一个可用的")
    parser.add_argument("--motion-type", type=int, default=None, help="预设动作编号 1-48，不传=仅绑骨")
    parser.add_argument("--polls", type=int, default=18, help="轮询次数，每次间隔 10 秒")
    parser.add_argument("--preflight-only", action="store_true",
                        help="只跑前置检查，不提交任务（不产生任何费用）")
    args = parser.parse_args()

    if not _preflight():
        print("\n前置条件不满足，先补齐再跑（否则只是浪费一次调用）。")
        return 1

    if args.preflight_only:
        print("\n只做了前置检查，未提交任务（--preflight-only）。")
        print("提醒：账号积分/后付费状态属于第 4 条前置条件，无法离线查询——")
        print("      腾讯 ai3d 没有查询开通状态或资源余量的接口，需真提交一次才能确认。")
        return 0

    if not args.asset_id:
        parser.error("--asset-id 必填（只有 --preflight-only 模式可以省略）")

    provider = args.provider
    if not provider:
        provider = (_get("/api/v1/model-3d/backends?capability=rigging").get("backends") or [{}])[0].get("name", "")

    payload = {"provider": provider, "source_asset_id": args.asset_id}
    if args.motion_type:
        payload["motion_type"] = args.motion_type

    print(f"\n== 提交绑骨 ==\n  {json.dumps(payload, ensure_ascii=False)}")
    submitted = _post("/api/v1/model-3d/rig", payload)
    diagnostics = submitted.get("diagnostics") or {}
    print(f"  task_id = {submitted.get('task_id') or '(无)'}")
    print(f"  status  = {submitted.get('status')}")
    if submitted.get("error"):
        print(f"  error   = {submitted['error']}")
    if diagnostics:
        print(f"  阶段    = {diagnostics.get('operation')}  endpoint={diagnostics.get('endpoint')}")
        print(f"  响应摘要= {str(diagnostics.get('response_excerpt'))[:400]}")
    for hint in _hints(json.dumps(submitted, ensure_ascii=False)):
        print(f"  → 诊断  : {hint}")

    task_id = submitted.get("task_id")
    if not task_id:
        print("\n提交未成功，没有任务可轮询。")
        return 1

    print(f"\n== 轮询（每 10 秒一次，最多 {args.polls} 次）==")
    for attempt in range(args.polls):
        time.sleep(10)
        task = _get(f"/api/v1/model-3d/tasks/{task_id}")
        status = task.get("status")
        print(f"  [{attempt + 1}] status={status} progress={task.get('progress')} asset={task.get('asset_id')}")
        if status in ("done", "error", "cancelled"):
            print("\n最终结果:", json.dumps(task, ensure_ascii=False)[:1600])
            if status == "done":
                print(f"\n绑骨完成，素材 id = {task.get('asset_id')}")
                print("下一步：用 tools/inspect_model3d.py 核对产物文件里的骨骼数/动画段数，")
                print("        不要只看页面上的徽标。")
            return 0
    print(f"\n仍在等待，可继续查：{BASE}/api/v1/model-3d/tasks/{task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
