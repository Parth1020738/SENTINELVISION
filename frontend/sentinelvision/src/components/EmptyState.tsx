interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon = 'inbox', title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <span className="material-symbols-outlined text-[40px] text-outline">{icon}</span>
      <h3 className="font-headline-sm text-on-surface font-bold">{title}</h3>
      {description && (
        <p className="font-body-sm text-on-surface-variant text-center max-w-md">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
