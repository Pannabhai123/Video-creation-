import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {SubtitleCue} from '../types';

interface SubtitleOverlayProps {
  cues: SubtitleCue[];
  accentColor: string;
}

export const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({cues, accentColor}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const currentSec = frame / fps;

  const active = cues.find((c) => currentSec >= c.startSec && currentSec <= c.endSec);
  if (!active) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingBottom: 46,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(8, 13, 26, 0.86)',
          border: `2px solid ${accentColor}66`,
          padding: '14px 34px',
          borderRadius: 16,
          maxWidth: 1460,
          textAlign: 'center',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.55)',
        }}
      >
        <span
          style={{
            fontFamily: '"Poppins", "DejaVu Sans", sans-serif',
            fontSize: 36,
            fontWeight: 600,
            color: '#FFFFFF',
            lineHeight: 1.32,
          }}
        >
          {active.text}
        </span>
      </div>
    </AbsoluteFill>
  );
};
