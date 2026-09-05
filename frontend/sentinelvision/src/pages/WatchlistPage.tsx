import { useState } from 'react';
import { api } from '../api/client';
import { useApi, getPriorityColor, getCategoryColor } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import { WATCHLIST_CATEGORIES, WATCHLIST_PRIORITIES, WatchlistEntry } from '../types';

export default function WatchlistPage() {
  const watchlist = useApi(() => api.getWatchlist(), [], 10000);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingEntry, setEditingEntry] = useState<WatchlistEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plate, setPlate] = useState('');
  const [reason, setReason] = useState('');
  const [category, setCategory] = useState('OTHER');
  const [priority, setPriority] = useState('MEDIUM');
  const [notes, setNotes] = useState('');
  const refresh = () => { watchlist.refresh(); setError(null); };

  const handleDeactivate = async (p: string) => {
    try { await api.deleteWatchlistEntry(p); refresh(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : 'Failed'); }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingEntry) {
        await api.updateWatchlistEntry(editingEntry.normalized_plate, { reason, category, priority, notes });
      } else {
        await api.createWatchlistEntry({ plate, reason, category, priority, notes: notes || undefined });
      }
      setShowAddForm(false); setEditingEntry(null); setPlate(''); setReason(''); setNotes('');
      refresh();
    } catch (err: unknown) { setError(err instanceof Error ? err.message : 'Failed'); }
  };

  const startEdit = (entry: WatchlistEntry) => {
    setEditingEntry(entry); setShowAddForm(false);
    setPlate(entry.normalized_plate); setReason(entry.reason); setCategory(entry.category); setPriority(entry.priority); setNotes(entry.notes || '');
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2"><span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">WATCHLIST MANAGEMENT</span></div>
          <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Vehicle Watchlist</h1>
          <p className="font-body-sm text-on-surface-variant">Manage watched plates for automated alert generation.</p>
        </div>
        <button onClick={() => { setShowAddForm(true); setEditingEntry(null); }} className="btn-primary">+ Add Entry</button>
      </div>
      {error && <div className="card p-4 border-l-4 border-error"><p className="text-error">{error}</p></div>}



      {(showAddForm || editingEntry) && (
        <div className="card p-4">
          <h3 className="font-headline-sm text-on-surface font-bold mb-4">{editingEntry ? 'Edit' : 'Add'} Watchlist Entry</h3>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div><label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Plate *</label><input type="text" value={plate} onChange={(e) => setPlate(e.target.value)} className="input-field" disabled={!!editingEntry} required /></div>
            <div><label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Category *</label><select value={category} onChange={(e) => setCategory(e.target.value)} className="select-field">{WATCHLIST_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
            <div><label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Priority *</label><select value={priority} onChange={(e) => setPriority(e.target.value)} className="select-field">{WATCHLIST_PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}</select></div>
            <div><label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Reason *</label><input type="text" value={reason} onChange={(e) => setReason(e.target.value)} className="input-field" required /></div>
            <div className="md:col-span-2"><label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Notes</label><textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="input-field" rows={2} /></div>
            <div className="md:col-span-2 flex gap-3 justify-end"><button type="button" onClick={() => { setShowAddForm(false); setEditingEntry(null); }} className="btn-secondary">Cancel</button><button type="submit" className="btn-primary">Save</button></div>
          </form>
        </div>
      )}
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h2 className="font-headline-sm text-on-surface font-bold">Watchlist Entries</h2>
          {watchlist.status === 'success' && <span className="font-code-telemetry text-label-sm text-on-surface-variant">{watchlist.data?.count} entries</span>}
        </div>
        <div className="p-4">
          {watchlist.status === 'loading' && <LoadingState message="Loading watchlist..." />}
          {watchlist.status === 'error' && <ErrorState message={watchlist.error} onRetry={refresh} />}
          {watchlist.status === 'success' && watchlist.data?.results.length === 0 && <EmptyState icon="shield_with_heart" title="No watchlist entries" />}
          {watchlist.status === 'success' && watchlist.data && watchlist.data.results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-outline-variant/20">
                  <th className="text-left py-2 px-3 font-label-sm text-outline">Plate</th>
                  <th className="text-left py-2 px-3 font-label-sm text-outline">Category</th>
                  <th className="text-left py-2 px-3 font-label-sm text-outline">Priority</th>
                  <th className="text-left py-2 px-3 font-label-sm text-outline">Reason</th>
                  <th className="text-left py-2 px-3 font-label-sm text-outline">Status</th>
                  <th className="text-right py-2 px-3 font-label-sm text-outline">Actions</th>
                </tr></thead>
                <tbody>
                  {watchlist.data.results.map((entry: WatchlistEntry) => (
                    <tr key={entry.id} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                      <td className="py-2 px-3 font-code-telemetry text-label-sm text-primary font-bold">{entry.normalized_plate}</td>
                      <td className="py-2 px-3"><span className={'status-badge ' + getCategoryColor(entry.category)}>{entry.category}</span></td>
                      <td className="py-2 px-3"><span className={'status-badge ' + getPriorityColor(entry.priority)}>{entry.priority}</span></td>
                      <td className="py-2 px-3 text-on-surface-variant max-w-xs truncate">{entry.reason}</td>
                      <td className="py-2 px-3"><span className={'status-badge ' + (entry.active ? 'bg-secondary/20 text-secondary' : 'bg-surface-container-high text-outline')}>{entry.active ? 'ACTIVE' : 'INACTIVE'}</span></td>
                      <td className="py-2 px-3 text-right">
                        <button onClick={() => startEdit(entry)} className="text-primary hover:underline text-sm mr-2">Edit</button>
                        {entry.active && <button onClick={() => handleDeactivate(entry.normalized_plate)} className="text-error hover:underline text-sm">Deactivate</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
