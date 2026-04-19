/**
 * YLCraft — Clip Lab 页面
 *
 * 支持三种剪辑模式：
 * - CutClaw Agent：自然语言指令驱动
 * - NarratoAI Pipeline：自动节拍踩点 + VLM 美学评分
 * - MoE 多专家协作
 */

import { Card, Tabs, message } from 'antd'
import { ScissorOutlined } from '@ant-design/icons'

export default function ClipLabPage() {
  return (
    <div>
      <Card
        title={
          <span>
            <ScissorOutlined style={{ marginRight: 8 }} />
            Clip Lab — AI 视频剪辑
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        <Tabs
          items={[
            {
              key: 'cutclaw',
              label: '🤖 CutClaw Agent',
              children: (
                <Card type="inner" title="CutClaw Agent">
                  <p style={{ color: '#8b8ba8' }}>
                    输入自然语言指令，AI Agent 自动分析视频内容并完成剪辑。
                    例如：「把第 30 秒到 1 分钟的内容剪出来，要求保留对话高潮部分」
                  </p>
                  <p style={{ color: '#8b8ba8', marginTop: 16 }}>
                    该模块正在开发中，敬请期待...
                  </p>
                </Card>
              ),
            },
            {
              key: 'narrato',
              label: '🎵 NarratoAI Pipeline',
              children: (
                <Card type="inner" title="NarratoAI Pipeline">
                  <p style={{ color: '#8b8ba8' }}>
                    自动检测节拍踩点，VLM 美学评分筛选高质量片段，
                    支持字幕分析与自动打轴。
                  </p>
                  <p style={{ color: '#8b8ba8', marginTop: 16 }}>
                    该模块正在开发中，敬请期待...
                  </p>
                </Card>
              ),
            },
            {
              key: 'moe',
              label: '🔀 MoE 多专家协作',
              children: (
                <Card type="inner" title="MoE 多专家协作">
                  <p style={{ color: '#8b8ba8' }}>
                    多专家模型协作：节拍专家 + 构图专家 + 叙事专家 +
                    人工审核分流，输出最佳剪辑方案。
                  </p>
                  <p style={{ color: '#8b8ba8', marginTop: 16 }}>
                    该模块正在开发中，敬请期待...
                  </p>
                </Card>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
