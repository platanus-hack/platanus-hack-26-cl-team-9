import { Component, type ErrorInfo, type ReactNode } from "react";
/** Catches a render error below it and offers a reload instead of a blank page. Renders `children` unchanged otherwise. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("render error", error, info.componentStack); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert">
        <p>Algo salió mal al mostrar el mapa.</p>
        <button type="button" onClick={() => location.reload()}>Recargar</button>
      </div>
    );
  }
}
