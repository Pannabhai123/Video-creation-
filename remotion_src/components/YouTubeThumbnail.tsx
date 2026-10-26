import React from 'react';
import {AbsoluteFill, Img} from 'remotion';

export interface YouTubeThumbnailProps {
  title: string;
  badgeText: string;
  channelName: string;
  accentColor: string;
  secondaryColor: string;
  heroImageUrl?: string;
}

export const YouTubeThumbnail: React.FC<YouTubeThumbnailProps> = ({
  title,
  badgeText,
  channelName,
  accentColor,
  secondaryColor,
  heroImageUrl,
}) => {
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(circle at 20% 25%, #172554 0%, #0B1120 60%, #050811 100%)',
        fontFamily: '"Poppins", "Noto Sans Devanagari", "DejaVu Sans", sans-serif',
        color: '#FFFFFF',
        padding: '92px 104px',
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 64,
        overflow: 'hidden',
      }}
    >
      {/* Subtle architectural grid */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
          backgroundSize: '68px 68px',
        }}
      />

      {/* Left Headline Column */}
      <div style={{flex: 1.15, zIndex: 2, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%'}}>
        <div>
          <span
            style={{
              display: 'inline-block',
              backgroundColor: accentColor,
              color: '#08101D',
              padding: '10px 28px',
              borderRadius: 999,
              fontSize: 32,
              fontWeight: 800,
              letterSpacing: 1.2,
              marginBottom: 34,
            }}
          >
            {badgeText}
          </span>

          <h1
            style={{
              fontSize: 92,
              lineHeight: 1.14,
              fontWeight: 900,
              margin: 0,
              textShadow: '0 10px 28px rgba(0,0,0,0.65)',
              color: '#FFFFFF',
            }}
          >
            {title}
          </h1>
        </div>

        <div style={{display: 'flex', alignItems: 'center', gap: 18}}>
          <div style={{width: 18, height: 52, borderRadius: 6, backgroundColor: secondaryColor}} />
          <span style={{fontSize: 34, fontWeight: 700, color: '#CBD5E1', letterSpacing: 1}}>
            {channelName}
          </span>
        </div>
      </div>

      {/* Right Visual Showcase Card */}
      <div
        style={{
          flex: 0.85,
          height: 780,
          zIndex: 2,
          borderRadius: 36,
          overflow: 'hidden',
          border: `5px solid ${accentColor}`,
          background: `radial-gradient(circle at 35% 25%, ${accentColor}38, #0F172A 75%)`,
          boxShadow: '0 28px 70px rgba(0,0,0,0.55)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {heroImageUrl ? (
          <Img src={heroImageUrl} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        ) : (
          <div style={{padding: 48, textAlign: 'center'}}>
            <div style={{fontSize: 108, fontWeight: 900, color: accentColor, lineHeight: 1}}>100%</div>
            <div style={{fontSize: 34, fontWeight: 700, color: '#E2E8F0', marginTop: 22}}>
              PRACTICAL SUMMARY
            </div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
