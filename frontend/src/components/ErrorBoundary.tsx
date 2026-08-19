import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Class component because React only supports error boundaries via
// getDerivedStateFromError/componentDidCatch — there is no hook equivalent.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="fb-root" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", padding: "1.5rem" }}>
          <div className="fb-callout" style={{ maxWidth: 420, textAlign: "center" }}>
            <strong>Something went wrong.</strong>
            <p style={{ margin: ".6rem 0 1rem" }}>
              This screen hit an unexpected error. Reloading usually fixes it — your data hasn't been affected.
            </p>
            <button className="fb-btn fb-btn-solid" type="button" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
