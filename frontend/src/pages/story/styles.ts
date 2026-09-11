/**
 * 创作项目工作台：styles.ts。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { type ThemeColors } from '../../constants/theme'
import { ProjectGraphNode } from './types'
import React from 'react'

export function graphNodeStyle(node: ProjectGraphNode, selected: boolean): React.CSSProperties {
  return {
    position: 'absolute',
    border: selected ? '2px solid var(--primary)' : '1px solid var(--borderLight)',
    borderRadius: 8,
    padding: 10,
    background: 'var(--bgElevated)',
    boxShadow: selected ? '0 10px 30px rgba(0, 0, 0, 0.18)' : '0 6px 18px rgba(0, 0, 0, 0.08)',
    cursor: 'grab',
    userSelect: 'none',
    color: 'var(--textPrimary)',
    outline: node.type === 'prompt' ? '1px dashed rgba(168, 85, 247, 0.35)' : undefined,
  }
}

export const panelStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 14,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

export function createWorkbenchHeaderStyle(theme: ThemeColors): React.CSSProperties {
  return {
  border: `1px solid ${theme.borderLight}`,
  borderRadius: 8,
  padding: 14,
  background: theme.bgElevated,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
  color: theme.textPrimary,
  }
}

export function createCompactBlockStyle(theme: ThemeColors): React.CSSProperties {
  return {
  border: `1px solid ${theme.borderLight}`,
  borderRadius: 8,
  padding: 10,
  background: theme.bgElevated,
  color: theme.textPrimary,
  }
}

export const readerPanelStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '22px 26px',
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minWidth: 0,
}

export const readerTextStyle: React.CSSProperties = {
  margin: '18px 0 0',
  whiteSpace: 'pre-wrap',
  fontSize: 16,
  lineHeight: 1.9,
  color: 'var(--textPrimary)',
}

export const readerLayoutStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '260px minmax(0, 1fr)',
  gap: 12,
  alignItems: 'start',
}

export const readerTocStyle: React.CSSProperties = {
  ...panelStyle,
  position: 'sticky',
  top: 12,
}

export const readerTocListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  maxHeight: 520,
  overflow: 'auto',
}

export const readerTocButtonStyle: React.CSSProperties = {
  width: '100%',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '8px 10px',
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  textAlign: 'left',
  cursor: 'pointer',
  display: 'grid',
  gap: 2,
}

export const readerTocButtonActiveStyle: React.CSSProperties = {
  borderColor: 'var(--primary)',
  background: 'var(--bgHover)',
}

export const writerRoomComparePaneStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgCard)',
  minWidth: 0,
}

export const writerRoomDiffListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  maxHeight: 720,
  overflow: 'auto',
  paddingRight: 4,
}

export const writerRoomDiffRowStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
}

export const writerRoomDiffColumnsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))',
  gap: 8,
  marginTop: 8,
}

export const writerRoomDiffTextStyle: React.CSSProperties = {
  borderRadius: 6,
  minWidth: 0,
  padding: '8px 10px',
}

export const writerRoomShellStyle: React.CSSProperties = {
  ...panelStyle,
  background: 'linear-gradient(135deg, var(--bgElevated), var(--bgCard))',
}

export const writerRoomProgressStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(160px, 1fr) auto',
  gap: 10,
  alignItems: 'center',
  marginTop: 12,
}

export const writerRoomBatchControlStyle: React.CSSProperties = {
  marginTop: 12,
  borderTop: '1px solid var(--borderLight)',
  paddingTop: 12,
}

export const writerRoomWorkspaceStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(min(100%, 280px), 0.42fr) minmax(min(100%, 420px), 1fr)',
  gap: 12,
  alignItems: 'start',
}

export const writerRoomPipelineStyle: React.CSSProperties = {
  ...panelStyle,
  position: 'sticky',
  top: 12,
}

export const writerRoomStepListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
}

export const writerRoomStepButtonStyle: React.CSSProperties = {
  width: '100%',
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '10px 11px',
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  textAlign: 'left',
  cursor: 'pointer',
  transition: 'border-color 160ms ease, background 160ms ease, transform 160ms ease',
}

export const writerRoomStepButtonActiveStyle: React.CSSProperties = {
  ...writerRoomStepButtonStyle,
  border: '1px solid var(--primary)',
  background: 'var(--bgHover)',
  transform: 'translateX(2px)',
}

export const writerRoomStepIndexStyle: React.CSSProperties = {
  width: 24,
  height: 24,
  borderRadius: 6,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flex: '0 0 auto',
  background: 'var(--bgElevated)',
  border: '1px solid var(--borderLight)',
  color: 'var(--textSecondary)',
  fontSize: 12,
}

export const writerRoomStepTitleStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  minWidth: 0,
}

export const writerRoomMainPanelStyle: React.CSSProperties = {
  ...panelStyle,
  minWidth: 0,
}

export const writerRoomMetricGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
  gap: 8,
}

export const writerRoomMetricStyle: React.CSSProperties = {
  display: 'grid',
  gap: 4,
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

export const writerRoomContextGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
  gap: 8,
}

export const writerRoomContextBlockStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  minWidth: 0,
}

export const writerRoomPreviewStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minHeight: 260,
  maxHeight: 680,
  overflow: 'auto',
}

export const writerRoomVersionStatusStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
  padding: '10px 12px',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  background: 'var(--bgElevated)',
}

export const writerRoomPromoteSummaryStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
  gap: 8,
}

export const writerRoomIssueStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
}

export const writerRoomContinuityStyle: React.CSSProperties = {
  borderTop: '1px solid var(--border-color)',
  paddingTop: 14,
}

export const writerRoomContinuityItemStyle: React.CSSProperties = {
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  padding: '10px 12px',
  background: 'var(--component-background)',
}

export const writerRoomParagraphListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  maxHeight: 320,
  overflow: 'auto',
  paddingRight: 4,
}

export const writerRoomParagraphButtonStyle: React.CSSProperties = {
  width: '100%',
  textAlign: 'left',
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  background: 'var(--component-background)',
  padding: '10px 12px',
  cursor: 'pointer',
}

export const writerRoomParagraphButtonActiveStyle: React.CSSProperties = {
  borderColor: 'var(--primary)',
  boxShadow: 'inset 3px 0 0 var(--primary)',
}

export const writerRoomQualityStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgHover)',
  color: 'var(--textPrimary)',
}

export const writerRoomTeamGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
  alignItems: 'start',
}

export const writerRoomTeamRoleStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderLeft: '3px solid var(--primary)',
  borderRadius: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  overflow: 'hidden',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
}

export const writerRoomTeamRoleHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '12px 14px',
  cursor: 'pointer',
  userSelect: 'none',
  transition: 'background 0.2s ease',
}

export const writerRoomTeamAvatarStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: '50%',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bgHover)',
  border: '1px solid var(--borderLight)',
  color: 'var(--textPrimary)',
  fontSize: 13,
  fontWeight: 600,
  flexShrink: 0,
}

export const writerRoomTeamRoleBodyStyle: React.CSSProperties = {
  padding: '4px 14px 14px',
  borderTop: '1px solid var(--borderLight)',
  background: 'var(--bgElevated)',
}

export const writerRoomTeamJoinStyle: React.CSSProperties = {
  borderTop: '1px dashed var(--borderLight)',
  paddingTop: 12,
}

export const writerRoomLogBlockStyle: React.CSSProperties = {
  margin: 0,
  maxHeight: 260,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

export const comicPreviewGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
}

export const comicPreviewPageStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minHeight: 180,
}

export const inlineImageShellStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  alignItems: 'center',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

export const referenceAssetCardStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  alignItems: 'center',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 8,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

export const referenceAssetPlaceholderStyle: React.CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: 6,
  border: '1px solid var(--borderLight)',
  background: 'var(--bgInput)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--textSecondary)',
}

export function createResizeHandleStyle(_theme: ThemeColors): React.CSSProperties {
  return {
  alignSelf: 'stretch',
  minHeight: 120,
  cursor: 'col-resize',
  display: 'flex',
  alignItems: 'stretch',
  justifyContent: 'center',
  borderRadius: 8,
  transition: 'background 120ms ease',
  }
}

export function createResizeHandleLineStyle(theme: ThemeColors): React.CSSProperties {
  return {
  width: 2,
  borderRadius: 2,
  background: theme.borderStrong,
  margin: '8px 0',
  }
}

