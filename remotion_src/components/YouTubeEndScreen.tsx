import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export interface YouTubeEndScreenProps {
  channelName: string;
  channelTagline: string;
  accentColor: string;
  secondaryColor: string;
}

export const YouTubeEndScreen: React.FC<YouTubeEndScreenProps> = ({
  channelName,
  channelTagline,
  accentColor,
  secondaryColor,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const mainSpring = spring({frame, fps, config: {damping: 14, stiffness: 110}});
  const cardSpring = spring({frame: Math.max(0, frame - 8), fps, config: {damping: 16, stiffness: 105}});
  const pulse = interpolate(Math.sin(frame / 6), [-1, 1], [0.97, 1.04]);

  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(circle at 50% 20%, #1E293B 0%, #090D16 70%)',
        fontFamily: '"Poppins", "DejaVu Sans", sans-serif',
        color: '#F8FAFC',
        padding: '68px 120px 132px 120px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      {/* Header Thank You & Subscribe CTA */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          opacity: mainSpring,
          transform: `translateY(${(1 - mainSpring) * 24}px)`,
        }}
      >
        <div>
          <div style={{fontSize: 24, color: accentColor, fontWeight: 700, letterSpacing: 1.6}}>
            THANKS FOR WATCHING
          </div>
          <h2 style={{fontSize: 60, margin: '8px 0 6px 0', fontWeight: 800}}>{channelName}</h2>
          <p style={{fontSize: 26, margin: 0, color: '#94A3B8'}}>{channelTagline}</p>
        </div>

        {/* Subscribe CTA Pill */}
        <div
          style={{
            backgroundColor: '#EF4444',
            color: '#FFFFFF',
            padding: '20px 44px',
            borderRadius: 999,
            fontSize: 30,
            fontWeight: 800,
            letterSpacing: 1.2,
            transform: `scale(${pulse})`,
            boxShadow: '0 16px 40px rgba(239, 68, 68, 0.45)',
          }}
        >
          SUBSCRIBE + BELL
        </div>
      </div>

      {/* Compliant YouTube End Screen 16:9 Video Card Slots + Avatar Slot */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 54,
          marginTop: 32,
          opacity: cardSpring,
          transform: `translateY(${(1 - cardSpring) * 32}px)`,
        }}
      >
        {/* Watch Next 16:9 Card */}
        <div
          style={{
            width: 610,
            height: 343,
            borderRadius: 24,
            border: `3px solid ${accentColor}`,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-end',
            padding: 30,
            boxShadow: '0 20px 48px rgba(0,0,0,0.45)',
          }}
        >
          <span style={{color: accentColor, fontSize: 20, fontWeight: 700, letterSpacing: 1.4}}>
            WATCH NEXT
          </span>
          <span style={{fontSize: 28, fontWeight: 700, marginTop: 6}}>
            Recommended Deep-Dive Episode
          </span>
        </div>

        {/* Center Channel Subscribe Circle */}
        <div
          style={{
            width: 210,
            height: 210,
            borderRadius: '50%',
            border: `4px solid ${secondaryColor}`,
            background: `linear-gradient(135deg, ${accentColor}33, ${secondaryColor}33)`,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            textAlign: 'center',
            fontWeight: 800,
            fontSize: 24,
            padding: 20,
          }}
        >
          CHANNEL
          <br />
          ICON
        </div>

        {/* Best For Viewer 16:9 Card */}
        <div
          style={{
            width: 610,
            height: 343,
            borderRadius: 24,
            border: `3px solid ${secondaryColor}`,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-end',
            padding: 30,
            boxShadow: '0 20px 48px rgba(0,0,0,0.45)',
          }}
        >
          <span style={{color: secondaryColor, fontSize: 20, fontWeight: 700, letterSpacing: 1.4}}>
            BEST FOR VIEWER
          </span>
          <span style={{fontSize: 28, fontWeight: 700, marginTop: 6}}>
            Full Production Playlist
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
