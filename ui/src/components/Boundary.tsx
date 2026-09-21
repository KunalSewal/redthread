/* Keeps one broken panel from taking the case file with it.
 *
 * Tool digests are shaped by whatever the graph returned, so a renderer can meet a field it did not
 * expect. Without this, that throws during render and React unmounts the whole tree — the reader
 * loses the verdict, the thread and the evidence because one panel could not draw a list. Here it
 * loses the panel.
 */
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props { children: ReactNode; label: string }
interface State { message: string | null }

export class Boundary extends Component<Props, State> {
  state: State = { message: null }

  static getDerivedStateFromError(error: Error): State {
    return { message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`${this.props.label} failed to render`, error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    // A new child (the next step, say) deserves a fresh attempt.
    if (prev.children !== this.props.children && this.state.message) this.setState({ message: null })
  }

  render() {
    if (this.state.message === null) return this.props.children
    return (
      <p className="empty boundary-failed">
        {this.props.label} could not be displayed. The rest of the case is unaffected.
        <br />
        <code>{this.state.message}</code>
      </p>
    )
  }
}
