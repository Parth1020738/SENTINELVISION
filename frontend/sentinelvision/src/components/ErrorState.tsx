interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <span className="material-symbols-outlined text-[40px] text-error">error</span>
      <p className="font-body-sm text-on-surface-variant text-center max-w-md">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-primary mt-2">
          Retry
        </button>
      )}
    </div>
  );
}
