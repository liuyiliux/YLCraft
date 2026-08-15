"""Durable, bounded subagent orchestration for YLCraft Agent runs."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentDelegation, AgentRun, AgentRunStep


class DelegationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DelegationLimits:
    max_depth: int = 2
    max_children_per_call: int = 6
    max_concurrency: int = 3
    max_children_per_root: int = 12
    child_timeout_seconds: float = 300.0


@dataclass(frozen=True)
class DelegatedTask:
    task_key: str
    profile_id: str
    objective: str
    context: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    spawn_mode: str = "spawn"  # spawn | fork

    @classmethod
    def from_value(cls, value: "DelegatedTask | dict[str, Any]", index: int = 0) -> "DelegatedTask":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise DelegationValidationError("子任务必须是对象")
        task_key = str(value.get("task_key") or value.get("task_id") or f"task-{index + 1}").strip()
        profile_id = str(value.get("profile_id") or "").strip()
        objective = str(value.get("objective") or value.get("message") or "").strip()
        context = value.get("context") if isinstance(value.get("context"), dict) else {}
        raw_dependencies = value.get("depends_on") if isinstance(value.get("depends_on"), list) else []
        spawn_mode = str(value.get("spawn_mode") or value.get("spawn") or "spawn").strip() or "spawn"
        if spawn_mode not in {"spawn", "fork"}:
            raise DelegationValidationError("spawn_mode 只支持 spawn 或 fork")
        return cls(
            task_key=task_key,
            profile_id=profile_id,
            objective=objective,
            context=context,
            depends_on=tuple(str(item).strip() for item in raw_dependencies if str(item).strip()),
            spawn_mode=spawn_mode,
        )


@dataclass
class SubagentExecutionResult:
    task_key: str
    profile_id: str
    status: str
    child_run_id: str = ""
    child_thread_id: str = ""
    reply: str = ""
    linked_objects: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw_result: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "completed"


class SubagentRunner(Protocol):
    async def execute(
        self,
        task: DelegatedTask,
        *,
        user_id: str,
        root_run_id: str,
        parent_run_id: str,
        delegation_depth: int,
        context: dict[str, Any],
    ) -> SubagentExecutionResult: ...


class DelegationPolicy:
    def __init__(self, limits: DelegationLimits | None = None):
        self.limits = limits or DelegationLimits()

    def validate(
        self,
        tasks: list[DelegatedTask | dict[str, Any]],
        *,
        parent_depth: int,
        existing_root_children: int = 0,
    ) -> list[DelegatedTask]:
        normalized = [DelegatedTask.from_value(item, index) for index, item in enumerate(tasks)]
        if not normalized:
            raise DelegationValidationError("至少需要一个子任务")
        if parent_depth >= self.limits.max_depth:
            raise DelegationValidationError(f"委派深度已达到上限 {self.limits.max_depth}")
        if len(normalized) > self.limits.max_children_per_call:
            raise DelegationValidationError(
                f"单次最多委派 {self.limits.max_children_per_call} 个子任务"
            )
        if existing_root_children + len(normalized) > self.limits.max_children_per_root:
            raise DelegationValidationError(
                f"根任务最多创建 {self.limits.max_children_per_root} 个子任务"
            )

        keys = [task.task_key for task in normalized]
        if len(set(keys)) != len(keys):
            raise DelegationValidationError("子任务 task_key 必须唯一")
        key_set = set(keys)
        for task in normalized:
            if not task.task_key:
                raise DelegationValidationError("子任务 task_key 不能为空")
            if not task.profile_id:
                raise DelegationValidationError(f"子任务 {task.task_key} 缺少 profile_id")
            if not task.objective:
                raise DelegationValidationError(f"子任务 {task.task_key} 缺少 objective")
            unknown = [item for item in task.depends_on if item not in key_set]
            if unknown:
                raise DelegationValidationError(
                    f"子任务 {task.task_key} 依赖未知任务：{', '.join(unknown)}"
                )
            if task.task_key in task.depends_on:
                raise DelegationValidationError(f"子任务 {task.task_key} 不能依赖自身")

        self.execution_batches(normalized)
        return normalized

    def execution_batches(self, tasks: list[DelegatedTask]) -> list[list[DelegatedTask]]:
        remaining = {task.task_key: task for task in tasks}
        completed: set[str] = set()
        batches: list[list[DelegatedTask]] = []
        while remaining:
            ready = [
                task for task in remaining.values()
                if set(task.depends_on).issubset(completed)
            ]
            if not ready:
                raise DelegationValidationError("子任务依赖存在循环")
            ready.sort(key=lambda item: item.task_key)
            batches.append(ready)
            for task in ready:
                completed.add(task.task_key)
                remaining.pop(task.task_key, None)
        return batches


class DelegationContextBuilder:
    _PARENT_KEYS = {
        "project_id",
        "creative_project_id",
        "chapter_number",
        "episode_number",
        "default_project_id",
        "default_workflow",
        "creative_project_context",
        "project_context",
        "selected_content_id",
        "selected_asset_ids",
    }

    def __init__(self, max_chars: int = 16000):
        self.max_chars = max_chars

    def build(
        self,
        parent_context: dict[str, Any],
        task: DelegatedTask,
        *,
        root_run_id: str,
        parent_run_id: str,
        delegation_depth: int,
    ) -> dict[str, Any]:
        projected = {
            key: value
            for key, value in (parent_context or {}).items()
            if key in self._PARENT_KEYS
        }
        result = {
            **projected,
            **task.context,
            "_delegation": {
                "root_run_id": root_run_id,
                "parent_run_id": parent_run_id,
                "delegation_depth": delegation_depth,
                "task_key": task.task_key,
                "target_profile_id": task.profile_id,
            },
        }
        encoded = json.dumps(result, ensure_ascii=False, default=str)
        if len(encoded) <= self.max_chars:
            return result

        compact = {
            key: value
            for key, value in result.items()
            if key not in {"creative_project_context", "project_context"}
        }
        compact["_delegation"]["context_truncated"] = True
        return compact


class SubagentResultAdapter:
    @staticmethod
    def from_agent_result(task: DelegatedTask, result: dict[str, Any]) -> SubagentExecutionResult:
        done = bool(result.get("done"))
        error = str(result.get("error") or "")
        run_status = str(result.get("status") or "")
        if run_status in {"waiting_confirmation", "cancelled"}:
            status = run_status
        else:
            status = "completed" if done and not error else "failed"
        return SubagentExecutionResult(
            task_key=task.task_key,
            profile_id=task.profile_id,
            status=status,
            child_run_id=str(result.get("run_id") or ""),
            child_thread_id=str(result.get("thread_id") or result.get("session_id") or ""),
            reply=str(result.get("reply") or ""),
            linked_objects=list(result.get("linked_objects") or []),
            error=error or ("子智能体等待用户确认" if status == "waiting_confirmation" else "子智能体未完成" if not done else ""),
            raw_result=result,
        )

    @staticmethod
    def joined_observation(results: list[SubagentExecutionResult], limit: int = 12000) -> str:
        sections = []
        for result in results:
            if result.success:
                body = result.reply.strip() or "已完成，但没有文本回复。"
            elif result.status == "waiting_confirmation":
                body = f"等待用户确认：{result.reply.strip() or result.error}"
            elif result.status == "cancelled":
                body = "任务已取消。"
            elif result.status == "skipped":
                body = f"已跳过：{result.error or '依赖任务未完成'}"
            else:
                body = f"失败：{result.error or '未知错误'}"
            sections.append(f"[{result.profile_id} / {result.task_key}]\n{body}")
        text = "\n\n".join(sections)
        return text if len(text) <= limit else text[: limit - 3] + "..."


class SubagentExecutor:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        timeout_seconds: float = 300.0,
        service_factory: Callable[[AsyncSession, str], Any] | None = None,
    ):
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.service_factory = service_factory

    async def execute(
        self,
        task: DelegatedTask,
        *,
        user_id: str,
        root_run_id: str,
        parent_run_id: str,
        delegation_depth: int,
        context: dict[str, Any],
    ) -> SubagentExecutionResult:
        try:
            async with self.session_factory() as session:
                if self.service_factory is None:
                    from app.services.agent.service import AgentService

                    service = AgentService(session, user_id=user_id)
                else:
                    service = self.service_factory(session, user_id)
                result = await asyncio.wait_for(
                    service.chat(
                        session_id="",
                        user_message=task.objective,
                        context=context,
                        profile_id=task.profile_id,
                        parent_run_id=parent_run_id,
                        force_new_thread=True,
                    ),
                    timeout=self.timeout_seconds,
                )
                await session.commit()
                return SubagentResultAdapter.from_agent_result(task, result)
        except asyncio.TimeoutError:
            return SubagentExecutionResult(
                task_key=task.task_key,
                profile_id=task.profile_id,
                status="failed",
                error=f"子智能体执行超过 {self.timeout_seconds:g} 秒",
            )
        except Exception as exc:  # noqa: BLE001
            return SubagentExecutionResult(
                task_key=task.task_key,
                profile_id=task.profile_id,
                status="failed",
                error=str(exc),
            )

    async def send_message(
        self,
        *,
        thread_id: str,
        user_message: str,
        user_id: str,
        profile_id: str,
        context: dict[str, Any] | None = None,
    ) -> SubagentExecutionResult:
        """Continue an existing child session/thread (continuable primitive)."""
        task = DelegatedTask(task_key="continuation", profile_id=profile_id, objective=user_message)
        try:
            async with self.session_factory() as session:
                if self.service_factory is None:
                    from app.services.agent.service import AgentService

                    service = AgentService(session, user_id=user_id)
                else:
                    service = self.service_factory(session, user_id)
                result = await asyncio.wait_for(
                    service.chat(
                        session_id=thread_id,
                        user_message=user_message,
                        context=context or {},
                        profile_id=profile_id,
                        force_new_thread=False,
                    ),
                    timeout=self.timeout_seconds,
                )
                await session.commit()
                return SubagentResultAdapter.from_agent_result(task, result)
        except asyncio.TimeoutError:
            return SubagentExecutionResult(
                task_key="continuation",
                profile_id=profile_id,
                status="failed",
                error=f"续跑超过 {self.timeout_seconds:g} 秒",
            )
        except Exception as exc:  # noqa: BLE001
            return SubagentExecutionResult(
                task_key="continuation",
                profile_id=profile_id,
                status="failed",
                error=str(exc),
            )


class ForkExecutor(SubagentExecutor):
    """fork primitive: inherit a bounded read-only reference to parent context."""

    async def execute(
        self,
        task: DelegatedTask,
        *,
        user_id: str,
        root_run_id: str,
        parent_run_id: str,
        delegation_depth: int,
        context: dict[str, Any],
    ) -> SubagentExecutionResult:
        fork_context = dict(context or {})
        fork_context["_fork"] = {
            "parent_run_id": parent_run_id,
            "root_run_id": root_run_id,
            "read_only": True,
        }
        return await super().execute(
            task,
            user_id=user_id,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
            delegation_depth=delegation_depth,
            context=fork_context,
        )


class SubagentOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        runner: SubagentRunner,
        *,
        policy: DelegationPolicy | None = None,
        context_builder: DelegationContextBuilder | None = None,
    ):
        self.session = session
        self.runner = runner
        self.policy = policy or DelegationPolicy()
        self.context_builder = context_builder or DelegationContextBuilder()

    async def delegate(
        self,
        parent_run: AgentRun,
        tasks: list[DelegatedTask | dict[str, Any]],
        *,
        join_strategy: str = "all",
    ) -> dict[str, Any]:
        if join_strategy not in {"all", "best_effort"}:
            raise DelegationValidationError("join_strategy 只支持 all 或 best_effort")

        root_run_id = parent_run.root_run_id or parent_run.id
        existing_count = int(
            await self.session.scalar(
                select(func.count()).select_from(AgentDelegation).where(
                    AgentDelegation.root_run_id == root_run_id
                )
            )
            or 0
        )
        normalized = self.policy.validate(
            tasks,
            parent_depth=int(parent_run.delegation_depth or 0),
            existing_root_children=existing_count,
        )
        batches = self.policy.execution_batches(normalized)
        parent_context = self._loads(parent_run.context_json, {})
        parent_step = await self._create_parent_step(parent_run, normalized, join_strategy)
        records: dict[str, AgentDelegation] = {}
        for task in normalized:
            record = AgentDelegation(
                id=uuid.uuid4().hex,
                user_id=parent_run.user_id,
                root_run_id=root_run_id,
                parent_run_id=parent_run.id,
                parent_step_id=parent_step.id,
                task_key=task.task_key,
                target_profile_id=task.profile_id,
                objective=task.objective,
                context_json=json.dumps(task.context, ensure_ascii=False, default=str),
                depends_on_json=json.dumps(list(task.depends_on), ensure_ascii=False),
                execution_mode="parallel" if len(normalized) > 1 else "sequential",
                spawn_mode=task.spawn_mode,
            )
            self.session.add(record)
            records[task.task_key] = record
        await self.session.commit()

        results_by_key: dict[str, SubagentExecutionResult] = {}
        semaphore = asyncio.Semaphore(self.policy.limits.max_concurrency)
        for batch in batches:
            runnable: list[DelegatedTask] = []
            for task in batch:
                failed_dependencies = [
                    key for key in task.depends_on
                    if not results_by_key.get(key) or not results_by_key[key].success
                ]
                if failed_dependencies:
                    result = SubagentExecutionResult(
                        task_key=task.task_key,
                        profile_id=task.profile_id,
                        status="skipped",
                        error=f"依赖任务失败：{', '.join(failed_dependencies)}",
                    )
                    results_by_key[task.task_key] = result
                    await self._finish_record(records[task.task_key].id, result)
                else:
                    runnable.append(task)

            async def run_one(task: DelegatedTask) -> SubagentExecutionResult:
                async with semaphore:
                    context = self.context_builder.build(
                        parent_context,
                        task,
                        root_run_id=root_run_id,
                        parent_run_id=parent_run.id,
                        delegation_depth=int(parent_run.delegation_depth or 0) + 1,
                    )
                    return await self.runner.execute(
                        task,
                        user_id=parent_run.user_id,
                        root_run_id=root_run_id,
                        parent_run_id=parent_run.id,
                        delegation_depth=int(parent_run.delegation_depth or 0) + 1,
                        context=context,
                    )

            if runnable:
                for task in runnable:
                    await self._mark_running(records[task.task_key].id, commit=False)
                await self.session.commit()
                batch_results = await asyncio.gather(*(run_one(task) for task in runnable))
                for result in batch_results:
                    results_by_key[result.task_key] = result
                    await self._finish_record(records[result.task_key].id, result)

        ordered_results = [results_by_key[task.task_key] for task in normalized]
        completed = [item for item in ordered_results if item.success]
        failed = [item for item in ordered_results if item.status == "failed"]
        skipped = [item for item in ordered_results if item.status == "skipped"]
        waiting = [item for item in ordered_results if item.status == "waiting_confirmation"]
        cancelled = [item for item in ordered_results if item.status == "cancelled"]
        if len(completed) == len(ordered_results):
            status = "completed"
        elif waiting:
            status = "waiting_confirmation"
        elif completed:
            status = "partial"
        elif cancelled and len(cancelled) == len(ordered_results):
            status = "cancelled"
        else:
            status = "failed"
        if join_strategy == "all" and failed:
            status = "failed"
        joined = SubagentResultAdapter.joined_observation(ordered_results)
        payload = {
            "status": status,
            "join_strategy": join_strategy,
            "joined_observation": joined,
            "delegations": [self._result_dict(item, records[item.task_key].id) for item in ordered_results],
            "linked_runs": [item.child_run_id for item in ordered_results if item.child_run_id],
            "summary": {
                "total": len(ordered_results),
                "completed": len(completed),
                "failed": len(failed),
                "skipped": len(skipped),
                "waiting_confirmation": len(waiting),
                "cancelled": len(cancelled),
            },
        }
        if len(ordered_results) == 1:
            payload["child_run_id"] = ordered_results[0].child_run_id or None
            payload["target_profile_id"] = ordered_results[0].profile_id
        await self._finish_parent_step(parent_step.id, parent_run.id, status, payload)

        first = ordered_results[0]
        return {
            "success": status in {"completed", "partial"},
            "parent_run_id": parent_run.id,
            "child_run_id": first.child_run_id if len(ordered_results) == 1 else None,
            "target_profile_id": first.profile_id if len(ordered_results) == 1 else None,
            "result": first.raw_result if len(ordered_results) == 1 else payload,
            **payload,
        }

    async def send_message(self, delegation_id: str, message: str, user_id: str = "") -> dict[str, Any]:
        """Continue an existing delegation's child session (continuable primitive)."""
        record = await self.session.get(AgentDelegation, delegation_id)
        if not record:
            raise DelegationValidationError(f"委派记录不存在：{delegation_id}")
        if not record.child_run_id:
            raise DelegationValidationError("该委派尚未产生子运行，无法续跑")
        result_json = self._loads(record.result_json, {})
        thread_id = str(result_json.get("thread_id") or record.child_run_id)
        send = getattr(self.runner, "send_message", None)
        if send is None:
            raise DelegationValidationError("当前 runner 不支持续跑")
        result = await send(
            thread_id=thread_id,
            user_message=message,
            user_id=user_id or record.user_id,
            profile_id=record.target_profile_id,
            context=self._loads(record.context_json, {}),
        )
        continuation = {
            "reply": result.reply,
            "status": result.status,
            "error": result.error,
        }
        record.result_json = json.dumps(
            {**result_json, "continuation": continuation},
            ensure_ascii=False,
            default=str,
        )
        if result.child_run_id and result.child_run_id != record.child_run_id:
            record.continuation_of = record.child_run_id
            record.child_run_id = result.child_run_id
        record.updated_at = datetime.utcnow()
        await self.session.commit()
        return {
            "success": result.success,
            "status": result.status,
            "reply": result.reply,
            "delegation_id": delegation_id,
            "child_run_id": record.child_run_id,
            "continuation_of": record.continuation_of,
        }

    async def _create_parent_step(
        self,
        parent_run: AgentRun,
        tasks: list[DelegatedTask],
        join_strategy: str,
    ) -> AgentRunStep:
        last_index = await self.session.scalar(
            select(func.max(AgentRunStep.order_index)).where(AgentRunStep.run_id == parent_run.id)
        )
        step = AgentRunStep(
            run_id=parent_run.id,
            session_id=parent_run.session_id,
            profile_id=parent_run.profile_id,
            step_type="delegate_subtask",
            status="running",
            order_index=int(last_index) + 1 if last_index is not None else 0,
            summary=f"委派 {len(tasks)} 个子任务",
            input_json=json.dumps(
                {
                    "join_strategy": join_strategy,
                    "tasks": [
                        {
                            "task_key": task.task_key,
                            "profile_id": task.profile_id,
                            "objective": task.objective,
                            "depends_on": list(task.depends_on),
                        }
                        for task in tasks
                    ],
                },
                ensure_ascii=False,
            ),
            output_json="{}",
            linked_objects_json="[]",
        )
        self.session.add(step)
        await self.session.flush()
        return step

    async def _mark_running(self, delegation_id: str, *, commit: bool = True) -> None:
        record = await self.session.get(AgentDelegation, delegation_id)
        if record:
            record.status = "running"
            record.started_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            if commit:
                await self.session.commit()

    async def _finish_record(self, delegation_id: str, result: SubagentExecutionResult) -> None:
        record = await self.session.get(AgentDelegation, delegation_id)
        if not record:
            return
        record.child_run_id = result.child_run_id or None
        record.status = result.status
        record.result_json = json.dumps(
            {
                "reply": result.reply,
                "thread_id": result.child_thread_id,
                "linked_objects": result.linked_objects,
                "pending_confirmations": result.raw_result.get("pending_confirmations") or [],
            },
            ensure_ascii=False,
            default=str,
        )
        record.error = result.error
        record.updated_at = datetime.utcnow()
        record.finished_at = (
            None
            if result.status in {"pending", "running", "waiting_confirmation"}
            else datetime.utcnow()
        )
        await self.session.commit()

    async def _finish_parent_step(
        self,
        step_id: int,
        parent_run_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        step = await self.session.get(AgentRunStep, step_id)
        if step:
            step.status = "completed" if status == "completed" else status
            step.summary = (
                f"子任务完成 {payload['summary']['completed']}/{payload['summary']['total']}"
            )
            step.output_json = json.dumps(payload, ensure_ascii=False, default=str)
            step.linked_objects_json = json.dumps(
                [
                    {"type": "agent_run", "id": run_id, "relation": "child_run"}
                    for run_id in payload.get("linked_runs") or []
                ],
                ensure_ascii=False,
            )
            if status == "failed":
                step.error = "一个或多个子任务失败"
        parent = await self.session.get(AgentRun, parent_run_id)
        if parent:
            if status == "waiting_confirmation":
                parent.status = "waiting_confirmation"
            parent.updated_at = datetime.utcnow()
        await self.session.commit()

    @staticmethod
    def _result_dict(result: SubagentExecutionResult, delegation_id: str) -> dict[str, Any]:
        return {
            "delegation_id": delegation_id,
            "task_key": result.task_key,
            "profile_id": result.profile_id,
            "status": result.status,
            "child_run_id": result.child_run_id,
            "child_thread_id": result.child_thread_id,
            "reply": result.reply,
            "linked_objects": result.linked_objects,
            "error": result.error,
        }

    @staticmethod
    def _loads(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback
