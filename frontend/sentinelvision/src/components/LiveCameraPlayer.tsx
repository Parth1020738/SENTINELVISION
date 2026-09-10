import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';

interface LiveCameraPlayerProps {
  cameraId: string;
  cameraName?: string | null;
  resolution?: string | null;
  aiActive?: boolean;
}

export type PlayerConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'RECONNECTING' | 'OFFLINE' | 'ERROR';

export default function LiveCameraPlayer({
  cameraId,
  cameraName,
  resolution,
  aiActive = false,
}: LiveCameraPlayerProps) {
  const imgRef = useRef<HTMLImageElement | null>(null);

  const [streamSrc, setStreamSrc] = useState<string>('');
  const [status, setStatus] = useState<PlayerConnectionStatus>('CONNECTING');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState<number>(0);

  const handleRetry = () => {
    setRetryCount((prev) => prev + 1);
  };

  useEffect(() => {
    // Form fresh stream URL with timestamp cache buster
    const baseUrl = api.getCameraLiveUrl(cameraId);
    const separator = baseUrl.includes('?') ? '&' : '?';
    const url = `${baseUrl}${separator}_t=${Date.now()}`;
    setStreamSrc(url);
    setStatus('CONNECTED');
    setErrorMsg(null);

    return () => {
      // Stop image stream download on unmount/camera change
      setStreamSrc('');
    };
  }, [cameraId, retryCount]);

  const isPlaying = status === 'CONNECTED';

  return (
    <div className="lg:col-span-2 card overflow-hidden flex flex-col bg-surface-container-lowest">
      {/* Player Header */}
      <div className="card-header flex items-center justify-between bg-surface-container-low p-3 border-b border-outline-variant/40">
        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              status === 'CONNECTED'
                ? 'bg-secondary animate-pulse'
                : status === 'CONNECTING' || status === 'RECONNECTING'
                ? 'bg-warning animate-pulse'
                : status === 'OFFLINE'
                ? 'bg-outline'
                : 'bg-error'
            }`}
          />
          <span className="font-code-telemetry text-label-md text-on-surface font-bold">
            {cameraId}: {cameraName || `Camera ${cameraId}`}
          </span>
          <span
            className={`status-badge text-[11px] px-2 py-0.5 rounded font-bold ${
              status === 'CONNECTED'
                ? 'bg-secondary/20 text-secondary border border-secondary/30'
                : status === 'CONNECTING' || status === 'RECONNECTING'
                ? 'bg-warning/20 text-warning border border-warning/30'
                : status === 'OFFLINE'
                ? 'bg-surface-container-high text-on-surface-variant'
                : 'bg-error/20 text-error border border-error/30'
            }`}
          >
            {status}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="font-code-telemetry text-label-sm text-on-surface-variant">
            {resolution || '1920x1080'}
          </span>
          <span className="font-code-telemetry text-label-sm bg-surface-container-high px-2 py-0.5 rounded text-on-surface-variant">
            Protocol: MJPEG Stream (Authenticated)
          </span>
        </div>
      </div>

      {/* Video / Stream Viewport Area */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden group">
        {streamSrc && (
          <img
            ref={imgRef}
            src={streamSrc}
            alt={`Live feed for ${cameraId}`}
            className={`w-full h-full object-contain ${isPlaying ? 'block' : 'hidden'}`}
            onError={() => {
              setStatus('ERROR');
              setErrorMsg('Unable to receive live video frames from server relay.');
            }}
          />
        )}

        {/* Overlay Badges when Stream is Connected & Playing */}
        {isPlaying && (
          <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none z-10">
            <span className="bg-error text-white font-code-telemetry text-[11px] font-bold px-2 py-0.5 rounded flex items-center gap-1 shadow-md">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
              LIVE
            </span>
            {aiActive && (
              <span className="bg-primary/90 text-primary-container font-code-telemetry text-[11px] font-bold px-2 py-0.5 rounded shadow-md">
                AI ACTIVE (RTSP Frame Relay)
              </span>
            )}
          </div>
        )}

        {/* Loading State Overlay (CONNECTING or RECONNECTING) */}
        {(status === 'CONNECTING' || status === 'RECONNECTING') && (
          <div className="absolute inset-0 bg-surface-container-lowest/90 flex flex-col items-center justify-center p-6 text-center z-20">
            <div className="w-10 h-10 border-3 border-primary border-t-transparent rounded-full animate-spin mb-3" />
            <p className="font-code-telemetry text-label-md text-primary font-semibold">
              {status === 'RECONNECTING'
                ? `Reconnecting stream for ${cameraId}...`
                : `Connecting to real stream for ${cameraId}...`}
            </p>
            <p className="font-body-xs text-on-surface-variant mt-1">
              Establishing authenticated server-side RTSP relay channel
            </p>
          </div>
        )}

        {/* Error / Offline State */}
        {(status === 'OFFLINE' || status === 'ERROR') && (
          <div className="absolute inset-0 bg-surface-container-lowest flex flex-col items-center justify-center p-6 text-center z-20">
            <span className="material-symbols-outlined text-[48px] text-error mb-2">
              {status === 'OFFLINE' ? 'videocam_off' : 'signal_disconnected'}
            </span>
            <h4 className="font-headline-sm text-on-surface font-bold mb-1">
              {status === 'OFFLINE' ? 'Camera Offline' : 'Stream Connection Error'}
            </h4>
            <p className="font-body-sm text-on-surface-variant max-w-md mb-4">
              {errorMsg || 'Unable to establish video stream connection.'}
            </p>
            <button
              type="button"
              onClick={handleRetry}
              className="btn btn-secondary flex items-center gap-2 px-4 py-2 text-label-md cursor-pointer"
            >
              <span className="material-symbols-outlined text-[18px]">refresh</span>
              Retry Playback Connection
            </button>
          </div>
        )}
      </div>

      {/* Footer Banner */}
      <div className="p-3 bg-surface-container-low border-t border-outline-variant/30 flex items-center justify-between text-body-xs text-on-surface-variant">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px] text-primary">shield</span>
          <span>
            Browser playback is authenticated; RTSP credentials remain server-side.
          </span>
        </div>
        <span className="font-code-telemetry text-[11px] text-outline">
          Relay: /api/cameras/{cameraId}/live
        </span>
      </div>
    </div>
  );
}

