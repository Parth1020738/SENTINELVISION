import { useState } from 'react';
import { api } from '../api/client';
import { useApi, formatTimestamp } from '../hooks';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import { PlateRead } from '../types';

export default function ANPRPage() {
  const [searchPlate, setSearchPlate] = useState('');
  const [matchType, setMatchType] = useState<'exact' | 'partial'>('partial');
  const [searchParams, setSearchParams] = useState<{ plate: string; match: 'exact' | 'partial' } | null>(null);

  const results = useApi(
    () => (searchParams ? api.searchPlates(searchParams.plate, searchParams.match) : Promise.resolve({ query: '', normalized_query: '', match: 'partial', count: 0, results: [] })),
    [searchParams],
    undefined
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchPlate.trim()) {
      setSearchParams({ plate: searchPlate.trim(), match: matchType });
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1720px] mx-auto">
      <div className="bg-surface-container-low p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-label-sm text-primary uppercase tracking-widest bg-primary-container/20 px-2 py-0.5 rounded">OPTICAL SENSOR PIPELINE // OCR</span>
        </div>
        <h1 className="font-headline-lg text-on-surface font-bold tracking-tight">Automatic Number Plate Recognition</h1>
        <p className="font-body-sm text-on-surface-variant">Real-time optical character extraction, vehicle class association, and confidence scoring.</p>
      </div>

      <div className="card p-4">
        <form onSubmit={handleSearch} className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">License Plate</label>
            <input type="text" value={searchPlate} onChange={(e) => setSearchPlate(e.target.value)} placeholder="Enter plate number" className="input-field" />
          </div>
          <div>
            <label className="font-label-sm text-on-surface-variant uppercase tracking-wider mb-1 block">Match</label>
            <select value={matchType} onChange={(e) => setMatchType(e.target.value as 'exact' | 'partial')} className="select-field w-32">
              <option value="partial">Partial</option>
              <option value="exact">Exact</option>
            </select>
          </div>
          <button type="submit" className="btn-primary">Search</button>
        </form>
      </div>

      {searchParams && (
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h2 className="font-headline-sm text-on-surface font-bold">Search Results</h2>
            {results.status === 'success' && <span className="font-code-telemetry text-label-sm text-on-surface-variant">{results.data?.count} found</span>}
          </div>
          <div className="p-4">
            {results.status === 'loading' && <LoadingState message="Searching plates..." />}
            {results.status === 'error' && <ErrorState message={results.error} onRetry={results.refresh} />}
            {results.status === 'success' && results.data && (
              results.data.count === 0 ? (
                <EmptyState icon="document_scanner" title="No license plates detected" description="No matching plates found. The ANPR system may not have captured readable plates yet." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-outline-variant/20">
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Plate</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Vehicle ID</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Camera</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Confidence</th>
                        <th className="text-left py-2 px-3 font-label-sm text-outline">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.data.results.map((plate: PlateRead, idx: number) => (
                        <tr key={idx} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                          <td className="py-2 px-3 font-code-telemetry text-label-sm text-primary font-bold">{plate.normalized_plate || plate.raw_ocr || '—'}</td>
                          <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface">{plate.canonical_vehicle_id}</td>
                          <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface-variant">{plate.camera_id}</td>
                          <td className="py-2 px-3 font-code-telemetry text-label-sm text-secondary">{plate.ocr_confidence ? `${(plate.ocr_confidence * 100).toFixed(1)}%` : '—'}</td>
                          <td className="py-2 px-3 font-code-telemetry text-label-sm text-on-surface-variant">{formatTimestamp(plate.timestamp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {!searchParams && (
        <div className="card p-8">
          <EmptyState icon="document_scanner" title="Search for license plates" description="Enter a plate number to search the ANPR database." />
        </div>
      )}
    </div>
  );
}
