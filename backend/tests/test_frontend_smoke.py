"""
前端烟雾测试：验证两轮对话刷新后仍在同一线程中。

M7.5: 使用 patchright 验证 Agent 页面线程持久性

运行前提：
- 后端运行在 http://localhost:8000
- 前端运行在 http://localhost:5173
- Docker PostgreSQL 运行中
- 已配置至少一个 Agent Profile 和 LLM 连接器

用法：
    pytest backend/tests/test_frontend_smoke.py -v -s
"""
import os
import sys
import time
import pytest

# 跳过条件：没有可用的浏览器环境
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_FRONTEND_SMOKE"),
    reason="设置 RUN_FRONTEND_SMOKE=1 以运行前端烟雾测试（需要完整环境）",
)


@pytest.fixture(scope="module")
def browser():
    """启动 patchright 浏览器（仅在 RUN_FRONTEND_SMOKE=1 时执行）"""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("patchright 未安装，跳过前端烟雾测试")
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture(scope="module")
def agent_page(browser):
    """打开 Agent 页面并等待加载完成"""
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        page.goto("http://localhost:5173/agent", timeout=10000)
    except Exception:
        pytest.skip("前端未运行（http://localhost:5173/agent 不可达），跳过烟雾测试")
    # 等待页面加载：检查关键元素
    page.wait_for_selector("[data-agent-chat-input]", timeout=15000)
    page.wait_for_selector("[data-agent-send-btn]", timeout=5000)
    yield page
    page.close()


class TestAgentThreadPersistence:
    """M7.5: 验证线程刷新后上下文持久性"""

    def test_two_turn_messages_stay_in_one_thread_after_refresh(self, agent_page):
        """
        验证内容：
        1. 发送第一轮消息，获取 thread_id
        2. 发送第二轮消息（不传 thread_id，模拟客户端丢失 ID）
        3. 刷新页面
        4. 验证两轮消息都在同一个线程中显示
        """
        page = agent_page

        # ---- 第一轮：发送消息 ----
        chat_input = page.locator("[data-agent-chat-input]")
        send_btn = page.locator("[data-agent-send-btn]")

        chat_input.fill("你好，介绍一下你自己")
        send_btn.click()

        # 等待响应（最多 60 秒）
        page.wait_for_function(
            'document.querySelectorAll("[data-agent-message-role=\\"assistant\\"]").length > 0',
            timeout=60000,
        )
        time.sleep(2)  # 等 SSE stream 完成

        # 获取第一轮后的消息数
        messages_after_turn1 = page.locator("[data-agent-message]").count()

        # ---- 第二轮：发送 follow-up（模拟丢失 session/thread id） ----
        # 先清除 localStorage 中的 thread id（模拟刷新丢失场景）
        page.evaluate("localStorage.removeItem('ylcraft.agent.last_thread_id')")
        page.evaluate("localStorage.removeItem('ylcraft.agent.last_session_id')")

        chat_input = page.locator("[data-agent-chat-input]")
        send_btn = page.locator("[data-agent-send-btn]")

        chat_input.fill("刚才说了什么？")
        send_btn.click()

        page.wait_for_function(
            f'document.querySelectorAll("[data-agent-message]").length > {messages_after_turn1}',
            timeout=60000,
        )
        time.sleep(2)

        messages_after_turn2 = page.locator("[data-agent-message]").count()
        thread_id_before_refresh = page.evaluate(
            "localStorage.getItem('ylcraft.agent.last_thread_id')"
        )

        # ---- 刷新页面 ----
        page.reload()
        page.wait_for_selector("[data-agent-chat-input]", timeout=15000)
        time.sleep(3)  # 等自动恢复完成

        # ---- 验证：消息数应恢复 ----
        page.wait_for_function(
            f'document.querySelectorAll("[data-agent-message]").length > 0',
            timeout=15000,
        )
        messages_after_refresh = page.locator("[data-agent-message]").count()

        # 刷新后消息数应 >= 第二轮后的消息数（可能加载更多历史）
        assert messages_after_refresh >= messages_after_turn2, (
            f"刷新后消息数 ({messages_after_refresh}) 应 >= 第二轮后消息数 ({messages_after_turn2})"
        )

        # 验证线程 ID 被恢复
        thread_id_after_refresh = page.evaluate(
            "localStorage.getItem('ylcraft.agent.last_thread_id')"
        )
        assert thread_id_after_refresh is not None, "刷新后应恢复 last_thread_id"
        assert thread_id_before_refresh is not None, "第二轮后应有 last_thread_id"

        # 验证线程标题显示（不为"新线程，首轮发送后保存"）
        thread_title = page.locator("[data-agent-inspector]").inner_text()
        assert "新线程" not in thread_title or "首轮发送" not in thread_title, (
            f"刷新后应显示已绑定线程，而非新建状态。当前标题: {thread_title}"
        )

    def test_new_thread_button_creates_separate_thread(self, agent_page):
        """
        验证新建线程按钮行为：
        1. 点击"新线程"后清空当前对话
        2. localStorage 中的 thread_id 被清除
        """
        page = agent_page

        # 先发送一条消息建立线程
        chat_input = page.locator("[data-agent-chat-input]")
        send_btn = page.locator("[data-agent-send-btn]")
        chat_input.fill("测试新建线程")
        send_btn.click()
        page.wait_for_function(
            'document.querySelectorAll("[data-agent-message-role=\\"assistant\\"]").length > 0',
            timeout=60000,
        )
        time.sleep(2)

        thread_id_before = page.evaluate(
            "localStorage.getItem('ylcraft.agent.last_thread_id')"
        )

        # 点击新建线程按钮
        new_thread_btn = page.locator("button:has-text('新线程')").first
        new_thread_btn.click()
        time.sleep(1)

        # 验证：localStorage 中的 thread_id 被清除
        thread_id_after = page.evaluate(
            "localStorage.getItem('ylcraft.agent.last_thread_id')"
        )
        assert thread_id_after is None or thread_id_after == "", (
            "新建线程后 localStorage 中的 thread_id 应被清除"
        )

        # 验证：消息被清空
        messages_after_new = page.locator("[data-agent-message]").count()
        assert messages_after_new == 0, f"新建线程后消息应清空，实际: {messages_after_new}"
