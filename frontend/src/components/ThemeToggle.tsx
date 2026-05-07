/**
 * YLCraft — 主题切换器
 * 5 套主题一键切换：深海 · 极光 · 暮光 · 月光 · 晨曦
 */
import { useState, useRef, useEffect } from 'react'
import { useTheme } from '../constants/theme'

export default function ThemeToggle() {
  const { themeId, theme, themeDef, setTheme, allThemes } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        title="切换主题"
        style={{
          width: 34,
          height: 34,
          borderRadius: 10,
          border: `1px solid ${theme.border}`,
          background: theme.bgHover,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          transition: 'all 0.2s',
          backdropFilter: 'blur(4px)',
        }}
        onMouseEnter={e => (e.currentTarget.style.background = theme.primaryAlpha(0.12))}
        onMouseLeave={e => (e.currentTarget.style.background = theme.bgHover)}
      >
        {themeDef.icon}
      </button>

      {/* 下拉面板 */}
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            zIndex: 1000,
            minWidth: 200,
            padding: 6,
            borderRadius: 12,
            border: `1px solid ${theme.border}`,
            background: theme.bgElevated,
            backdropFilter: 'blur(16px)',
            boxShadow: `0 8px 32px ${theme.primaryAlpha(0.15)}`,
          }}
        >
          <div style={{ padding: '6px 10px 4px', fontSize: 11, color: theme.textSecondary, letterSpacing: 1, textTransform: 'uppercase' }}>
            主题切换
          </div>
          {allThemes.map(t => {
            const isActive = t.id === themeId
            return (
              <button
                key={t.id}
                onClick={() => { setTheme(t.id); setOpen(false) }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '8px 10px',
                  border: 'none',
                  borderRadius: 8,
                  background: isActive ? theme.bgHover : 'transparent',
                  cursor: 'pointer',
                  color: isActive ? theme.textPrimary : theme.textSecondary,
                  fontSize: 13,
                  transition: 'all 0.15s',
                  textAlign: 'left',
                }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = theme.bgHover }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
              >
                <span style={{ fontSize: 18 }}>{t.icon}</span>
                <span style={{ flex: 1 }}>{t.name}</span>
                {/* 当前主题色圆点 */}
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: t.colors.primary,
                    opacity: isActive ? 1 : 0.4,
                    boxShadow: isActive ? `0 0 8px ${t.colors.primary}` : 'none',
                  }}
                />
              </button>
            )
          })}

          {/* 当前主题名 */}
          <div style={{
            padding: '6px 10px 0',
            fontSize: 10,
            color: theme.textDisabled,
            textAlign: 'center',
          }}>
            {themeDef.icon} {themeDef.name} · 自动保存
          </div>
        </div>
      )}
    </div>
  )
}
