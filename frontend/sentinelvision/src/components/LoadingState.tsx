interface LoadingStateProps {
  message?: string;
}

export default function LoadingState({ message = 'Loading...' }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <span className="material-symbols-outlined text-[40px] text-primary animate-spin">progress_activity</span>
      <p className="font-code-telemetry text-label-sm text-on-surface-variant">{message}</p>
    </div>
  );
}
