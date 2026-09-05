interface StatCardProps {
  icon: string;
  label: string;
  value: string | number;
  sublabel?: string;
  trend?: { value: string; positive?: boolean };
  color?: string;
}

export default function StatCard({ icon, label, value, sublabel, trend, color = 'text-primary' }: StatCardProps) {
  return (
    <div className="card p-4 relative overflow-hidden">
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className="font-label-sm text-outline uppercase tracking-wider">{label}</span>
          <div className="flex items-baseline gap-2">
            <span className={`font-headline-xl text-on-surface font-bold ${color}`}>{value}</span>
            {trend && (
              <span className={`font-code-telemetry text-label-sm flex items-center gap-0.5 ${trend.positive ? 'text-secondary' : 'text-error'}`}>
                <span className="material-symbols-outlined text-[14px]">
                  {trend.positive ? 'arrow_upward' : 'arrow_downward'}
                </span>
                {trend.value}
              </span>
            )}
          </div>
          {sublabel && (
            <span className="font-code-telemetry text-label-sm text-on-surface-variant">{sublabel}</span>
          )}
        </div>
        <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center">
          <span className={`material-symbols-outlined text-[24px] ${color}`}>{icon}</span>
        </div>
      </div>
      <div className="absolute -right-4 -bottom-4 w-20 h-20 rounded-full bg-primary/5 pointer-events-none" />
    </div>
  );
}
