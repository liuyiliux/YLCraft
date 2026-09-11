import { useStoryPageContext } from './hooks/useStoryPageContext'
import { StoryWorkspaceShell } from './components/StoryWorkspaceShell'


export default function StoryPage() {
  const ctx = useStoryPageContext()

  return <StoryWorkspaceShell ctx={ctx} />
}
